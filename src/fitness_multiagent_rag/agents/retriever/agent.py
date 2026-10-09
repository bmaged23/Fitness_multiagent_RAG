
from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.graph.state import CompiledStateGraph
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

_SRC_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_SRC_DIR))

from config.settings import (
    QDRANT_PROGRAMS_COLLECTION,
    QDRANT_EXERCISES_COLLECTION,
)

from fitness_multiagent_rag.llm.model import get_model
from fitness_multiagent_rag.utils.prompt_loader import load_agent_prompt
from fitness_multiagent_rag.vectorstore.embeddings import embed_one
from fitness_multiagent_rag.vectorstore import qdrant_client as qdrant
from .query_rewrite import Need, decompose, rewrite_query
from .coverage import validate_relevance, check_coverage


# --------------------------------------------------
# Configuration
# --------------------------------------------------

_AGENT_DIR = Path(__file__).parent
_PROJECT_ROOT = _AGENT_DIR.parent.parent.parent.parent
_SKILLS_DIR = "/src/fitness_multiagent_rag/agents/retriever/skills"

_SYSTEM_PROMPT = load_agent_prompt(
    _AGENT_DIR,
    "system_prompt.md",
)

MAX_SEARCH_ATTEMPTS = 3
MAX_TOP_K = 3

# Thread-safe counters, scoped to one agent invocation.
_search_lock = threading.Lock()
_search_counts: dict[str, int] = {}


def _request_id(config: RunnableConfig | None) -> str | None:
    if not config:
        return None

    configurable = config.get("configurable") or {}
    return configurable.get("retriever_request_id")


def _acquire_search_slot(
    request_id: str,
) -> tuple[bool, int]:
    """Reserve a search attempt atomically."""
    with _search_lock:
        used = _search_counts.get(request_id, 0)

        if used >= MAX_SEARCH_ATTEMPTS:
            return False, used

        used += 1
        _search_counts[request_id] = used
        return True, used


def _release_search_budget(request_id: str) -> None:
    """Remove the counter after a request completes."""
    with _search_lock:
        _search_counts.pop(request_id, None)


def _search_response(
    *,
    request_id: str,
    query: str,
    collection: str,
    goal: list[str] | str | None,
    level: list[str] | str | None,
    equipment: list[str] | str | None,
    top_k: int,
    text_chars: int,
) -> dict:
    allowed, attempt = _acquire_search_slot(request_id)

    if not allowed:
        return {
            "search_limit_reached": True,
            "attempts_used": MAX_SEARCH_ATTEMPTS,
            "remaining_searches": 0,
            "message": (
                "Search budget exhausted. Do not call "
                "search_programs or search_exercises again. "
                "Return the best previously retrieved results."
            ),
        }

    vector = embed_one(query)

    hits = qdrant.search(
        collection=collection,
        query_vector=vector,
        top_k=max(1, min(int(top_k), MAX_TOP_K)),
        goal=_coerce_list(goal),
        level=_coerce_list(level),
        equipment=_coerce_list(equipment),
    )

    remaining = MAX_SEARCH_ATTEMPTS - attempt

    return {
        "subquery": query,
        "collection": collection,
        "attempt": attempt,
        "remaining_searches": remaining,
        "search_limit_reached": remaining == 0,
        "chunks": _slim(hits, text_chars=text_chars),
        "message": (
            "SEARCH BUDGET EXHAUSTED. Return final JSON now. "
            "Do not call any more tools."
            if remaining == 0
            else f"{remaining} search attempt(s) remain."
        ),
    }


# --------------------------------------------------
# JSON parsing helpers
# --------------------------------------------------

def _parse_json(
    value: Any,
    expected_type: type,
    argument_name: str,
    default: Any,
) -> Any:
    if value is None or value == "":
        return default

    if isinstance(value, expected_type):
        return value

    if not isinstance(value, str):
        raise ValueError(
            f"{argument_name} must be a "
            f"{expected_type.__name__} or JSON string."
        )

    text = value.strip()

    if not text:
        return default

    fence = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    if fence:
        text = fence.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{argument_name} contains invalid JSON: "
            f"{exc.msg} at position {exc.pos}. "
            f"Input preview: {text[:150]!r}"
        ) from exc

    if not isinstance(data, expected_type):
        raise ValueError(
            f"{argument_name} must contain a JSON "
            f"{expected_type.__name__}."
        )

    return data


def _parse_chunks(
    value: Any,
    argument_name: str,
) -> list[dict]:
    data = _parse_json(
        value,
        list,
        argument_name,
        [],
    )

    if not all(isinstance(item, dict) for item in data):
        raise ValueError(
            f"{argument_name} must contain a JSON array of objects."
        )

    return data


def _tool_input_error(error: ValueError) -> str:
    return (
        f"Invalid tool input: {error}. "
        "Retry with valid JSON using double quotes, "
        "lowercase true/false/null, and no trailing commas."
    )


# --------------------------------------------------
# Search helpers
# --------------------------------------------------

def _coerce_list(val) -> list[str] | None:
    if val is None:
        return None

    if isinstance(val, list):
        return [str(item) for item in val]

    if isinstance(val, str):
        try:
            parsed = json.loads(val)

            if isinstance(parsed, list):
                return [str(item) for item in parsed]

            return [str(parsed)]

        except (json.JSONDecodeError, ValueError):
            return [val]

    return [str(val)]


_KEEP = (
    "id",
    "point_id",
    "source",
    "source_id",
    "goal",
    "level",
    "equipment",
    "program_length_weeks",
    "time_per_workout_min",
    "sets_median",
    "reps_median",
    "is_time_based",
)


def _slim(
    hits: list[dict],
    text_chars: int = 200,
) -> list[dict]:
    out = []

    for h in hits:
        d = {
            k: h[k]
            for k in _KEEP
            if k in h
        }

        d["title"] = (
            h.get("title")
            or h.get("exercise_name")
            or "?"
        )

        d["collection"] = h.get("collection", "")
        d["score"] = round(float(h.get("score") or 0), 3)
        d["text"] = str(h.get("text") or "")[:text_chars]

        out.append(d)

    return out


# --------------------------------------------------
# Search tools
# --------------------------------------------------

@tool
def search_programs(
    query: str,
    goal: list[str] | str | None = None,
    level: list[str] | str | None = None,
    equipment: list[str] | str | None = None,
    top_k: int = 3,
    config: RunnableConfig = None,
) -> dict:
    """Search fitness programs. Shared limit of 3 Qdrant searches."""

    request_id = _request_id(config)

    if not request_id:
        return {
            "error": (
                "Missing retriever_request_id in runnable config."
            )
        }

    return _search_response(
        request_id=request_id,
        query=query,
        collection=QDRANT_PROGRAMS_COLLECTION,
        goal=goal,
        level=level,
        equipment=equipment,
        top_k=top_k,
        text_chars=250,
    )


@tool
def search_exercises(
    query: str,
    goal: list[str] | str | None = None,
    level: list[str] | str | None = None,
    equipment: list[str] | str | None = None,
    top_k: int = 3,
    config: RunnableConfig = None,
) -> dict:
    """Search fitness exercises. Shared limit of 3 Qdrant searches."""

    request_id = _request_id(config)

    if not request_id:
        return {
            "error": (
                "Missing retriever_request_id in runnable config."
            )
        }

    return _search_response(
        request_id=request_id,
        query=query,
        collection=QDRANT_EXERCISES_COLLECTION,
        goal=goal,
        level=level,
        equipment=equipment,
        top_k=top_k,
        text_chars=150,
    )


# --------------------------------------------------
# Query decomposition
# --------------------------------------------------

@tool
def decompose_query(
    query: str,
    trainee_context_json: str,
) -> str:
    """Break a retrieval request into distinct search needs."""

    try:
        context = _parse_json(
            trainee_context_json,
            dict,
            "trainee_context_json",
            {},
        )
    except ValueError as exc:
        return _tool_input_error(exc)

    needs = decompose(query, context)

    return json.dumps([
        {
            "description": n.description,
            "query_text": n.query_text,
            "collection": n.collection,
            "goal": n.goal,
            "level": n.level,
            "equipment": n.equipment,
            "top_k": min(n.top_k, MAX_TOP_K),
        }
        for n in needs[:MAX_SEARCH_ATTEMPTS]
    ])


# --------------------------------------------------
# Query rewriting
# --------------------------------------------------

@tool
def rewrite_search_query(
    need_description: str,
    original_query: str,
    poor_chunks_json: str,
) -> str:
    """Generate improved queries for low-quality retrieval results."""

    try:
        poor_chunks = _parse_chunks(
            poor_chunks_json,
            "poor_chunks_json",
        )
    except ValueError as exc:
        return _tool_input_error(exc)

    need = Need(
        description=need_description,
        query_text=original_query,
        collection=QDRANT_PROGRAMS_COLLECTION,
    )

    sub_queries = rewrite_query(
        need,
        poor_chunks,
    )

    return json.dumps(sub_queries)


# --------------------------------------------------
# Relevance validation
# --------------------------------------------------

@tool
def validate_chunk_relevance(
    need_description: str,
    chunks_json: str,
) -> bool | str:
    """Determine whether chunks match the retrieval need."""

    try:
        chunks = _parse_chunks(
            chunks_json,
            "chunks_json",
        )
    except ValueError as exc:
        return _tool_input_error(exc)

    need = Need(
        description=need_description,
        query_text=need_description,
        collection=QDRANT_PROGRAMS_COLLECTION,
    )

    return validate_relevance(
        need,
        chunks,
    )


# --------------------------------------------------
# Coverage validation
# --------------------------------------------------

@tool
def check_retrieval_coverage(
    original_query: str,
    needs_json: str,
    pool_json: str,
) -> str:
    """Evaluate whether the retrieved pool covers the needs."""

    try:
        needs_descs = _parse_json(
            needs_json,
            list,
            "needs_json",
            [],
        )

        if not all(isinstance(d, str) for d in needs_descs):
            raise ValueError(
                "needs_json must contain an array of strings."
            )

        pool = _parse_chunks(
            pool_json,
            "pool_json",
        )

    except ValueError as exc:
        return _tool_input_error(exc)

    needs = [
        Need(
            description=d,
            query_text=d,
            collection=QDRANT_PROGRAMS_COLLECTION,
        )
        for d in needs_descs
    ]

    result = check_coverage(
        original_query,
        needs,
        pool,
    )

    return json.dumps({
        "satisfied": result.satisfied,
        "gaps": result.gaps,
        "confident": result.confident,
    })


# --------------------------------------------------
# Retriever tools
# --------------------------------------------------

RETRIEVER_TOOLS = [
    decompose_query,
    search_programs,
    search_exercises,
    rewrite_search_query,
    validate_chunk_relevance,
    check_retrieval_coverage,
]


# --------------------------------------------------
# Agent factory
# --------------------------------------------------

def build_retriever_agent() -> CompiledStateGraph:
    """Build the Retriever DeepAgent."""

    backend = FilesystemBackend(
        root_dir=str(_PROJECT_ROOT),
        virtual_mode=True,
    )

    return create_deep_agent(
        model=get_model(),
        tools=RETRIEVER_TOOLS,
        system_prompt=_SYSTEM_PROMPT,
        backend=backend,
        skills=[_SKILLS_DIR],
        name="retriever",
    )


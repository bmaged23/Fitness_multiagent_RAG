
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from threading import Lock
from typing import Any
from dataclasses import asdict, is_dataclass

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.graph.state import CompiledStateGraph

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend


# --------------------------------------------------
# Project configuration
# --------------------------------------------------

_SRC_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_SRC_DIR))

from config.settings import (
    QDRANT_PROGRAMS_COLLECTION,
    QDRANT_EXERCISES_COLLECTION,
    RETRIEVER_PROGRAM_MAX_RETRIES,
    RETRIEVER_EXERCISE_MAX_RETRIES,
)

from fitness_multiagent_rag.llm.model import get_model
from fitness_multiagent_rag.utils.prompt_loader import load_agent_prompt
from fitness_multiagent_rag.vectorstore.embeddings import embed_one
from fitness_multiagent_rag.vectorstore import qdrant_client as qdrant

from .query_rewrite import (
    Need,
    decompose,
    rewrite_query,
)

from .coverage import (
    validate_relevance,
    check_coverage,
)


# --------------------------------------------------
# Paths and prompt
# --------------------------------------------------

_AGENT_DIR = Path(__file__).parent
_PROJECT_ROOT = _AGENT_DIR.parent.parent.parent.parent

_SKILLS_DIR = (
    "/src/fitness_multiagent_rag/agents/retriever/skills"
)

_PROMPT_TEMPLATE = load_agent_prompt(_AGENT_DIR, "system_prompt.md")

_SYSTEM_PROMPT = (
    _PROMPT_TEMPLATE
    .replace("__PROGRAM_MAX_RETRIES__", str(RETRIEVER_PROGRAM_MAX_RETRIES))
    .replace("__EXERCISE_MAX_RETRIES__", str(RETRIEVER_EXERCISE_MAX_RETRIES))
    .replace("__PROGRAM_MAX_SEARCHES__", str(1 + RETRIEVER_PROGRAM_MAX_RETRIES))
    .replace("__EXERCISE_MAX_SEARCHES__", str(1 + RETRIEVER_EXERCISE_MAX_RETRIES))
    .replace(
        "__TOTAL_MAX_SEARCHES__",
        str(2 + RETRIEVER_PROGRAM_MAX_RETRIES + RETRIEVER_EXERCISE_MAX_RETRIES),
    )
)


# --------------------------------------------------
# Search configuration
# --------------------------------------------------

MAX_TOP_K = 3

MAX_SEARCH_ATTEMPTS = {
    QDRANT_PROGRAMS_COLLECTION: (
        1 + RETRIEVER_PROGRAM_MAX_RETRIES
    ),
    QDRANT_EXERCISES_COLLECTION: (
        1 + RETRIEVER_EXERCISE_MAX_RETRIES
    ),
}

_COLLECTIONS = tuple(MAX_SEARCH_ATTEMPTS)


# --------------------------------------------------
# Per-request search counters
# --------------------------------------------------

_search_lock = Lock()

_search_counts: dict[str, dict[str, int]] = {}


def _request_id(
    config: RunnableConfig | None,
) -> str:

    configurable = (
        (config or {}).get("configurable") or {}
    )

    return str(
        configurable.get(
            "retriever_request_id",
            "",
        )
    )


def _acquire_search_slot(
    request_id: str,
    collection: str,
) -> tuple[bool, int, int]:

    with _search_lock:

        counts = _search_counts.setdefault(
            request_id,
            {
                name: 0
                for name in _COLLECTIONS
            },
        )

        maximum = MAX_SEARCH_ATTEMPTS[collection]
        current = counts[collection]

        if current >= maximum:
            return False, current, 0

        counts[collection] += 1

        attempt = counts[collection]
        remaining = maximum - attempt

        return True, attempt, remaining


def _release_search_budget(
    request_id: str,
) -> None:

    with _search_lock:
        _search_counts.pop(request_id, None)


# --------------------------------------------------
# JSON helpers
# --------------------------------------------------

def _parse_json(value: Any) -> Any:

    if isinstance(value, (dict, list)):
        return value

    if not isinstance(value, str):
        raise ValueError(
            "Expected JSON string, dictionary, or list."
        )

    text = value.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    try:
        return json.loads(text)

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON input: {exc}"
        ) from exc


def _parse_chunks(
    chunks: Any,
) -> list[dict[str, Any]]:

    parsed = _parse_json(chunks)

    if isinstance(parsed, dict):
        parsed = parsed.get(
            "chunks",
            parsed.get("results", []),
        )

    if not isinstance(parsed, list):
        raise ValueError(
            "Chunks must be a JSON array."
        )

    return [
        chunk
        for chunk in parsed
        if isinstance(chunk, dict)
    ]


def _tool_input_error(
    exc: Exception,
) -> str:

    return (
        json.dumps({"error": f"{type(exc).__name__}: {exc}"})
    )


def _coerce_list(value: Any) -> list[Any]:

    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    return [value]


# --------------------------------------------------
# Qdrant result formatting
# --------------------------------------------------

_KEEP = (
    "goal",
    "level",
    "equipment",
    "program_length_weeks",
    "time_per_workout_min",
    "sets_median",
    "reps_median",
    "is_time_based",
    "source_id",
    "program_id",
    "exercise_id",
)


def _to_dict(chunk: Any) -> dict[str, Any] | None:
    if isinstance(chunk, dict):
        return chunk
    if hasattr(chunk, "model_dump"):      # pydantic v2
        return chunk.model_dump()
    if hasattr(chunk, "dict"):            # pydantic v1
        return chunk.dict()
    if is_dataclass(chunk):
        return asdict(chunk)
    return None

def _slim(
    chunks: Any,
    collection: str,
    text_chars: int,
) -> list[dict[str, Any]]:

    results = []

    for chunk in _coerce_list(chunks):

        chunk = _to_dict(chunk)
        if chunk is None:
            continue

        metadata = chunk.get("metadata") or {}

        if not isinstance(metadata, dict):
            metadata = {}

        result = {
            key: metadata[key]
            for key in _KEEP
            if key in metadata
        }

        for key in _KEEP:
            if key in chunk and key not in result:
                result[key] = chunk[key]

        result["title"] = (
            chunk.get("title")
            or metadata.get("title")
            or metadata.get("name")
            or "Untitled"
        )

        result["collection"] = collection

        result["score"] = chunk.get(
            "score",
            0.0,
        )

        text = (
            chunk.get("text")
            or chunk.get("page_content")
            or chunk.get("content")
            or ""
        )

        result["text"] = str(text)[:text_chars]

        results.append(result)

    return results


# --------------------------------------------------
# Shared search implementation
# --------------------------------------------------

def _search_response(
    *,
    request_id: str,
    query: str,
    collection: str,
    goal: str | None,
    level: str | None,
    equipment: str | None,
    top_k: int,
    text_chars: int,
) -> dict[str, Any]:

    if not request_id:
        return {
            "error": (
                "Missing retriever_request_id "
                "in runnable config."
            ),
            "collection": collection,
            "chunks": [],
        }

    allowed, attempt, remaining = (
        _acquire_search_slot(
            request_id,
            collection,
        )
    )

    if not allowed:
        return {
            "subquery": query,
            "collection": collection,
            "attempt": attempt,
            "remaining_searches": 0,
            "search_limit_reached": True,
            "chunks": [],
            "message": (
                f"Search limit reached for {collection}. "
                "Do not search this collection again. "
                "Use the best previously retrieved chunks."
            ),
        }

    filters = {
        key: value
        for key, value in {
            "goal": goal,
            "level": level,
            "equipment": equipment,
        }.items()
        if value is not None
    }

    try:
        embedding = embed_one(query)

        chunks = qdrant.search(
            collection=collection,
            query_vector=embedding,
            top_k=max(1, min(int(top_k), MAX_TOP_K)),
            goal=[goal] if goal else None,
            level=[level] if level else None,
            equipment=[equipment] if equipment else None,
        )
        result = {
            "subquery": query,
            "collection": collection,
            "attempt": attempt,
            "remaining_searches": remaining,
            "search_limit_reached": (
                remaining == 0
            ),
            "chunks": _slim(
                chunks,
                collection,
                text_chars,
            ),
        }

        if remaining == 0:
            result["message"] = (
                f"No more searches are allowed "
                f"for {collection}. "
                "Use the best retrieved evidence "
                "and finalize this collection."
            )

        return result

    except Exception as exc:
        return {
            "subquery": query,
            "collection": collection,
            "attempt": attempt,
            "remaining_searches": remaining,
            "search_limit_reached": (
                remaining == 0
            ),
            "chunks": [],
            "error": (
                f"{type(exc).__name__}: {exc}"
            ),
        }


# --------------------------------------------------
# Query decomposition tool
# --------------------------------------------------

@tool
def decompose_query(
    request: str,
) -> str:
    """Decompose a fitness request into retrieval needs."""

    try:
        needs = decompose(request, trainee_context={})

        if isinstance(needs, str):
            needs = _parse_json(needs)

        if isinstance(needs, dict):
            needs = needs.get("needs", [])

        output = []

        for need in _coerce_list(needs)[:4]:

            if hasattr(need, "model_dump"):
                data = need.model_dump()

            elif is_dataclass(need):
                data = asdict(need)

            elif isinstance(need, dict):
                data = dict(need)

            else:
                continue

            data["top_k"] = max(
                1,
                min(
                    int(data.get("top_k", 3)),
                    MAX_TOP_K,
                ),
            )

            output.append(data)

        return json.dumps(
            output,
            ensure_ascii=False,
        )

    except Exception as exc:
        return _tool_input_error(exc)


# --------------------------------------------------
# Program search tool
# --------------------------------------------------

@tool
def search_programs(
    query: str,
    goal: str | None = None,
    level: str | None = None,
    equipment: str | None = None,
    top_k: int = 3,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """
    Search fitness program summaries.

    The first search is always allowed.
    Additional searches are limited by
    RETRIEVER_PROGRAM_MAX_RETRIES.

    Retry only when previously retrieved
    evidence is insufficient.
    """

    return _search_response(
        request_id=_request_id(config),
        query=query,
        collection=QDRANT_PROGRAMS_COLLECTION,
        goal=goal,
        level=level,
        equipment=equipment,
        top_k=top_k,
        text_chars=250,
    )


# --------------------------------------------------
# Exercise search tool
# --------------------------------------------------

@tool
def search_exercises(
    query: str,
    goal: str | None = None,
    level: str | None = None,
    equipment: str | None = None,
    top_k: int = 3,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """
    Search individual fitness exercises.

    The first search is always allowed.
    Additional searches are limited by
    RETRIEVER_EXERCISE_MAX_RETRIES.

    Retry only when previously retrieved
    evidence is insufficient.
    """

    return _search_response(
        request_id=_request_id(config),
        query=query,
        collection=QDRANT_EXERCISES_COLLECTION,
        goal=goal,
        level=level,
        equipment=equipment,
        top_k=top_k,
        text_chars=150,
    )


# --------------------------------------------------
# Query rewriting tool
# --------------------------------------------------

@tool
def rewrite_search_query(
    query: str,
    reason: str = "",
) -> str:
    """Rewrite an unsuccessful fitness retrieval query."""

    try:
        result = rewrite_query(
            Need(description=f"{query}. Retry reason: {reason}",
                 query_text=query, collection=QDRANT_PROGRAMS_COLLECTION),
            [],
        )

        if hasattr(result, "model_dump"):
            result = result.model_dump()

        if isinstance(result, (dict, list)):
            return json.dumps(
                result,
                ensure_ascii=False,
            )

        return str(result)

    except Exception as exc:
        return _tool_input_error(exc)


# --------------------------------------------------
# Relevance validation tool
# --------------------------------------------------

@tool
def validate_chunk_relevance(
    query: str,
    chunks: str,
) -> str:
    """Validate the relevance of retrieved chunks."""

    try:
        parsed_chunks = _parse_chunks(chunks)

        result = {"relevant": validate_relevance(
            Need(description=query, query_text=query,
                 collection=QDRANT_PROGRAMS_COLLECTION),
            parsed_chunks,
        )}

        if hasattr(result, "model_dump"):
            result = result.model_dump()

        if isinstance(result, (dict, list)):
            return json.dumps(
                result,
                ensure_ascii=False,
            )

        return str(result)

    except Exception as exc:
        return _tool_input_error(exc)


# --------------------------------------------------
# Retrieval coverage tool
# --------------------------------------------------

@tool
def check_retrieval_coverage(
    request: str,
    chunks: str,
) -> str:
    """Check whether the retrieved evidence covers the request."""

    try:
        parsed_chunks = _parse_chunks(chunks)

        result = asdict(check_coverage(
            request,
            [Need(description=request, query_text=request,
                  collection=QDRANT_PROGRAMS_COLLECTION)],
            parsed_chunks,
        ))

        if hasattr(result, "model_dump"):
            result = result.model_dump()

        if isinstance(result, (dict, list)):
            return json.dumps(
                result,
                ensure_ascii=False,
            )

        return str(result)

    except Exception as exc:
        return _tool_input_error(exc)


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
# Build Retriever DeepAgent
# --------------------------------------------------

def build_retriever_agent() -> CompiledStateGraph:

    retry_instructions = f"""

## Collection-specific search retry budgets

- fitness_programs:
  Maximum {RETRIEVER_PROGRAM_MAX_RETRIES}
  additional searches after the first search.

- fitness_exercises:
  Maximum {RETRIEVER_EXERCISE_MAX_RETRIES}
  additional searches after the first search.

These limits are independent.

For each collection:
1. Perform the initial search.
2. Inspect and validate the returned evidence.
3. If relevant, accept the results and stop searching
   that collection.
4. If insufficient, rewrite the query and search again.
5. Continue only while searches remain.
6. When the limit is reached, use the best available
   evidence and stop searching that collection.

Do not retry merely because retries remain.

The search tools enforce these limits.

Any older global search ceiling mentioned elsewhere
in the prompt is superseded by these limits.

After both collections are handled, return the final
JSON array with the best retrieved chunks.

Do not write files.
"""

    return create_deep_agent(
        model=get_model(),
        tools=RETRIEVER_TOOLS,
        system_prompt=(
            _SYSTEM_PROMPT
            + "\n"
            + retry_instructions
        ),
        backend=FilesystemBackend(
            root_dir=str(_PROJECT_ROOT),
            virtual_mode=True,
        ),
        # skills=[_SKILLS_DIR],
        name="retriever",
    )


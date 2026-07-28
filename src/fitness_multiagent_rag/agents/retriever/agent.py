from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

_SRC_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_SRC_DIR))

from langchain_core.tools import tool
from langgraph.graph.state import CompiledStateGraph
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend


def _coerce_list(val) -> list[str] | None:
    """Accept list[str], JSON-encoded list string, or plain string — always return list or None."""
    if val is None:
        return None
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else [parsed]
        except (json.JSONDecodeError, ValueError):
            return [val]
    return [str(val)]

from config.settings import (
    QDRANT_PROGRAMS_COLLECTION,
    QDRANT_EXERCISES_COLLECTION,
    RETRIEVER_STEP_CEILING,
)
from fitness_multiagent_rag.llm.model import get_model
from fitness_multiagent_rag.utils.prompt_loader import load_agent_prompt
from fitness_multiagent_rag.vectorstore.embeddings import embed_one
from fitness_multiagent_rag.vectorstore import qdrant_client as qdrant
from .query_rewrite import Need, decompose, rewrite_query
from .coverage import validate_relevance, check_coverage

_AGENT_DIR    = Path(__file__).parent
_PROJECT_ROOT = _AGENT_DIR.parent.parent.parent.parent  # → Fitness_multiagent_RAG_project/
_SKILLS_DIR   = "/src/fitness_multiagent_rag/agents/retriever/skills"
_SYSTEM_PROMPT = load_agent_prompt(_AGENT_DIR, "system_prompt.md")

# ---------------------------------------------------------------------------
# Tools — the LLM calls these to drive the retrieval loop
# ---------------------------------------------------------------------------

@tool
def search_programs(
    query: str,
    goal: list[str] | str | None = None,
    level: list[str] | str | None = None,
    equipment: list[str] | str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """Search the fitness_programs collection for full workout programs and training splits.
    Embeds the query and runs a vector search with optional slot filters.
    Returns a ranked list of matching chunks with score, title, and text."""
    vector = embed_one(query)
    return qdrant.search(
        collection=QDRANT_PROGRAMS_COLLECTION,
        query_vector=vector,
        top_k=top_k,
        goal=_coerce_list(goal),
        level=_coerce_list(level),
        equipment=_coerce_list(equipment),
    )


@tool
def search_exercises(
    query: str,
    goal: list[str] | str | None = None,
    level: list[str] | str | None = None,
    equipment: list[str] | str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """Search the fitness_exercises collection for individual exercises, movements, and substitutions.
    Embeds the query and runs a vector search with optional slot filters.
    Returns a ranked list of matching chunks with score, title, and text."""
    vector = embed_one(query)
    return qdrant.search(
        collection=QDRANT_EXERCISES_COLLECTION,
        query_vector=vector,
        top_k=top_k,
        goal=_coerce_list(goal),
        level=_coerce_list(level),
        equipment=_coerce_list(equipment),
    )


@tool
def decompose_query(query: str, trainee_context_json: str) -> str:
    """Break a retrieval request into 1–4 distinct search needs.
    trainee_context_json: JSON string with keys goal, equipment, fitness_level, duration_weeks.
    Returns a JSON list of need objects (description, query_text, collection, filters, top_k)."""
    context = json.loads(trainee_context_json) if trainee_context_json else {}
    needs   = decompose(query, context)
    return json.dumps([
        {
            "description": n.description,
            "query_text":  n.query_text,
            "collection":  n.collection,
            "goal":        n.goal,
            "level":       n.level,
            "equipment":   n.equipment,
            "top_k":       n.top_k,
        }
        for n in needs
    ])


@tool
def rewrite_search_query(need_description: str, original_query: str, poor_chunks_json: str) -> str:
    """Produce improved sub-queries when initial search results were poor or irrelevant.
    poor_chunks_json: JSON list of the chunks returned by the failed search.
    Returns a JSON list of sub-query strings — the model decides how many are needed."""
    poor_chunks = json.loads(poor_chunks_json) if poor_chunks_json else []
    need = Need(
        description=need_description,
        query_text=original_query,
        collection=QDRANT_PROGRAMS_COLLECTION,
    )
    sub_queries = rewrite_query(need, poor_chunks)
    return json.dumps(sub_queries)


@tool
def validate_chunk_relevance(need_description: str, chunks_json: str) -> bool:
    """Check whether retrieved chunks adequately satisfy a specific retrieval need.
    chunks_json: JSON list of chunk dicts returned from search_programs or search_exercises.
    Returns true if the chunks are relevant and sufficient, false otherwise."""
    chunks = json.loads(chunks_json) if chunks_json else []
    need   = Need(
        description=need_description,
        query_text=need_description,
        collection=QDRANT_PROGRAMS_COLLECTION,
    )
    return validate_relevance(need, chunks)


@tool
def check_retrieval_coverage(
    original_query: str,
    needs_json: str,
    pool_json: str,
) -> str:
    """Check whether the full retrieval pool covers all identified needs.
    needs_json: JSON list of need description strings.
    pool_json: JSON list of all retrieved chunks accumulated so far.
    Returns JSON with keys: satisfied (list), gaps (list), confident (bool)."""
    needs_descs = json.loads(needs_json) if needs_json else []
    pool        = json.loads(pool_json)  if pool_json  else []

    needs = [
        Need(description=d, query_text=d, collection=QDRANT_PROGRAMS_COLLECTION)
        for d in needs_descs
    ]
    result = check_coverage(original_query, needs, pool)
    return json.dumps({
        "satisfied": result.satisfied,
        "gaps":      result.gaps,
        "confident": result.confident,
    })


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

RETRIEVER_TOOLS = [
    decompose_query,
    search_programs,
    search_exercises,
    rewrite_search_query,
    validate_chunk_relevance,
    check_retrieval_coverage,
]


def build_retriever_agent() -> CompiledStateGraph:
    """Build and return the compiled Retriever deepagent."""
    backend = FilesystemBackend(root_dir=str(_PROJECT_ROOT), virtual_mode=True)
    return create_deep_agent(
        model=get_model(),
        tools=RETRIEVER_TOOLS,
        system_prompt=_SYSTEM_PROMPT,
        backend=backend,
        skills=[_SKILLS_DIR],
        name="retriever",
    )

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent.parent))

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from fitness_multiagent_rag.llm.client import structured_chat
from fitness_multiagent_rag.utils.prompt_loader import load_agent_prompt

_AGENT_DIR      = Path(__file__).parent
_SYSTEM_PROMPT  = load_agent_prompt(_AGENT_DIR, "system_prompt.md")
_DECOMPOSE_TMPL = load_agent_prompt(_AGENT_DIR, "query_decomposition.md")


# ---------------------------------------------------------------------------
# Pydantic schemas for LLM output validation
# ---------------------------------------------------------------------------

class NeedSchema(BaseModel):
    description: str
    query_text:  str
    collection:  str                              = "fitness_programs"
    goal:        Optional[list[str]]              = None
    level:       Optional[list[str]]              = None
    equipment:   Optional[list[str]]              = None
    top_k:       int                              = Field(default=5, ge=5, le=15)


class DecomposeOutput(BaseModel):
    needs: list[NeedSchema] = Field(max_length=4)


class RewriteOutput(BaseModel):
    sub_queries: list[str] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Runtime Need dataclass (tracks satisfaction state during the loop)
# ---------------------------------------------------------------------------

@dataclass
class Need:
    description: str
    query_text:  str
    collection:  str
    goal:        Optional[list[str]]      = None
    level:       Optional[list[str]]      = None
    equipment:   Optional[list[str]]      = None
    top_k:       int                      = 5
    satisfied:   bool                     = False

    @classmethod
    def from_schema(cls, s: NeedSchema) -> "Need":
        return cls(
            description=s.description,
            query_text=s.query_text,
            collection=s.collection,
            goal=s.goal,
            level=s.level,
            equipment=s.equipment,
            top_k=s.top_k,
        )


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def decompose(query: str, trainee_context: dict) -> list[Need]:
    """Ask the LLM to break the query into 1–4 distinct retrieval needs."""
    context_str = "\n".join(f"- {k}: {v}" for k, v in trainee_context.items() if v)

    prompt = (
        _DECOMPOSE_TMPL
        .replace("{query}", query)
        .replace("{trainee_context}", context_str or "(no context provided)")
    )

    output: DecomposeOutput = structured_chat(
        [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)],
        DecomposeOutput,
    )
    return [Need.from_schema(n) for n in output.needs]


def rewrite_query(need: Need, poor_chunks: list[dict]) -> list[str]:
    """
    Ask the LLM to produce one or more better sub-queries when initial results were poor.
    The model decides how many — the caller enforces RETRIEVER_STEP_CEILING.
    """
    chunks_summary = "\n".join(
        f"- [{c.get('title', '?')}] {c.get('text', '')[:150]}"
        for c in poor_chunks[:3]
    )

    prompt = (
        f"A search query returned poor or irrelevant results for the following need.\n\n"
        f"Need: {need.description}\n"
        f"Original query: {need.query_text}\n\n"
        f"Poor results:\n{chunks_summary or '(no results returned)'}\n\n"
        f"Produce one or more improved sub-queries that together would better cover this need. "
        f"If the need is broad, split it into focused sub-queries. "
        f"If it just needs rephrasing, return a single better query."
    )

    output: RewriteOutput = structured_chat(
        [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)],
        RewriteOutput,
    )
    return output.sub_queries

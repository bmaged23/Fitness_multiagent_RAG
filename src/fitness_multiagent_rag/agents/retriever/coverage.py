from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent.parent))

from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage

from fitness_multiagent_rag.llm.client import structured_chat, chat
from fitness_multiagent_rag.utils.prompt_loader import load_agent_prompt
from .query_rewrite import Need

_AGENT_DIR     = Path(__file__).parent
_SYSTEM_PROMPT = load_agent_prompt(_AGENT_DIR, "system_prompt.md")
_COVERAGE_TMPL = load_agent_prompt(_AGENT_DIR, "coverage_check.md")


# ---------------------------------------------------------------------------
# Pydantic schemas for LLM output validation
# ---------------------------------------------------------------------------

class RelevanceOutput(BaseModel):
    relevant: bool


class CoverageOutput(BaseModel):
    satisfied: list[str]
    gaps:      list[str]
    confident: bool


# ---------------------------------------------------------------------------
# Runtime result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CoverageResult:
    satisfied: list[str] = field(default_factory=list)
    gaps:      list[str] = field(default_factory=list)
    confident: bool      = False


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def validate_relevance(need: Need, chunks: list[dict]) -> bool:
    """Return True if the chunks adequately answer this specific need."""
    if not chunks:
        return False

    chunks_text = "\n\n".join(
        f"[{c.get('title', '?')}] {c.get('text', '')[:300]}"
        for c in chunks[:5]
    )

    prompt = (
        f"You are validating search results for a fitness retrieval system.\n\n"
        f"IMPORTANT: The fitness_programs collection stores PROGRAM SUMMARIES — title, goal, "
        f"level, equipment, duration, and a short description. They do NOT contain full exercise "
        f"schedules or day-by-day plans. This is the expected data format. Do NOT mark chunks as "
        f"irrelevant just because they lack detailed schedules.\n\n"
        f"Retrieval need: {need.description}\n\n"
        f"Retrieved chunks:\n{chunks_text}\n\n"
        f"Are these chunks topically relevant to the retrieval need?\n"
        f"Answer TRUE if: goal/level/equipment metadata aligns with the need AND the text is "
        f"about the right type of training.\n"
        f"Answer FALSE only if the chunks are clearly off-topic: wrong goal, wrong equipment, "
        f"or completely different training domain."
    )

    output: RelevanceOutput = structured_chat(
        [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)],
        RelevanceOutput,
    )
    return output.relevant


def check_coverage(
    original_query: str,
    needs: list[Need],
    pool: list[dict],
) -> CoverageResult:
    """Check whether the full retrieval pool covers all identified needs."""
    if not pool:
        return CoverageResult(
            gaps=[n.description for n in needs],
            confident=False,
        )

    needs_text  = "\n".join(f"- {n.description}" for n in needs)
    chunks_text = "\n\n".join(
        f"[{c.get('title', '?')}] {c.get('text', '')[:200]}"
        for c in pool[:12]
    )

    prompt = (
        _COVERAGE_TMPL
        .replace("{original_query}", original_query)
        .replace("{needs}", needs_text)
        .replace("{chunks_text}", chunks_text)
    )

    output: CoverageOutput = structured_chat(
        [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)],
        CoverageOutput,
    )

    return CoverageResult(
        satisfied=output.satisfied,
        gaps=output.gaps,
        confident=output.confident,
    )

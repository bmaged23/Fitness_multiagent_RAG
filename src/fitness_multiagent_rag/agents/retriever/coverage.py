
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent.parent.parent.parent.parent.parent),
)

from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage

from fitness_multiagent_rag.llm.client import structured_chat
from fitness_multiagent_rag.utils.prompt_loader import load_agent_prompt
from .query_rewrite import Need


# --------------------------------------------------
# Configuration
# --------------------------------------------------

_AGENT_DIR = Path(__file__).parent

_COVERAGE_TMPL = load_agent_prompt(
    _AGENT_DIR,
    "coverage_check.md",
)


# --------------------------------------------------
# Pydantic output schemas
# --------------------------------------------------

class RelevanceOutput(BaseModel):
    relevant: bool


class CoverageOutput(BaseModel):
    satisfied: list[str]
    gaps: list[str]
    confident: bool


# --------------------------------------------------
# Runtime result
# --------------------------------------------------

@dataclass
class CoverageResult:
    satisfied: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    confident: bool = False


# --------------------------------------------------
# Relevance validation
# --------------------------------------------------

def validate_relevance(
    need: Need,
    chunks: list[dict],
) -> bool:
    """Return True if the chunks are relevant to the retrieval need."""

    if not chunks:
        return False

    # Limit content to reduce input tokens.
    chunks_text = "\n\n".join(
        f"[{c.get('title', '?')}] "
        f"{str(c.get('text') or '')[:300]}"
        for c in chunks[:5]
    )

    system_prompt = (
        "You are a fitness retrieval relevance classifier. "
        "Evaluate whether retrieved fitness documents match "
        "the requested training goal, fitness level, "
        "equipment, and training type. "
        "Fitness program summaries do not necessarily "
        "contain complete workout schedules. "
        "Return only a valid JSON object with the boolean "
        'field "relevant". '
        'Example: {"relevant": true}. '
        "Do not include Markdown, explanations, or "
        "plain TRUE/FALSE."
    )

    prompt = (
        "Evaluate the following retrieved fitness documents.\n\n"

        f"Retrieval need:\n{need.description}\n\n"

        f"Retrieved chunks:\n{chunks_text}\n\n"

        "Relevance rules:\n"
        "1. Check whether the training goal matches.\n"
        "2. Check whether the fitness level matches.\n"
        "3. Check whether the available equipment matches.\n"
        "4. Check whether the documents concern the requested "
        "type of training.\n"
        "5. Do not reject program summaries merely because "
        "they lack detailed exercise schedules.\n\n"

        "Return relevant=true if the chunks are topically "
        "appropriate for the retrieval need.\n"
        "Return relevant=false if the chunks are clearly "
        "off-topic.\n\n"

        "Required JSON output:\n"
        '{"relevant": true}\n\n'

        "Replace true with false when appropriate. "
        "Return only the JSON object."
    )

    output: RelevanceOutput = structured_chat(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ],
        RelevanceOutput,
    )

    return output.relevant


# --------------------------------------------------
# Coverage validation
# --------------------------------------------------

def check_coverage(
    original_query: str,
    needs: list[Need],
    pool: list[dict],
) -> CoverageResult:
    """Check whether retrieved chunks cover all search needs."""

    if not pool:
        return CoverageResult(
            gaps=[n.description for n in needs],
            confident=False,
        )

    needs_text = "\n".join(
        f"- {n.description}"
        for n in needs
    )

    # Limit chunks and text size to control prompt length.
    chunks_text = "\n\n".join(
        f"[{c.get('title', '?')}] "
        f"{str(c.get('text') or '')[:200]}"
        for c in pool[:12]
    )

    prompt = (
        _COVERAGE_TMPL
        .replace("{original_query}", original_query)
        .replace("{needs}", needs_text)
        .replace("{chunks_text}", chunks_text)
    )

    system_prompt = (
        "You are a fitness retrieval coverage evaluator. "
        "Determine which retrieval needs are supported "
        "by the available evidence and which are missing. "
        "Fitness program summaries do not need complete "
        "day-by-day workout schedules. "
        "Return only a valid JSON object with these fields: "
        '"satisfied" (list of strings), '
        '"gaps" (list of strings), '
        '"confident" (boolean). '
        "Do not include Markdown or explanations."
    )

    prompt += (
        "\n\nRequired JSON output format:\n"
        '{"satisfied": ["example satisfied need"], '
        '"gaps": ["example missing need"], '
        '"confident": false}\n\n'
        "Use the actual retrieval needs and evidence. "
        "Return only the JSON object."
    )

    output: CoverageOutput = structured_chat(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ],
        CoverageOutput,
    )

    return CoverageResult(
        satisfied=output.satisfied,
        gaps=output.gaps,
        confident=output.confident,
    )


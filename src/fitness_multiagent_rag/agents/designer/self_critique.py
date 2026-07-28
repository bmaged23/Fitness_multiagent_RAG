from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from fitness_multiagent_rag.llm.client import structured_chat
from fitness_multiagent_rag.schemas.plan_schema import Exercise, PlanSchema
from fitness_multiagent_rag.db.models import Trainee
from fitness_multiagent_rag.utils.prompt_loader import load_agent_prompt

_AGENT_DIR  = Path(__file__).parent
_SYS_PROMPT = load_agent_prompt(_AGENT_DIR, "system_prompt.md")
_TMPL       = load_agent_prompt(_AGENT_DIR, "self_critique_prompts.md")


# ── What the LLM outputs — only the changes, not the full plan ───────────────

class ExerciseChange(BaseModel):
    week: int
    day: int
    original_name: str           # exercise to find (case-insensitive partial match)
    action: Literal["remove", "replace"]
    replacement: Exercise | None = None   # required when action=="replace"
    reason: str


class _CritiqueLLMOutput(BaseModel):
    changed: bool
    critique_notes: str          # 1–3 sentences max
    changes: list[ExerciseChange] = Field(default_factory=list)


# ── Public interface — same shape as before so agent.py needs no changes ─────

class CritiqueOutput(BaseModel):
    changed: bool
    critique_notes: str
    plan_json: PlanSchema


# ── Helpers ───────────────────────────────────────────────────────────────────

def _apply_changes(plan: dict, changes: list[ExerciseChange]) -> dict:
    """Apply ExerciseChange list to a plan dict in-place (on a deep copy)."""
    result = copy.deepcopy(plan)
    weeks  = result.get("weeks", [])
    for ch in changes:
        w_idx = ch.week - 1
        d_idx = ch.day - 1
        if w_idx < 0 or w_idx >= len(weeks):
            continue
        days = weeks[w_idx].get("days", [])
        if d_idx < 0 or d_idx >= len(days):
            continue
        exercises = days[d_idx].get("exercises", [])
        # Case-insensitive partial name match
        idx = next(
            (i for i, ex in enumerate(exercises)
             if ch.original_name.lower() in ex.get("name", "").lower()),
            None,
        )
        if idx is None:
            continue
        if ch.action == "remove":
            exercises.pop(idx)
        elif ch.action == "replace" and ch.replacement is not None:
            exercises[idx] = ch.replacement.model_dump()
    return result


def critique_plan(
    plan: dict,
    trainee: Trainee,
    source_chunks: list[dict],
) -> CritiqueOutput:
    """LLM coherence pass — receives and returns only the 2-week template.
    Changes are applied programmatically so the LLM never re-outputs the full plan.
    """
    source_summary = "\n".join(
        f"- {c.get('title', '?')} "
        f"(goal: {c.get('goal', '?')}, level: {c.get('level', '?')})"
        for c in source_chunks[:6]
        if c.get("collection") == "fitness_programs"
    ) or "(no program summaries in source)"

    prompt = (
        _TMPL
        .replace(
            "{trainee_context}",
            f"Goal: {trainee.goal} | Level: {trainee.fitness_level} | "
            f"Equipment: {', '.join(trainee.equipment_available or [])}",
        )
        .replace("{injuries_text}", trainee.injuries_limitations or "none")
        .replace("{source_chunks_summary}", source_summary)
        .replace("{plan_json}", json.dumps(plan, indent=2))
    )

    llm_out = structured_chat(
        [SystemMessage(content=_SYS_PROMPT), HumanMessage(content=prompt)],
        _CritiqueLLMOutput,
    )

    updated_plan = _apply_changes(plan, llm_out.changes) if llm_out.changed else plan
    return CritiqueOutput(
        changed=llm_out.changed,
        critique_notes=llm_out.critique_notes,
        plan_json=PlanSchema.model_validate(updated_plan),
    )

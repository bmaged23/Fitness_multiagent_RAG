from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage

from fitness_multiagent_rag.llm.client import structured_chat
from fitness_multiagent_rag.schemas.plan_schema import PlanSchema, Week, Day, Exercise
from fitness_multiagent_rag.schemas.program_structure import ProgramStructure
from fitness_multiagent_rag.db.models import Trainee
from fitness_multiagent_rag.utils.prompt_loader import load_agent_prompt

_AGENT_DIR    = Path(__file__).parent
_SYS_PROMPT   = load_agent_prompt(_AGENT_DIR, "system_prompt.md")
_STRUCT_TMPL  = load_agent_prompt(_AGENT_DIR, "structure_proposal_prompts.md")
_WEEK_TMPL    = load_agent_prompt(_AGENT_DIR, "week_synthesis_prompts.md")
_SYNTH_TMPL   = load_agent_prompt(_AGENT_DIR, "synthesis_prompts.md")
_REV_TMPL     = load_agent_prompt(_AGENT_DIR, "revision_prompts.md")


class PatchOutput(BaseModel):
    needs_rebuild: bool
    change_description: str
    plan_json: PlanSchema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trainee_str(trainee: Trainee) -> str:
    return (
        f"Goal: {trainee.goal or 'not specified'}\n"
        f"Fitness level: {trainee.fitness_level or 'not specified'}\n"
        f"Equipment: {', '.join(trainee.equipment_available or ['not specified'])}\n"
        f"Injuries/limitations: {trainee.injuries_limitations or 'none'}\n"
        f"Age: {trainee.age or 'N/A'} | Gender: {trainee.gender or 'N/A'}"
    )


def _fmt_programs(chunks: list[dict]) -> str:
    progs = [c for c in chunks if c.get("collection") == "fitness_programs"]
    if not progs:
        return "(no program summaries retrieved)"
    return "\n\n".join(
        f"[{c.get('title', '?')}]\n"
        f"Goal: {c.get('goal', '?')} | Level: {c.get('level', '?')} | "
        f"Equipment: {c.get('equipment', '?')} | "
        f"Duration: {c.get('program_length_weeks', '?')} weeks\n"
        f"{c.get('text', '')[:500]}"
        for c in progs[:6]
    )


def _fmt_exercises(chunks: list[dict]) -> str:
    exs = [c for c in chunks if c.get("collection") == "fitness_exercises"]
    if not exs:
        return "(no exercise options retrieved)"
    return "\n".join(
        f"- {c.get('title', '?')}: equipment={c.get('equipment', '?')} | "
        f"{c.get('text', '')[:120]}"
        for c in exs[:20]
    )


# ---------------------------------------------------------------------------
# Week expansion — programmatic progressive overload after 2-week LLM output
# ---------------------------------------------------------------------------

def _expand_to_duration(plan: PlanSchema) -> PlanSchema:
    """Expand a 2-week template to plan.duration_weeks with linear progressive overload.

    Every 2 weeks beyond the template: +1 rep per exercise.
    After 4 weeks beyond the template: +1 set per exercise (capped at 5).
    Rest days are preserved as-is.
    """
    template = plan.weeks[-1]  # use last generated week as rolling baseline
    all_weeks: list[Week] = list(plan.weeks)

    for w in range(len(all_weeks) + 1, plan.duration_weeks + 1):
        delta = w - len(plan.weeks)          # weeks past the template
        extra_reps = min(delta // 2, 4)      # +1 rep every 2 weeks, max +4
        extra_sets = 1 if delta >= 4 else 0  # +1 set after 4 extra weeks

        new_days: list[Day] = []
        for day in template.days:
            if day.rest_day:
                new_days.append(Day(day=day.day, focus=day.focus, rest_day=True, exercises=[]))
            else:
                new_days.append(Day(
                    day=day.day,
                    focus=day.focus,
                    rest_day=False,
                    exercises=[
                        Exercise(
                            name=ex.name,
                            sets=min(ex.sets + extra_sets, 5),
                            reps=ex.reps + extra_reps,
                            rest_seconds=ex.rest_seconds,
                            equipment=ex.equipment,
                            muscle_group=ex.muscle_group,
                            notes=ex.notes,
                        )
                        for ex in day.exercises
                    ],
                ))
        all_weeks.append(Week(week=w, days=new_days))

    return PlanSchema(
        goal=plan.goal,
        difficulty=plan.difficulty,
        duration_weeks=plan.duration_weeks,
        equipment_available=plan.equipment_available,
        weeks=all_weeks,
    )


# ---------------------------------------------------------------------------
# LLM calls — both return Pydantic models
# ---------------------------------------------------------------------------

def synthesize_plan(chunks: list[dict], trainee: Trainee, request_text: str) -> PlanSchema:
    """Build a new plan from retrieved chunks. Returns the 2-week template only.
    Expansion to full duration happens in save_plan after validation and critique.
    """
    prompt = (
        _SYNTH_TMPL
        .replace("{trainee_context}", _trainee_str(trainee))
        .replace("{request_text}", request_text)
        .replace("{program_chunks}", _fmt_programs(chunks))
        .replace("{exercise_chunks}", _fmt_exercises(chunks))
    )
    return structured_chat(
        [SystemMessage(content=_SYS_PROMPT), HumanMessage(content=prompt)],
        PlanSchema,
    )


def propose_structure(
    chunks: list[dict],
    trainee: Trainee,
    request_text: str,
) -> ProgramStructure:
    """Stage 1 — Generate only the training skeleton (no exercises).
    Compact output: split type, schedule, duration, rep style, rationale.
    """
    prompt = (
        _STRUCT_TMPL
        .replace("{trainee_context}", _trainee_str(trainee))
        .replace("{request_text}", request_text)
        .replace("{program_chunks}", _fmt_programs(chunks))
    )
    return structured_chat(
        [SystemMessage(content=_SYS_PROMPT), HumanMessage(content=prompt)],
        ProgramStructure,
    )


def build_week_one(
    structure: ProgramStructure,
    chunks: list[dict],
    trainee: Trainee,
    user_feedback: str = "",
) -> PlanSchema:
    """Stage 2 — Fill Week 1 exercises guided by the approved structure.
    Returns a PlanSchema with weeks=[Week 1 only]. save_plan expands to full duration.
    """
    schedule_lines = "\n".join(
        f"  Day {i + 1}: {label}"
        for i, label in enumerate(structure.day_schedule)
    )
    prompt = (
        _WEEK_TMPL
        .replace("{trainee_context}", _trainee_str(trainee))
        .replace("{split_type}", structure.split_type)
        .replace("{days_per_week}", str(structure.days_per_week))
        .replace("{rep_style}", structure.rep_style)
        .replace("{duration_weeks}", str(structure.duration_weeks))
        .replace("{day_schedule}", schedule_lines)
        .replace("{goal}", structure.goal)
        .replace("{difficulty}", structure.difficulty)
        .replace("{equipment}", ", ".join(structure.equipment_available))
        .replace("{injuries_text}", trainee.injuries_limitations or "none")
        .replace("{exercise_chunks}", _fmt_exercises(chunks))
        .replace("{user_feedback}", user_feedback or "none")
    )
    return structured_chat(
        [SystemMessage(content=_SYS_PROMPT), HumanMessage(content=prompt)],
        PlanSchema,
    )


def patch_plan(
    current_plan: dict,
    patch_instructions: str,
    chunks: list[dict],
    trainee: Trainee,
) -> PatchOutput:
    """Apply targeted edits to an existing plan. Returns a PatchOutput."""
    prompt = (
        _REV_TMPL
        .replace("{trainee_context}", _trainee_str(trainee))
        .replace("{current_plan_json}", json.dumps(current_plan, indent=2))
        .replace("{patch_instructions}", patch_instructions)
        .replace("{exercise_chunks}", _fmt_exercises(chunks))
    )
    return structured_chat(
        [SystemMessage(content=_SYS_PROMPT), HumanMessage(content=prompt)],
        PatchOutput,
    )

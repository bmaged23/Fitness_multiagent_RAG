from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage

from fitness_multiagent_rag.llm.client import structured_chat
from fitness_multiagent_rag.schemas.plan_schema import PlanSchema, ProgressionScheme, Week, Day, Exercise
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
# Progression helpers — computed deterministically, never from LLM output
# ---------------------------------------------------------------------------

def _default_deload_weeks(duration_weeks: int) -> list[int]:
    """Every 4th week is a deload, plus the final week if it isn't already one."""
    deloads = list(range(4, duration_weeks + 1, 4))
    if duration_weeks not in deloads:
        deloads.append(duration_weeks)
    return sorted(deloads)


def _default_weight_increment(difficulty: str) -> float:
    return {"Beginner": 2.5, "Novice": 2.5, "Intermediate": 1.25, "Advanced": 0.5}.get(difficulty, 2.0)


# ---------------------------------------------------------------------------
# Week expansion — programmatic progressive overload with deload weeks
# ---------------------------------------------------------------------------

def _expand_to_duration(plan: PlanSchema) -> PlanSchema:
    """Expand Week 1 to plan.duration_weeks applying progressive overload and deload weeks.

    Non-deload weeks:
      - Reps: +1 every 2 training weeks within a block (max +4 per block)
      - Sets: +1 after 5 training weeks in a block (capped at 5)
      - Notes: cumulative weight target vs Week 1

    Deload weeks (every 4th week + final week):
      - Sets: 60% of Week 1 (min 1)
      - Reps: Week 1 reps − 2 (min 1)
      - Notes: "Deload — use ~60% of usual weight, prioritise form and recovery."
      - Resets the block position counter for the next block
    """
    week1 = plan.weeks[0]
    deload_week_set = set(plan.progression.deload_weeks)
    weight_inc = plan.progression.weight_increment_kg_per_week

    all_weeks: list[Week] = [week1]
    block_pos = 1          # week 1 is position 1 in the first block
    training_weeks = 1     # total non-deload weeks so far

    for w in range(2, plan.duration_weeks + 1):
        if w in deload_week_set:
            new_days: list[Day] = []
            for day in week1.days:
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
                                sets=max(1, round(ex.sets * 0.6)),
                                reps=max(1, ex.reps - 2),
                                rest_seconds=ex.rest_seconds,
                                equipment=ex.equipment,
                                muscle_group=ex.muscle_group,
                                notes="Deload — use ~60% of usual weight, prioritise form and recovery.",
                            )
                            for ex in day.exercises
                        ],
                    ))
            all_weeks.append(Week(week=w, days=new_days))
            block_pos = 0   # reset; will be incremented to 1 on the next normal week
        else:
            block_pos += 1
            training_weeks += 1
            extra_reps = min((block_pos - 1) // 2, 4)   # +1 rep every 2 weeks in block
            extra_sets = 1 if block_pos > 5 else 0       # +1 set after 5 weeks in block
            cumulative_kg = weight_inc * (training_weeks - 1)
            weight_note = f"+{cumulative_kg:.1f}kg vs Week 1 target weight."

            new_days = []
            for day in week1.days:
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
                                notes=weight_note,
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
        progression=plan.progression,
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
    Deload weeks and weight increment are set programmatically after the LLM call.
    """
    prompt = (
        _STRUCT_TMPL
        .replace("{trainee_context}", _trainee_str(trainee))
        .replace("{request_text}", request_text)
        .replace("{program_chunks}", _fmt_programs(chunks))
    )
    structure = structured_chat(
        [SystemMessage(content=_SYS_PROMPT), HumanMessage(content=prompt)],
        ProgramStructure,
    )
    # Override progression fields — never trust LLM for these
    structure.deload_weeks = _default_deload_weeks(structure.duration_weeks)
    structure.weight_increment_kg_per_week = _default_weight_increment(structure.difficulty)
    return structure


def build_week_one(
    structure: ProgramStructure,
    chunks: list[dict],
    trainee: Trainee,
    user_feedback: str = "",
) -> PlanSchema:
    """Stage 2 — Fill Week 1 exercises guided by the approved structure.
    Returns a PlanSchema with weeks=[Week 1 only]. save_plan expands to full duration.
    Progression scheme is set programmatically from the structure after the LLM call.
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
    plan = structured_chat(
        [SystemMessage(content=_SYS_PROMPT), HumanMessage(content=prompt)],
        PlanSchema,
    )
    # Copy progression parameters from the approved structure (computed in Stage 1)
    plan.progression = ProgressionScheme(
        weight_increment_kg_per_week=structure.weight_increment_kg_per_week,
        deload_weeks=structure.deload_weeks,
    )
    return plan


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

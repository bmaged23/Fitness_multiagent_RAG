from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_SRC_DIR))
sys.path.insert(0, str(_SRC_DIR.parent))

from langchain_core.tools import tool
from langgraph.graph.state import CompiledStateGraph
from deepagents import CompiledSubAgent, create_deep_agent
from deepagents.backends import FilesystemBackend

from fitness_multiagent_rag.llm.model import get_model
from fitness_multiagent_rag.utils.prompt_loader import load_agent_prompt
from fitness_multiagent_rag.schemas.plan_schema import PlanSchema
from fitness_multiagent_rag.schemas.program_structure import ProgramStructure
from fitness_multiagent_rag.db import crud
from fitness_multiagent_rag.db.models import Plan, PlanRevision
from .synthesis import _expand_to_duration, build_week_one, patch_plan, propose_structure, synthesize_plan
from .validation import validate_structure
from .self_critique import critique_plan

_AGENT_DIR     = Path(__file__).parent
_PROJECT_ROOT  = _AGENT_DIR.parent.parent.parent.parent  # designer→agents→pkg→src→project_root
_SKILLS_DIR    = "/src/fitness_multiagent_rag/agents/designer/skills"
_SYSTEM_PROMPT = load_agent_prompt(_AGENT_DIR, "system_prompt.md")

_VALID_EQUIPMENT = {"Full Gym", "Garage Gym", "At Home", "Dumbbell Only"}
_VALID_GOALS = {
    "Bodybuilding", "Muscle & Sculpting", "Powerbuilding", "Athletics",
    "Powerlifting", "Bodyweight Fitness", "Olympic Weightlifting", "At-Home & Calisthenics",
}
_VALID_LEVELS = {"Beginner", "Novice", "Intermediate", "Advanced"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flatten_retriever_chunks(raw: str) -> list[dict]:
    """
    Parse the Retriever's JSON array output into a flat chunk list.
    Augments each chunk with 'collection' from its parent subquery entry.
    Handles both the Retriever's nested format and a pre-flattened list.
    """
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return []

    # Already flat (no 'chunks' key inside entries)
    if data and isinstance(data[0], dict) and "chunks" not in data[0]:
        return data

    chunks: list[dict] = []
    for entry in data:
        if not isinstance(entry, dict) or "chunks" not in entry:
            continue
        collection = entry.get("collection", "")
        for chunk in entry.get("chunks", []):
            chunk["collection"] = collection
            chunks.append(chunk)
    return chunks


def _plan_to_md(plan: dict, trainee_name: str = "") -> str:
    """Render a plan dict to compact markdown for plan.md in the virtual filesystem."""
    lines = [
        f"# Workout Plan{f' — {trainee_name}' if trainee_name else ''}",
        f"**Goal:** {plan.get('goal')}  ",
        f"**Difficulty:** {plan.get('difficulty')} | **Duration:** {plan.get('duration_weeks')} weeks  ",
        f"**Equipment:** {', '.join(plan.get('equipment_available', []))}",
        "",
    ]
    for week in plan.get("weeks", []):
        lines.append(f"## Week {week['week']}")
        for day in week.get("days", []):
            if day.get("rest_day"):
                lines.append(f"**Day {day['day']}:** REST")
            else:
                lines.append(f"**Day {day['day']} — {day.get('focus', '')}**")
                for ex in day.get("exercises", []):
                    reps = ex.get("reps", 0)
                    reps_str = f"{reps} reps" if reps > 0 else f"{abs(reps)}s"
                    lines.append(
                        f"  - {ex.get('name')}: {ex.get('sets')}×{reps_str} "
                        f"| rest {ex.get('rest_seconds')}s "
                        f"| {ex.get('equipment')} | {ex.get('muscle_group')}"
                    )
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools — each combines multiple operations, no thin single-function wrappers
# ---------------------------------------------------------------------------

@tool
def collect_missing_info(trainee_id: int, request_text: str) -> str:
    """Check whether the trainee profile has enough *valid* data to build a plan.
    Validates goal, fitness_level, and equipment against the allowed value sets —
    a non-empty field with an unrecognized value still triggers a question.
    ALWAYS call this first, before any retrieval or synthesis.
    Returns JSON: {ready: bool, questions: list[str]}
    If ready is false, return the questions to Coach immediately — do NOT proceed."""
    trainee = crud.get_trainee_by_id(trainee_id)
    if not trainee:
        return json.dumps({"ready": False, "questions": [f"Trainee id={trainee_id} not found."]})

    questions: list[str] = []

    # Goal — must be present and a recognized category
    if not trainee.goal:
        questions.append(
            "What is your main fitness goal? "
            "(Bodybuilding / Muscle & Sculpting / Powerbuilding / Athletics / "
            "Powerlifting / Bodyweight Fitness / Olympic Weightlifting / At-Home & Calisthenics)"
        )
    elif trainee.goal not in _VALID_GOALS:
        questions.append(
            f"Your profile goal '{trainee.goal}' needs to map to a training category. "
            "Which fits best? Bodybuilding / Muscle & Sculpting / Powerbuilding / Athletics / "
            "Powerlifting / Bodyweight Fitness / Olympic Weightlifting / At-Home & Calisthenics"
        )

    # Fitness level — must be present and a recognized value (exact case)
    level = (trainee.fitness_level or "").strip()
    if not level:
        questions.append(
            "What is your current fitness level? "
            "(Beginner / Novice / Intermediate / Advanced)"
        )
    elif level not in _VALID_LEVELS:
        questions.append(
            f"Your fitness level '{trainee.fitness_level}' isn't recognized. "
            "Please confirm: Beginner / Novice / Intermediate / Advanced"
        )

    # Equipment — must have at least one value that matches an allowed category
    valid_eq = [e for e in (trainee.equipment_available or []) if e in _VALID_EQUIPMENT]
    if not trainee.equipment_available:
        questions.append(
            "What equipment do you have access to? "
            "(Full Gym / Garage Gym / Dumbbell Only / At Home)"
        )
    elif not valid_eq:
        current = ", ".join(trainee.equipment_available)
        questions.append(
            f"Your equipment '{current}' doesn't match our categories. "
            "Please choose: Full Gym / Garage Gym / Dumbbell Only / At Home"
        )

    return json.dumps({"ready": len(questions) == 0, "questions": questions})


@tool
def update_trainee_profile(
    trainee_id: int,
    goal: str = "",
    fitness_level: str = "",
    equipment_available: str = "",
) -> str:
    """Persist validated profile fields to the DB after the user answers Stage 0 questions.

    Only pass fields that the user actually answered — leave others empty to keep existing values.
    Map natural-language answers to exact allowed values before calling this tool:
      goal: one of the 8 allowed goal strings
      fitness_level: Beginner / Novice / Intermediate / Advanced
      equipment_available: JSON array string, e.g. '["Dumbbell Only"]'

    Returns JSON: {updated: {field: new_value}, skipped: [reason, ...]}
    """
    trainee = crud.get_trainee_by_id(trainee_id)
    if not trainee:
        return json.dumps({"error": f"Trainee {trainee_id} not found"})

    updated: dict = {}
    skipped: list = []

    if goal:
        if goal in _VALID_GOALS:
            trainee.goal = goal
            updated["goal"] = goal
        else:
            skipped.append(f"goal '{goal}' not in allowed list — skipped")

    if fitness_level:
        level = fitness_level.strip().capitalize()
        if level in _VALID_LEVELS:
            trainee.fitness_level = level
            updated["fitness_level"] = level
        else:
            skipped.append(f"fitness_level '{fitness_level}' not in allowed list — skipped")

    if equipment_available:
        try:
            eq_list = json.loads(equipment_available)
        except Exception:
            eq_list = [equipment_available]
        valid_eq = [e for e in eq_list if e in _VALID_EQUIPMENT]
        if valid_eq:
            trainee.equipment_available = valid_eq
            updated["equipment_available"] = valid_eq
        else:
            skipped.append(f"equipment {eq_list} — none matched allowed values, skipped")

    if updated:
        crud.update_trainee(trainee)

    return json.dumps({"updated": updated, "skipped": skipped})


@tool
def load_context(trainee_id: int) -> str:
    """Load the trainee's full profile and current active plan from SQLite in one call.
    Returns JSON with keys: trainee (goal, fitness_level, equipment_available,
    injuries_limitations, age, gender) and active_plan (plan_id, plan_json) or null.
    Always call this first at the start of every Designer invocation."""
    trainee = crud.get_trainee_by_id(trainee_id)
    if not trainee:
        return json.dumps({"error": f"No trainee with id={trainee_id}"})

    active_plan = crud.get_active_plan(trainee_id)

    return json.dumps({
        "trainee": {
            "id":                   trainee.id,
            "name":                 trainee.name,
            "goal":                 trainee.goal,
            "fitness_level":        trainee.fitness_level,
            "equipment_available":  trainee.equipment_available,
            "injuries_limitations": trainee.injuries_limitations,
            "age":                  trainee.age,
            "gender":               trainee.gender,
        },
        "active_plan": {
            "plan_id":  active_plan.id,
            "plan_json": active_plan.plan_json,
        } if active_plan else None,
    })


@tool
def synthesize_new_plan(chunks_json: str, trainee_id: int, request_text: str) -> str:
    """Build a new workout plan from retrieved program summaries and exercise chunks.
    chunks_json: the Retriever's output — either its nested array format or a flat chunk list.
    Returns the synthesized plan as a JSON string matching PlanSchema.
    Always call validate_and_critique immediately after this tool."""
    trainee = crud.get_trainee_by_id(trainee_id)
    if not trainee:
        return json.dumps({"error": f"Trainee {trainee_id} not found"})

    chunks = _flatten_retriever_chunks(chunks_json)
    plan: PlanSchema = synthesize_plan(chunks, trainee, request_text)
    return plan.model_dump_json()


@tool
def validate_and_critique(
    plan_json: str,
    trainee_id: int,
    source_chunks_json: str,
    run_critique: bool,
) -> str:
    """Run structural validation then optionally an LLM self-critique pass.

    Structural checks (always, deterministic):
      - Equipment match: every exercise uses equipment the trainee actually has
      - Rest days: at least 1 per week (auto-fixed if missing)
      - Difficulty alignment: plan level within 1 step of trainee fitness_level

    Self-critique (only when run_critique=true):
      - Training split coherence, goal fit, injury constraint compliance, progression logic
      - Only call with run_critique=true when synthesizing from multiple source programs

    source_chunks_json: chunks used during synthesis — required when run_critique=true, else '[]'.

    Returns JSON: {passed: bool, failures: list[str], critique_notes: str, plan_json: dict}
    Always use the returned plan_json — it contains any auto-fixes and critique changes.
    Always call save_plan immediately after this tool."""
    trainee = crud.get_trainee_by_id(trainee_id)
    if not trainee:
        return json.dumps({"error": f"Trainee {trainee_id} not found"})

    plan   = json.loads(plan_json)
    chunks = _flatten_retriever_chunks(source_chunks_json) if source_chunks_json and source_chunks_json != "[]" else []

    val          = validate_structure(plan, trainee)
    current_plan = val.fixed_plan if val.fixed_plan else plan

    critique_notes = ""
    if run_critique:
        crit = critique_plan(current_plan, trainee, chunks)
        if crit.changed:
            current_plan   = crit.plan_json.model_dump()
            critique_notes = crit.critique_notes

    return json.dumps({
        "passed":         val.passed,
        "failures":       val.failures,
        "critique_notes": critique_notes,
        "plan_json":      current_plan,
    })


@tool
def save_plan(
    plan_json: str,
    trainee_id: int,
    is_revision: bool,
    change_description: str,
    triggered_by: str,
) -> str:
    """Validate against PlanSchema and persist to SQLite (plans + plan_revisions tables).

    New plan: archives the current active plan, inserts a new active one.
    Revision: updates the active plan in-place and appends a plan_revisions snapshot.

    triggered_by: 'user_request' | 'self_critique' | 'validation_fix'

    Returns JSON: {plan_id: int, change_summary: str, plan_md: str}"""
    if triggered_by not in ("user_request", "self_critique", "validation_fix"):
        triggered_by = "user_request"

    try:
        validated = PlanSchema.model_validate(json.loads(plan_json))
        if not is_revision:
            validated = _expand_to_duration(validated)
    except Exception as e:
        return json.dumps({"error": f"PlanSchema validation failed: {e}"})

    trainee         = crud.get_trainee_by_id(trainee_id)
    plan_dict_clean = validated.model_dump()

    if is_revision:
        existing = crud.get_active_plan(trainee_id)
        if not existing:
            return json.dumps({"error": "No active plan found to revise."})
        previous_json           = existing.plan_json
        existing.plan_json      = plan_dict_clean
        existing.difficulty     = validated.difficulty
        existing.duration_weeks = validated.duration_weeks
        crud.update_plan(existing)
        crud.add_plan_revision(PlanRevision(
            plan_id=existing.id,
            revision_number=0,
            change_description=change_description,
            previous_plan_json=previous_json,
            new_plan_json=plan_dict_clean,
            triggered_by=triggered_by,
        ))
        plan_id = existing.id
    else:
        saved   = crud.create_plan(Plan(
            trainee_id=trainee_id,
            difficulty=validated.difficulty,
            duration_weeks=validated.duration_weeks,
            plan_json=plan_dict_clean,
            status="active",
        ))
        plan_id = saved.id

    return json.dumps({
        "plan_id":        plan_id,
        "change_summary": change_description,
    })


@tool
def patch_existing_plan(
    current_plan_json: str,
    patch_instructions: str,
    chunks_json: str,
    trainee_id: int,
) -> str:
    """Apply targeted changes to an existing plan without full reconstruction.
    current_plan_json: the existing plan as a JSON string.
    patch_instructions: natural language describing exactly what to change.
    chunks_json: retrieved exercise alternatives as a JSON string — pass '[]' if not needed.
    Returns JSON: {needs_rebuild: bool, change_description: str, plan_json: dict}
    If needs_rebuild is true, use synthesize_new_plan instead.
    Always call validate_and_critique then save_plan immediately after this tool."""
    trainee = crud.get_trainee_by_id(trainee_id)
    if not trainee:
        return json.dumps({"error": f"Trainee {trainee_id} not found"})

    current = json.loads(current_plan_json)
    chunks  = _flatten_retriever_chunks(chunks_json) if chunks_json and chunks_json != "[]" else []
    output  = patch_plan(current, patch_instructions, chunks, trainee)

    return json.dumps({
        "needs_rebuild":      output.needs_rebuild,
        "change_description": output.change_description,
        "plan_json":          output.plan_json.model_dump(),
    })


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

@tool
def propose_plan_structure(chunks_json: str, trainee_id: int, request_text: str) -> str:
    """Stage 1 of the interactive plan flow — generate a compact training skeleton for user approval.
    Produces ONLY the split type, weekly schedule, rep style, and duration — NO exercises yet.
    Write the returned structure_json to plan_structure.json in the VFS, then surface the
    summary to Coach so the user can approve or request changes.
    Do NOT proceed to synthesize_week_one until the user has confirmed the structure.
    Returns JSON: {structure_json: str, summary: str}"""
    trainee = crud.get_trainee_by_id(trainee_id)
    if not trainee:
        return json.dumps({"error": f"Trainee {trainee_id} not found"})

    chunks    = _flatten_retriever_chunks(chunks_json)
    structure = propose_structure(chunks, trainee, request_text)

    day_lines = "\n".join(
        f"  Day {i + 1}: {label}"
        for i, label in enumerate(structure.day_schedule)
    )
    summary = (
        f"{structure.split_type} split — {structure.days_per_week} days/week, "
        f"{structure.duration_weeks} weeks, {structure.rep_style}.\n"
        f"Weekly schedule:\n{day_lines}\n"
        f"Rationale: {structure.rationale}"
    )

    return json.dumps({
        "structure_json": structure.model_dump_json(),
        "summary":        summary,
    })


@tool
def synthesize_week_one(
    structure_json: str,
    chunks_json: str,
    trainee_id: int,
    user_feedback: str = "",
) -> str:
    """Stage 2 of the interactive plan flow — fill in Week 1 exercises for the approved structure.
    structure_json: the ProgramStructure JSON from propose_plan_structure (or user-modified version).
    user_feedback: any changes the user requested to the structure before filling exercises.
    Write the returned week1_plan_json to plan_week1.json in the VFS, then surface the
    week1_summary to Coach so the user can approve or request changes.
    Do NOT call save_plan until the user has confirmed Week 1.
    Returns JSON: {week1_plan_json: str, week1_summary: str}"""
    trainee = crud.get_trainee_by_id(trainee_id)
    if not trainee:
        return json.dumps({"error": f"Trainee {trainee_id} not found"})

    structure = ProgramStructure.model_validate_json(structure_json)
    chunks    = _flatten_retriever_chunks(chunks_json)
    week1_plan = build_week_one(structure, chunks, trainee, user_feedback)

    # Build a readable summary of Week 1
    lines = [f"Week 1 — {structure.split_type} ({structure.rep_style}):"]
    for day in week1_plan.weeks[0].days if week1_plan.weeks else []:
        if day.rest_day:
            lines.append(f"  Day {day.day}: REST")
        else:
            lines.append(f"  Day {day.day} — {day.focus}:")
            for ex in day.exercises:
                reps_str = f"{abs(ex.reps)}s" if ex.reps < 0 else f"{ex.reps} reps"
                lines.append(f"    • {ex.name}: {ex.sets}×{reps_str}, rest {ex.rest_seconds}s ({ex.equipment})")

    return json.dumps({
        "week1_plan_json": week1_plan.model_dump_json(),
        "week1_summary":   "\n".join(lines),
    })


DESIGNER_TOOLS = [
    collect_missing_info,
    update_trainee_profile,
    load_context,
    propose_plan_structure,
    synthesize_week_one,
    synthesize_new_plan,
    validate_and_critique,
    save_plan,
    patch_existing_plan,
]


def build_designer_agent(backend: FilesystemBackend | None = None) -> CompiledStateGraph:
    """Build and return the compiled Program Designer deepagent.

    backend: pass a shared FilesystemBackend from orchestration so Coach and Designer
    share the same VFS session. If None, a standalone virtual backend is created
    (useful for isolated testing of the Designer).
    """
    from fitness_multiagent_rag.agents.retriever.agent import build_retriever_agent

    retriever_subagent: CompiledSubAgent = {
        "name": "retriever",
        "description": (
            "Searches the fitness corpus (programs + exercises) using an accumulate-and-expand "
            "retrieval loop. Returns grounded workout program summaries and exercise chunks. "
            "Provide the full retrieval request including trainee context: goal, equipment, "
            "fitness level, and duration. Use for new plans and for revisions that need "
            "new exercises or a different program structure."
        ),
        "runnable": build_retriever_agent(),
    }

    if backend is None:
        backend = FilesystemBackend(root_dir=str(_PROJECT_ROOT), virtual_mode=True)

    return create_deep_agent(
        model=get_model(),
        tools=DESIGNER_TOOLS,
        system_prompt=_SYSTEM_PROMPT,
        backend=backend,
        subagents=[retriever_subagent],
        skills=[_SKILLS_DIR],
        name="designer",
    )

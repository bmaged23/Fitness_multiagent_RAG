from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

_SRC_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_SRC_DIR))
sys.path.insert(0, str(_SRC_DIR.parent))

from langchain_core.tools import tool
from langgraph.graph.state import CompiledStateGraph
from deepagents import CompiledSubAgent, create_deep_agent
from deepagents.backends import FilesystemBackend
from tavily import TavilyClient

from fitness_multiagent_rag.llm.model import get_model
from fitness_multiagent_rag.utils.prompt_loader import load_agent_prompt
from fitness_multiagent_rag.db import crud
from fitness_multiagent_rag.db.models import Plan, ProgressLog
from fitness_multiagent_rag.memory.sqlite_memory_backend import CoachMemoryBackend
from .identity import COACH_NAME

_AGENT_DIR    = Path(__file__).parent
_PROJECT_ROOT = _AGENT_DIR.parent.parent.parent.parent
_SKILLS_DIR   = "/src/fitness_multiagent_rag/agents/coach/skills"
_SYSTEM_PROMPT = load_agent_prompt(_AGENT_DIR, "system_prompt.md")

_VALID_EQUIPMENT = {"Full Gym", "Garage Gym", "At Home", "Dumbbell Only"}
_VALID_GOALS = {
    "Bodybuilding", "Muscle & Sculpting", "Powerbuilding", "Athletics",
    "Powerlifting", "Bodyweight Fitness", "Olympic Weightlifting", "At-Home & Calisthenics",
}
_VALID_LEVELS = {"Beginner", "Novice", "Intermediate", "Advanced"}

_memory_backend = CoachMemoryBackend()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def update_fitness_profile(
    trainee_id: int,
    goal: str = "",
    fitness_level: str = "",
    equipment_available: str = "[]",
    injuries_limitations: str = "",
) -> str:
    """Update the trainee's fitness profile (goal, level, equipment, injuries).

    Call this after the trainee answers onboarding questions or updates their preferences.
    The trainee account already exists — this only updates fitness-related fields.

    equipment_available: JSON array string, e.g. '["Full Gym"]'.
    Map all natural-language answers to exact allowed values before calling:
      goal: Bodybuilding / Muscle & Sculpting / Powerbuilding / Athletics /
            Powerlifting / Bodyweight Fitness / Olympic Weightlifting / At-Home & Calisthenics
      fitness_level: Beginner / Novice / Intermediate / Advanced
      equipment_available: Full Gym / Garage Gym / Dumbbell Only / At Home

    Returns JSON: {trainee_id: int, updated_fields: list}
    """
    trainee = crud.get_trainee_by_id(trainee_id)
    if not trainee:
        return json.dumps({"error": f"Trainee id={trainee_id} not found."})

    try:
        eq_list = json.loads(equipment_available)
        if not isinstance(eq_list, list):
            eq_list = [equipment_available]
    except Exception:
        eq_list = [equipment_available] if equipment_available else []

    updated = []
    if goal and goal in _VALID_GOALS:
        trainee.goal = goal
        updated.append("goal")
    if fitness_level and fitness_level in _VALID_LEVELS:
        trainee.fitness_level = fitness_level
        updated.append("fitness_level")
    valid_eq = [e for e in eq_list if e in _VALID_EQUIPMENT]
    if valid_eq:
        trainee.equipment_available = valid_eq
        updated.append("equipment_available")
    if injuries_limitations:
        trainee.injuries_limitations = injuries_limitations
        updated.append("injuries_limitations")

    crud.update_trainee(trainee)
    return json.dumps({"trainee_id": trainee.id, "updated_fields": updated})


@tool
def get_trainee_profile(trainee_id: int) -> str:
    """Load the full trainee profile from the database.
    Returns JSON with name, age, gender, goal, fitness_level, equipment_available, injuries_limitations.
    Call this when you need profile details that are not already in context."""
    trainee = crud.get_trainee_by_id(trainee_id)
    if not trainee:
        return json.dumps({"error": f"Trainee id={trainee_id} not found"})
    return json.dumps({
        "trainee_id":           trainee.id,
        "name":                 trainee.name,
        "age":                  trainee.age,
        "gender":               trainee.gender,
        "goal":                 trainee.goal,
        "fitness_level":        trainee.fitness_level,
        "equipment_available":  trainee.equipment_available,
        "injuries_limitations": trainee.injuries_limitations,
    })


@tool
def get_active_plan_summary(trainee_id: int) -> str:
    """Return a compact summary of the trainee's current active workout plan.
    Does NOT return the full exercise JSON — only goal, difficulty, duration, weekly schedule,
    deload weeks, and weight progression.
    Call this before answering any plan-related question."""
    plan = crud.get_active_plan(trainee_id)
    if not plan:
        return json.dumps({"active_plan": None, "message": "No active plan found."})

    pj = plan.plan_json
    progression = pj.get("progression", {})
    deload_weeks = progression.get("deload_weeks", [])
    weight_inc   = progression.get("weight_increment_kg_per_week", 2.5)

    # Build week schedule from week 1 only (avoid dumping all weeks)
    schedule: list[str] = []
    if pj.get("weeks"):
        week1 = pj["weeks"][0]
        for d in week1.get("days", []):
            label = "REST" if d.get("rest_day") else d.get("focus", f"Day {d['day']}")
            schedule.append(f"  Day {d['day']}: {label}")

    return json.dumps({
        "plan_id":        plan.id,
        "goal":           pj.get("goal"),
        "difficulty":     pj.get("difficulty"),
        "duration_weeks": pj.get("duration_weeks"),
        "deload_weeks":   deload_weeks,
        "weight_increment_kg_per_week": weight_inc,
        "weekly_schedule": "\n".join(schedule),
    })


@tool
def log_workout(
    trainee_id: int,
    log_date: str,
    completed_workouts: str,
    notes: str = "",
    weight_kg: float = 0.0,
) -> str:
    """Log a completed workout session or progress update to the database.

    log_date: YYYY-MM-DD (use today's date if not specified)
    completed_workouts: JSON array of workout descriptions,
      e.g. '["Day 1 — Full Body A: completed all sets"]'
    weight_kg: trainee's current body weight in kg (0 if not provided)
    notes: freeform coaching notes from this session

    Returns JSON: {log_id: int, message: str}
    """
    if not log_date:
        log_date = date.today().isoformat()

    try:
        workouts = json.loads(completed_workouts)
        if not isinstance(workouts, list):
            workouts = [completed_workouts]
    except Exception:
        workouts = [completed_workouts] if completed_workouts else []

    active_plan = crud.get_active_plan(trainee_id)
    log = ProgressLog(
        trainee_id=trainee_id,
        plan_id=active_plan.id if active_plan else None,
        log_date=log_date,
        weight_kg=weight_kg if weight_kg > 0 else None,
        completed_workouts=workouts,
        notes=notes or None,
    )
    saved = crud.log_progress(log)
    return json.dumps({"log_id": saved.id, "message": f"Workout logged for {log_date}."})


@tool
def get_progress_summary(trainee_id: int, last_n: int = 7) -> str:
    """Return the last N workout logs for this trainee.
    Use this to review recent adherence, spot trends, or give personalised feedback.
    last_n: number of recent sessions to return (default 7, max 30)"""
    last_n = min(last_n, 30)
    logs = crud.get_recent_logs(trainee_id, limit=last_n)
    if not logs:
        return json.dumps({"logs": [], "message": "No workout logs found yet."})

    entries = [
        {
            "date":               l.log_date,
            "completed_workouts": l.completed_workouts,
            "weight_kg":          l.weight_kg,
            "notes":              l.notes,
        }
        for l in logs
    ]
    return json.dumps({"session_count": len(entries), "logs": entries})


@tool
def save_session_memory(trainee_id: int, key_takeaways: str) -> str:
    """Persist key facts from this coaching session to long-term memory.
    Call this at the END of every session.

    key_takeaways: plain text summary of what was learned or decided this session.
    Include: new goals/preferences discovered, plan decisions, struggles, achievements.
    Do NOT include generic check-in exchanges or motivational filler.

    Returns JSON: {saved: true}
    """
    _memory_backend.save(trainee_id, key_takeaways)
    return json.dumps({"saved": True})


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the internet for fitness, nutrition, health, or exercise information.
    Use when the trainee asks something specific you cannot answer with certainty:
    supplement doses, food macros, injury rehab protocols, research findings.
    Keep queries concise and fitness/health-scoped.
    After results: summarise the key finding; if nothing useful found, say so honestly.
    Never say 'I can't answer' before searching."""
    from config.settings import TAVILY_API_KEY
    if not TAVILY_API_KEY:
        return json.dumps({"error": "TAVILY_API_KEY not set — web search unavailable."})
    try:
        client = TavilyClient(api_key=TAVILY_API_KEY)
        response = client.search(query, max_results=max_results, search_depth="basic")
        results = response.get("results", [])
        if not results:
            return json.dumps({"results_count": 0, "results": "No results found."})
        formatted = "\n\n".join(
            f"[{i + 1}] {r.get('title', 'No title')}\n{r.get('content', '')[:400]}"
            for i, r in enumerate(results)
        )
        return json.dumps({"results_count": len(results), "results": formatted})
    except Exception as e:
        return json.dumps({"error": f"Web search failed: {e}"})


COACH_TOOLS = [
    update_fitness_profile,
    get_trainee_profile,
    get_active_plan_summary,
    log_workout,
    get_progress_summary,
    save_session_memory,
    web_search,
]


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def build_coach_agent(backend: FilesystemBackend | None = None) -> CompiledStateGraph:
    """Build and return the compiled Coach deepagent.

    Coach has two subagents:
      - designer: full 3-stage plan creation and revision flow
      - retriever: direct vector-DB exercise / program lookups
    """
    from fitness_multiagent_rag.agents.designer.agent import build_designer_agent
    from fitness_multiagent_rag.agents.retriever.agent import build_retriever_agent

    if backend is None:
        backend = FilesystemBackend(root_dir=str(_PROJECT_ROOT), virtual_mode=True)

    designer_subagent: CompiledSubAgent = {
        "name": "designer",
        "description": (
            "Creates new workout plans and handles plan revisions through a structured "
            "3-stage interactive flow (structure proposal → Week 1 exercises → save). "
            "Call when the trainee explicitly wants a new plan or wants to change their existing one. "
            "Provide: trainee_id, goal, equipment, fitness level, injuries, and the full request."
        ),
        "runnable": build_designer_agent(backend),
    }

    retriever_subagent: CompiledSubAgent = {
        "name": "retriever",
        "description": (
            "Searches the fitness corpus (fitness_programs + fitness_exercises Qdrant collections) "
            "for exercise options, training methods, and program references. "
            "Call for quick exercise lookups or when answering training questions that need "
            "grounded data — NOT for full plan creation (use designer for that). "
            "Provide the full question with trainee context: goal, equipment, fitness level."
        ),
        "runnable": build_retriever_agent(),
    }

    return create_deep_agent(
        model=get_model(),
        tools=COACH_TOOLS,
        system_prompt=_SYSTEM_PROMPT,
        backend=backend,
        subagents=[designer_subagent, retriever_subagent],
        skills=[_SKILLS_DIR],
        name=COACH_NAME.lower(),
    )

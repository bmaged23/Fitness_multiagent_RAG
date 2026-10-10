"""Coach-facing tools for independently stored nutrition plans."""
import json
from langchain_core.tools import tool
from fitness_multiagent_rag.db import nutrition
from fitness_multiagent_rag.schemas.nutrition_plan import NutritionPlanSchema


def _input(plan: NutritionPlanSchema | str):
    return plan.model_dump(mode='json') if isinstance(plan, NutritionPlanSchema) else plan


def _error(exc: Exception) -> str:
    return json.dumps({'error': f'{type(exc).__name__}: {exc}', 'retryable': False})


@tool
def save_nutrition_plan(trainee_id: int, plan: NutritionPlanSchema | str) -> str:
    """Validate and save a nutrition plan as a draft for review, without changing the active plan.
    Accept native plan data or its JSON string. Present the saved draft and ask for approval.
    Required: goal, daily_targets (calories_kcal, protein_g, carbohydrate_g, fat_g), meals
    (name, foods with name/portion/alternatives), dietary_preferences, allergies, restrictions,
    start_date and review_date (YYYY-MM-DD). Never activate before user approval.
    """
    try:
        return json.dumps({'nutrition_plan': nutrition.save_draft(trainee_id, _input(plan)), 'approval_required': True})
    except (ValueError, TypeError) as exc:
        return _error(exc)


@tool
def get_nutrition_plan(trainee_id: int) -> str:
    """Load the trainee's active nutrition plan and pending draft, including meals and targets.
    Use for requests to show a diet, meal, or nutrition plan and before continuing approval.
    Distinguish pending drafts from approved active plans. Do not regenerate a stored plan.
    """
    return json.dumps({'active_plan': nutrition.get_plan(trainee_id, 'active'),
                       'draft': nutrition.get_plan(trainee_id, 'draft')})


@tool
def approve_nutrition_plan(trainee_id: int, plan_id: int) -> str:
    """Activate the specified nutrition draft only after the trainee explicitly approves it.
    Archives the previous active nutrition plan. Does not change workout programs.
    Use the draft ID returned by get_nutrition_plan; never invent an ID.
    """
    try:
        return json.dumps({'nutrition_plan': nutrition.activate_draft(trainee_id, plan_id)})
    except ValueError as exc:
        return _error(exc)


@tool
def revise_nutrition_plan(trainee_id: int, plan_id: int, plan: NutritionPlanSchema | str,
                          change_description: str) -> str:
    """Save a requested nutrition revision as a draft, with a complete before/after history.
    plan is the full updated plan, not a partial patch. An active plan stays unchanged until
    the trainee approves this revision. Load the stored plan first and preserve untouched data.
    """
    try:
        return json.dumps({'nutrition_plan': nutrition.save_draft(trainee_id, _input(plan),
            change_description, plan_id), 'approval_required': True})
    except (ValueError, TypeError) as exc:
        return _error(exc)


@tool
def get_nutrition_plan_history(trainee_id: int, plan_id: int) -> str:
    """Load nutrition plan revision snapshots belonging to this trainee."""
    return json.dumps({'revisions': nutrition.revisions(trainee_id, plan_id)})

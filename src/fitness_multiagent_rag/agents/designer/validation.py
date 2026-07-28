from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional

from fitness_multiagent_rag.db.models import Trainee

# Equipment coverage hierarchy.
# A trainee with "Garage Gym" can do exercises tagged Garage Gym, At Home, or Dumbbell Only.
# A trainee with "Full Gym" can do everything.
_COVERS: dict[str, set[str]] = {
    "Full Gym":      {"Full Gym", "Garage Gym", "At Home", "Dumbbell Only"},
    "Garage Gym":    {"Garage Gym", "At Home", "Dumbbell Only"},
    "At Home":       {"At Home", "Dumbbell Only"},
    "Dumbbell Only": {"Dumbbell Only"},
}

_LEVEL_RANK = {"beginner": 0, "novice": 1, "intermediate": 2, "advanced": 3}


@dataclass
class ValidationResult:
    passed: bool
    failures: list[str] = field(default_factory=list)
    fixed_plan: Optional[dict] = None


def validate_structure(plan: dict, trainee: Trainee) -> ValidationResult:
    """
    Three deterministic checks — always runs before save_plan.
    Auto-fixes rest-day violations in place. Equipment and difficulty failures
    are returned as messages for the LLM to resolve via patch or re-synthesis.
    """
    failures: list[str] = []
    fixed = copy.deepcopy(plan)
    auto_fixed = False

    # Compute which exercise equipment categories this trainee can use.
    can_use: set[str] = set()
    for eq in (trainee.equipment_available or []):
        can_use.update(_COVERS.get(eq, {eq}))

    # --- Check 1: Equipment match ---
    for week in fixed.get("weeks", []):
        for day in week.get("days", []):
            if day.get("rest_day"):
                continue
            for ex in day.get("exercises", []):
                ex_eq = (ex.get("equipment") or "").strip()
                if not ex_eq or ex_eq.lower() in ("bodyweight", "none"):
                    continue
                if ex_eq not in can_use:
                    failures.append(
                        f"Week {week.get('week')} Day {day.get('day')}: "
                        f"'{ex.get('name', '?')}' requires '{ex_eq}' "
                        f"but trainee has {list(trainee.equipment_available or [])}"
                    )

    # --- Check 2: Rest days (auto-fixable) ---
    for week in fixed.get("weeks", []):
        has_rest = any(d.get("rest_day", False) for d in week.get("days", []))
        if not has_rest:
            non_rest = [d for d in week.get("days", []) if not d.get("rest_day", False)]
            if non_rest:
                lightest = min(non_rest, key=lambda d: len(d.get("exercises", [])))
                lightest["rest_day"] = True
                lightest["exercises"] = []
                auto_fixed = True
                failures.append(
                    f"Week {week.get('week')}: no rest day — "
                    f"auto-fixed day {lightest.get('day')} as rest"
                )
            else:
                failures.append(f"Week {week.get('week')}: no rest day, no auto-fix possible")

    # --- Check 3: Difficulty alignment ---
    plan_diff = (fixed.get("difficulty") or "").lower()
    trainee_lvl = (trainee.fitness_level or "").lower()
    if plan_diff in _LEVEL_RANK and trainee_lvl in _LEVEL_RANK:
        gap = abs(_LEVEL_RANK[plan_diff] - _LEVEL_RANK[trainee_lvl])
        if gap > 1:
            failures.append(
                f"Plan difficulty '{fixed.get('difficulty')}' is {gap} levels from "
                f"trainee level '{trainee.fitness_level}' — gap exceeds 1"
            )

    fatal = [f for f in failures if "auto-fixed" not in f]
    return ValidationResult(
        passed=len(fatal) == 0,
        failures=failures,
        fixed_plan=fixed if auto_fixed else None,
    )

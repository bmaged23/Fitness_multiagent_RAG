from __future__ import annotations

from pydantic import BaseModel, Field


class Exercise(BaseModel):
    name: str
    sets: int = Field(ge=1, le=20)
    reps: int = Field(ge=0)
    rest_seconds: int = Field(ge=0)
    equipment: str
    muscle_group: str
    notes: str = ""


class Day(BaseModel):
    day: int = Field(ge=1, le=7)
    focus: str
    rest_day: bool = False
    exercises: list[Exercise] = Field(default_factory=list)


class Week(BaseModel):
    week: int = Field(ge=1)
    days: list[Day]


class ProgressionScheme(BaseModel):
    """How the plan progresses week-over-week. Applied by _expand_to_duration."""
    weight_increment_kg_per_week: float = 2.5   # kg to add each non-deload week
    deload_weeks: list[int] = Field(default_factory=list)  # e.g. [4, 8]
    deload_volume_factor: float = 0.6           # fraction of normal sets on deload weeks


class PlanSchema(BaseModel):
    goal: str
    difficulty: str
    duration_weeks: int = Field(ge=6, le=52)
    equipment_available: list[str]
    progression: ProgressionScheme = Field(default_factory=ProgressionScheme)
    weeks: list[Week]

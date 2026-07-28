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


class PlanSchema(BaseModel):
    goal: str
    difficulty: str
    duration_weeks: int = Field(ge=1, le=52)
    equipment_available: list[str]
    weeks: list[Week]

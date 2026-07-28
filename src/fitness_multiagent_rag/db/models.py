from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Trainee:
    name: str
    secondary_id: str
    equipment_available: list[str] = field(default_factory=list)
    id: Optional[int] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    fitness_level: Optional[str] = None  # beginner / intermediate / advanced
    injuries_limitations: Optional[str] = None
    goal: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "Trainee":
        return cls(
            id=row["id"],
            name=row["name"],
            secondary_id=row["secondary_id"],
            age=row.get("age"),
            gender=row.get("gender"),
            fitness_level=row.get("fitness_level"),
            equipment_available=json.loads(row.get("equipment_available") or "[]"),
            injuries_limitations=row.get("injuries_limitations"),
            goal=row.get("goal"),
            created_at=row.get("created_at"),
        )


@dataclass
class Plan:
    trainee_id: int
    plan_json: dict = field(default_factory=dict)
    id: Optional[int] = None
    difficulty: Optional[str] = None
    duration_weeks: Optional[int] = None
    status: str = "active"  # active / completed / archived
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "Plan":
        return cls(
            id=row["id"],
            trainee_id=row["trainee_id"],
            difficulty=row.get("difficulty"),
            duration_weeks=row.get("duration_weeks"),
            plan_json=json.loads(row.get("plan_json") or "{}"),
            status=row["status"],
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


@dataclass
class PlanRevision:
    plan_id: int
    revision_number: int
    triggered_by: str  # user_request / self_critique / validation_fix
    new_plan_json: dict = field(default_factory=dict)
    previous_plan_json: dict = field(default_factory=dict)
    id: Optional[int] = None
    change_description: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "PlanRevision":
        return cls(
            id=row["id"],
            plan_id=row["plan_id"],
            revision_number=row["revision_number"],
            change_description=row.get("change_description"),
            previous_plan_json=json.loads(row.get("previous_plan_json") or "{}"),
            new_plan_json=json.loads(row.get("new_plan_json") or "{}"),
            triggered_by=row["triggered_by"],
            created_at=row.get("created_at"),
        )


@dataclass
class ProgressLog:
    trainee_id: int
    log_date: str  # YYYY-MM-DD
    completed_workouts: list = field(default_factory=list)
    id: Optional[int] = None
    plan_id: Optional[int] = None
    weight_kg: Optional[float] = None
    notes: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "ProgressLog":
        return cls(
            id=row["id"],
            trainee_id=row["trainee_id"],
            plan_id=row.get("plan_id"),
            log_date=row["log_date"],
            weight_kg=row.get("weight_kg"),
            completed_workouts=json.loads(row.get("completed_workouts") or "[]"),
            notes=row.get("notes"),
        )


@dataclass
class CoachMemory:
    trainee_id: int
    summary_text: str = ""
    session_count_since_truncation: int = 0
    id: Optional[int] = None
    last_updated: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "CoachMemory":
        return cls(
            id=row["id"],
            trainee_id=row["trainee_id"],
            summary_text=row.get("summary_text") or "",
            session_count_since_truncation=row.get("session_count_since_truncation") or 0,
            last_updated=row.get("last_updated"),
        )

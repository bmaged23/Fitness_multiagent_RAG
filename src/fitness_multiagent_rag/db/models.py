from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Trainee:
    """Trainee profile — no credentials.  This is the only model the LLM ever sees."""
    name: str
    secondary_id: str = ""
    equipment_available: list[str] = field(default_factory=list)
    id: Optional[int] = None
    # runtime-only: populated after auth lookup, never stored in trainees table
    username: Optional[str] = None
    # mandatory profile
    email: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None          # 'male' | 'female'
    # fitness profile (set during onboarding)
    fitness_level: Optional[str] = None  # Beginner / Novice / Intermediate / Advanced
    injuries_limitations: Optional[str] = None
    goal: Optional[str] = None
    # optional body stats
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    body_fat_pct: Optional[float] = None
    muscle_pct: Optional[float] = None
    images_dir: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "Trainee":
        return cls(
            id=row["id"],
            name=row["name"],
            secondary_id=row.get("secondary_id") or "",
            email=row.get("email"),
            phone=row.get("phone"),
            age=row.get("age"),
            gender=row.get("gender"),
            fitness_level=row.get("fitness_level"),
            equipment_available=json.loads(row.get("equipment_available") or "[]"),
            injuries_limitations=row.get("injuries_limitations"),
            goal=row.get("goal"),
            height_cm=row.get("height_cm"),
            weight_kg=row.get("weight_kg"),
            body_fat_pct=row.get("body_fat_pct"),
            muscle_pct=row.get("muscle_pct"),
            images_dir=row.get("images_dir"),
            created_at=row.get("created_at"),
        )


@dataclass
class TraineeAuth:
    """Credentials only — never exposed to the LLM."""
    trainee_id: int
    username: str
    password_hash: str
    id: Optional[int] = None
    created_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "TraineeAuth":
        return cls(
            id=row["id"],
            trainee_id=row["trainee_id"],
            username=row["username"],
            password_hash=row["password_hash"],
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

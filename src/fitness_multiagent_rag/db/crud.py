from __future__ import annotations

import json
from typing import Optional

from .connection import get_db, get_db_ro
from .models import CoachMemory, Plan, PlanRevision, ProgressLog, Trainee

# ---------------------------------------------------------------------------
# trainees
# ---------------------------------------------------------------------------

def get_trainee(name: str, secondary_id: str) -> Optional[Trainee]:
    """Look up a trainee by the dual-key identity (name + secondary_id)."""
    with get_db_ro() as conn:
        row = conn.execute(
            "SELECT * FROM trainees WHERE name = ? AND secondary_id = ?",
            (name, secondary_id),
        ).fetchone()
    return Trainee.from_row(dict(row)) if row else None


def get_trainee_by_id(trainee_id: int) -> Optional[Trainee]:
    with get_db_ro() as conn:
        row = conn.execute(
            "SELECT * FROM trainees WHERE id = ?", (trainee_id,)
        ).fetchone()
    return Trainee.from_row(dict(row)) if row else None


def create_trainee(trainee: Trainee) -> Trainee:
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO trainees
                (name, secondary_id, age, gender, fitness_level,
                 equipment_available, injuries_limitations, goal)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trainee.name,
                trainee.secondary_id,
                trainee.age,
                trainee.gender,
                trainee.fitness_level,
                json.dumps(trainee.equipment_available),
                trainee.injuries_limitations,
                trainee.goal,
            ),
        )
        trainee.id = cur.lastrowid
    return trainee


def update_trainee(trainee: Trainee) -> None:
    with get_db() as conn:
        conn.execute(
            """
            UPDATE trainees SET
                age = ?, gender = ?, fitness_level = ?,
                equipment_available = ?, injuries_limitations = ?, goal = ?
            WHERE id = ?
            """,
            (
                trainee.age,
                trainee.gender,
                trainee.fitness_level,
                json.dumps(trainee.equipment_available),
                trainee.injuries_limitations,
                trainee.goal,
                trainee.id,
            ),
        )


# ---------------------------------------------------------------------------
# plans
# ---------------------------------------------------------------------------

def get_active_plan(trainee_id: int) -> Optional[Plan]:
    with get_db_ro() as conn:
        row = conn.execute(
            "SELECT * FROM plans WHERE trainee_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (trainee_id,),
        ).fetchone()
    return Plan.from_row(dict(row)) if row else None


def get_plan_by_id(plan_id: int) -> Optional[Plan]:
    with get_db_ro() as conn:
        row = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    return Plan.from_row(dict(row)) if row else None


def create_plan(plan: Plan) -> Plan:
    # Archive any existing active plan before inserting the new one
    with get_db() as conn:
        conn.execute(
            "UPDATE plans SET status = 'archived', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
            "WHERE trainee_id = ? AND status = 'active'",
            (plan.trainee_id,),
        )
        cur = conn.execute(
            """
            INSERT INTO plans (trainee_id, difficulty, duration_weeks, plan_json, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                plan.trainee_id,
                plan.difficulty,
                plan.duration_weeks,
                json.dumps(plan.plan_json),
                plan.status,
            ),
        )
        plan.id = cur.lastrowid
    return plan


def update_plan(plan: Plan) -> None:
    with get_db() as conn:
        conn.execute(
            """
            UPDATE plans SET
                difficulty = ?, duration_weeks = ?, plan_json = ?,
                status = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')
            WHERE id = ?
            """,
            (
                plan.difficulty,
                plan.duration_weeks,
                json.dumps(plan.plan_json),
                plan.status,
                plan.id,
            ),
        )


def set_plan_status(plan_id: int, status: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE plans SET status = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?",
            (status, plan_id),
        )


# ---------------------------------------------------------------------------
# plan_revisions
# ---------------------------------------------------------------------------

def add_plan_revision(revision: PlanRevision) -> PlanRevision:
    with get_db() as conn:
        # Auto-increment revision_number if not set
        if revision.revision_number == 0:
            row = conn.execute(
                "SELECT COALESCE(MAX(revision_number), 0) FROM plan_revisions WHERE plan_id = ?",
                (revision.plan_id,),
            ).fetchone()
            revision.revision_number = row[0] + 1

        cur = conn.execute(
            """
            INSERT INTO plan_revisions
                (plan_id, revision_number, change_description,
                 previous_plan_json, new_plan_json, triggered_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                revision.plan_id,
                revision.revision_number,
                revision.change_description,
                json.dumps(revision.previous_plan_json),
                json.dumps(revision.new_plan_json),
                revision.triggered_by,
            ),
        )
        revision.id = cur.lastrowid
    return revision


def get_plan_revisions(plan_id: int) -> list[PlanRevision]:
    with get_db_ro() as conn:
        rows = conn.execute(
            "SELECT * FROM plan_revisions WHERE plan_id = ? ORDER BY revision_number",
            (plan_id,),
        ).fetchall()
    return [PlanRevision.from_row(dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# progress_logs
# ---------------------------------------------------------------------------

def log_progress(log: ProgressLog) -> ProgressLog:
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO progress_logs
                (trainee_id, plan_id, log_date, weight_kg, completed_workouts, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                log.trainee_id,
                log.plan_id,
                log.log_date,
                log.weight_kg,
                json.dumps(log.completed_workouts),
                log.notes,
            ),
        )
        log.id = cur.lastrowid
    return log


def get_recent_logs(trainee_id: int, limit: int = 14) -> list[ProgressLog]:
    with get_db_ro() as conn:
        rows = conn.execute(
            "SELECT * FROM progress_logs WHERE trainee_id = ? ORDER BY log_date DESC LIMIT ?",
            (trainee_id, limit),
        ).fetchall()
    return [ProgressLog.from_row(dict(r)) for r in rows]


def get_logs_since(trainee_id: int, since_date: str) -> list[ProgressLog]:
    """Return logs on or after since_date (YYYY-MM-DD)."""
    with get_db_ro() as conn:
        rows = conn.execute(
            "SELECT * FROM progress_logs WHERE trainee_id = ? AND log_date >= ? ORDER BY log_date",
            (trainee_id, since_date),
        ).fetchall()
    return [ProgressLog.from_row(dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# coach_memory
# ---------------------------------------------------------------------------

def get_memory(trainee_id: int) -> Optional[CoachMemory]:
    with get_db_ro() as conn:
        row = conn.execute(
            "SELECT * FROM coach_memory WHERE trainee_id = ?", (trainee_id,)
        ).fetchone()
    return CoachMemory.from_row(dict(row)) if row else None


def upsert_memory(memory: CoachMemory) -> None:
    """Insert or replace the memory row for a trainee (UNIQUE on trainee_id)."""
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO coach_memory
                (trainee_id, summary_text, session_count_since_truncation, last_updated)
            VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            ON CONFLICT(trainee_id) DO UPDATE SET
                summary_text                   = excluded.summary_text,
                session_count_since_truncation = excluded.session_count_since_truncation,
                last_updated                   = strftime('%Y-%m-%dT%H:%M:%SZ','now')
            """,
            (memory.trainee_id, memory.summary_text, memory.session_count_since_truncation),
        )


def increment_session_count(trainee_id: int) -> int:
    """Bump session_count_since_truncation by 1 and return the new value."""
    with get_db() as conn:
        conn.execute(
            """
            UPDATE coach_memory
            SET session_count_since_truncation = session_count_since_truncation + 1,
                last_updated = strftime('%Y-%m-%dT%H:%M:%SZ','now')
            WHERE trainee_id = ?
            """,
            (trainee_id,),
        )
        row = conn.execute(
            "SELECT session_count_since_truncation FROM coach_memory WHERE trainee_id = ?",
            (trainee_id,),
        ).fetchone()
    return row[0] if row else 0


def reset_session_count(trainee_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE coach_memory SET session_count_since_truncation = 0, "
            "last_updated = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE trainee_id = ?",
            (trainee_id,),
        )

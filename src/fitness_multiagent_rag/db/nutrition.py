"""Transactional draft, approval, and revision lifecycle for nutrition plans."""
import json
from pathlib import Path
from fitness_multiagent_rag.db.connection import get_db, get_db_ro
from fitness_multiagent_rag.schemas.nutrition_plan import NutritionPlanSchema

SCHEMA_PATH = Path(__file__).resolve().parents[3] / 'db' / 'nutrition_schema.sql'


def ensure_schema() -> None:
    with get_db() as conn:
        conn.executescript(SCHEMA_PATH.read_text())


def _record(row) -> dict | None:
    if row is None:
        return None
    record = dict(row)
    record['plan_json'] = json.loads(record['plan_json'])
    return record


def get_plan(trainee_id: int, status: str = 'active') -> dict | None:
    if status not in {'active', 'draft', 'archived'}:
        raise ValueError('Invalid nutrition plan status.')
    ensure_schema()
    with get_db_ro() as conn:
        return _record(conn.execute('SELECT * FROM nutrition_plans WHERE trainee_id=? AND status=? ORDER BY id DESC LIMIT 1',
                                    (trainee_id, status)).fetchone())


def _revision(conn, plan_id, previous, current, description):
    number = conn.execute('SELECT COALESCE(MAX(revision_number), 0)+1 FROM nutrition_plan_revisions WHERE nutrition_plan_id=?', (plan_id,)).fetchone()[0]
    conn.execute('INSERT INTO nutrition_plan_revisions (nutrition_plan_id, revision_number, previous_plan_json, new_plan_json, change_description) VALUES (?, ?, ?, ?, ?)',
                 (plan_id, number, previous, current, description))


def save_draft(trainee_id: int, plan: dict | str, change_description: str = 'Nutrition draft created', plan_id: int | None = None) -> dict:
    data = NutritionPlanSchema.model_validate_json(plan) if isinstance(plan, str) else NutritionPlanSchema.model_validate(plan)
    serialized = data.model_dump_json()
    ensure_schema()
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if not conn.execute('SELECT 1 FROM trainees WHERE id=?', (trainee_id,)).fetchone():
            raise ValueError('Trainee not found.')
        source = None
        if plan_id is not None:
            source = conn.execute('SELECT * FROM nutrition_plans WHERE id=? AND trainee_id=?', (plan_id, trainee_id)).fetchone()
            if source is None:
                raise ValueError('Nutrition plan does not belong to this trainee or does not exist.')
            if source['status'] == 'archived':
                raise ValueError('Cannot revise an archived nutrition plan.')
        draft = conn.execute("SELECT * FROM nutrition_plans WHERE trainee_id=? AND status='draft'", (trainee_id,)).fetchone()
        if source is not None and source['status'] == 'draft':
            draft = source
        if draft is not None:
            saved_id = draft['id']
            _revision(conn, saved_id, draft['plan_json'], serialized, change_description)
            conn.execute("UPDATE nutrition_plans SET plan_json=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?", (serialized, saved_id))
        else:
            cur = conn.execute("INSERT INTO nutrition_plans (trainee_id, plan_json) VALUES (?, ?)", (trainee_id, serialized))
            saved_id = cur.lastrowid
            _revision(conn, saved_id, source['plan_json'] if source else '{}', serialized, change_description)
        return _record(conn.execute('SELECT * FROM nutrition_plans WHERE id=?', (saved_id,)).fetchone())


def activate_draft(trainee_id: int, plan_id: int) -> dict:
    ensure_schema()
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute("SELECT * FROM nutrition_plans WHERE id=? AND trainee_id=? AND status='draft'", (plan_id, trainee_id)).fetchone()
        if row is None:
            raise ValueError('No matching nutrition draft to approve.')
        NutritionPlanSchema.model_validate_json(row['plan_json'])
        conn.execute("UPDATE nutrition_plans SET status='archived', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE trainee_id=? AND status='active'", (trainee_id,))
        conn.execute("UPDATE nutrition_plans SET status='active', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?", (plan_id,))
        return _record(conn.execute('SELECT * FROM nutrition_plans WHERE id=?', (plan_id,)).fetchone())


def revisions(trainee_id: int, plan_id: int) -> list[dict]:
    ensure_schema()
    with get_db_ro() as conn:
        rows = conn.execute('SELECT r.* FROM nutrition_plan_revisions r JOIN nutrition_plans p ON p.id=r.nutrition_plan_id WHERE p.trainee_id=? AND p.id=? ORDER BY revision_number', (trainee_id, plan_id)).fetchall()
        result = []
        for row in rows:
            record = dict(row)
            for key in ('previous_plan_json', 'new_plan_json'):
                record[key] = json.loads(record[key])
            result.append(record)
        return result


def list_plans(trainee_id: int) -> list[dict]:
    """List active, pending, and archived nutrition plans belonging to a trainee."""
    ensure_schema()
    with get_db_ro() as conn:
        return [_record(row) for row in conn.execute(
            'SELECT * FROM nutrition_plans WHERE trainee_id=? ORDER BY id DESC', (trainee_id,)).fetchall()]

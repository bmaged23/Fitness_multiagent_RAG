"""Persist unfinished plan stages without creating an active workout plan."""
import json
from langchain_core.tools import tool
from fitness_multiagent_rag.db.connection import get_db, get_db_ro


def save_draft(trainee_id: int, draft: dict) -> None:
    with get_db() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS plan_drafts (trainee_id INTEGER PRIMARY KEY REFERENCES trainees(id), draft_json TEXT NOT NULL)')
        conn.execute('INSERT INTO plan_drafts VALUES (?, ?) ON CONFLICT(trainee_id) DO UPDATE SET draft_json=excluded.draft_json',
                     (trainee_id, json.dumps(draft)))


def read_draft(trainee_id: int) -> dict:
    with get_db_ro() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='plan_drafts'").fetchone():
            return {}
        row = conn.execute('SELECT draft_json FROM plan_drafts WHERE trainee_id=?', (trainee_id,)).fetchone()
        return json.loads(row['draft_json']) if row else {}


def clear_draft(trainee_id: int) -> None:
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='plan_drafts'").fetchone():
            conn.execute('DELETE FROM plan_drafts WHERE trainee_id=?', (trainee_id,))


@tool
def load_plan_draft(trainee_id: int) -> str:
    """Load the stored structure, retrieved evidence, and Week 1 draft for stage continuation.
    Use before continuing a plan after user approval or a request for details.
    Drafts are not active or saved final plans. Never ask the user for internal JSON.
    """
    draft = read_draft(trainee_id)
    return json.dumps(draft or {'error': 'No plan draft exists yet; start Stage 1.'})

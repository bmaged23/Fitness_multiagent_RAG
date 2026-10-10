import json
from types import SimpleNamespace

from fitness_multiagent_rag.agents.designer import agent, drafts
from fitness_multiagent_rag.db import connection
from fitness_multiagent_rag.schemas.program_structure import ProgramStructure


def test_sqlite_draft_roundtrip_and_trainee_isolation(monkeypatch, tmp_path):
    monkeypatch.setattr(connection, 'SQLITE_DB_PATH', tmp_path / 'drafts.db')
    with connection.get_db() as conn:
        conn.execute('CREATE TABLE trainees (id INTEGER PRIMARY KEY)')
        conn.executemany('INSERT INTO trainees VALUES (?)', [(1,), (2,)])
    assert drafts.read_draft(1) == {}
    draft = {'stage': 'structure', 'structure_json': '{}', 'chunks': [{'text': 'dumbbells'}]}
    drafts.save_draft(1, draft)
    assert json.loads(drafts.load_plan_draft.invoke({'trainee_id': 1})) == draft
    assert drafts.read_draft(2) == {}
    drafts.save_draft(1, {**draft, 'stage': 'week1', 'week1_plan_json': '{}'})
    assert drafts.read_draft(1)['stage'] == 'week1'
    drafts.clear_draft(1)
    assert drafts.read_draft(1) == {}
    with connection.get_db_ro() as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='plans'").fetchone() is None


def test_stage_two_loads_stored_structure_and_evidence(monkeypatch):
    structure = ProgramStructure(goal='Bodybuilding', difficulty='Beginner',
        equipment_available=['Dumbbell Only'], split_type='Full Body', days_per_week=3,
        rep_style='8-12', duration_weeks=8, day_schedule=['A', 'REST', 'B', 'REST', 'C', 'REST', 'REST'],
        rationale='References')
    chunks = [{'text': 'dumbbell row'}]
    draft = {'stage': 'structure', 'structure_json': structure.model_dump_json(), 'chunks': chunks}
    monkeypatch.setattr(agent, 'read_draft', lambda _: draft)
    monkeypatch.setattr(agent.crud, 'get_trainee_by_id', lambda _: object())
    saved = []
    monkeypatch.setattr(agent, 'save_draft', lambda trainee_id, value: saved.append(value))
    def build(approved, evidence, trainee, feedback):
        assert approved == structure
        assert evidence == chunks
        return SimpleNamespace(weeks=[], progression=SimpleNamespace(deload_weeks=[],
            weight_increment_kg_per_week=1), model_dump_json=lambda: '{"week1":true}')
    monkeypatch.setattr(agent, 'build_week_one', build)
    result = json.loads(agent.synthesize_week_one.invoke({'structure_json': '', 'chunks_json': '[]',
        'trainee_id': 2, 'user_feedback': 'show me the details'}))
    assert result['week1_plan_json'] == '{"week1":true}'
    assert saved[0]['stage'] == 'week1'
    assert saved[0]['chunks'] == chunks

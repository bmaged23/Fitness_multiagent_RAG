import copy
import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError
from fitness_multiagent_rag.db import connection, nutrition
from fitness_multiagent_rag.agents.coach import agent, main, routing
from fitness_multiagent_rag.agents.coach import nutrition_tools as tools
from fitness_multiagent_rag.schemas.nutrition_plan import NutritionPlanSchema


@pytest.fixture
def database(monkeypatch, tmp_path):
    monkeypatch.setattr(connection, 'SQLITE_DB_PATH', tmp_path / 'test.db')
    with connection.get_db() as conn:
        conn.executescript((Path(__file__).parents[1] / 'db/schema.sql').read_text())
        conn.executemany('INSERT INTO trainees (id, name) VALUES (?, ?)', [(1, 'First'), (2, 'Second')])
        conn.execute("INSERT INTO plans (trainee_id, plan_json) VALUES (1, '{}')")
    nutrition.ensure_schema()
    return tmp_path / 'test.db'


@pytest.fixture
def plan():
    # Illustrative storage fixture, not a recommended diet.
    return {'goal': 'Test goal', 'daily_targets': {'calories_kcal': 2000,
        'protein_g': 100, 'carbohydrate_g': 250, 'fat_g': 200/3},
        'meals': [{'name': 'Breakfast', 'foods': [{'name': 'Oats', 'portion': '50 g',
            'alternatives': ['Rice']}]}], 'dietary_preferences': ['Vegetarian'],
        'allergies': ['Peanuts'], 'restrictions': [], 'start_date': '2026-10-10',
        'review_date': '2026-11-10', 'notes': 'Storage test'}


def test_draft_approval_and_workout_independence(database, plan):
    draft = nutrition.save_draft(1, plan)
    assert draft['status'] == 'draft'
    assert nutrition.get_plan(1) is None
    active = nutrition.activate_draft(1, draft['id'])
    assert active['status'] == 'active'
    assert active['plan_json'] == NutritionPlanSchema.model_validate(plan).model_dump(mode='json')
    assert nutrition.get_plan(2) is None
    with connection.get_db_ro() as conn:
        assert conn.execute('SELECT status FROM plans WHERE trainee_id=1').fetchone()[0] == 'active'


def test_revision_does_not_change_active_until_approved(database, plan):
    first = nutrition.save_draft(1, plan)
    nutrition.activate_draft(1, first['id'])
    changed = {**plan, 'notes': 'Updated meal preference'}
    draft = nutrition.save_draft(1, changed, 'Preference change', first['id'])
    assert draft['id'] != first['id']
    assert nutrition.get_plan(1)['plan_json']['notes'] == 'Storage test'
    history = nutrition.revisions(1, draft['id'])
    assert history[0]['previous_plan_json']['notes'] == 'Storage test'
    assert history[0]['new_plan_json']['notes'] == 'Updated meal preference'
    nutrition.activate_draft(1, draft['id'])
    assert nutrition.get_plan(1)['id'] == draft['id']
    assert nutrition.get_plan(1, 'archived')['id'] == first['id']


def test_draft_edits_have_ordered_history(database, plan):
    first = nutrition.save_draft(1, plan)
    second = nutrition.save_draft(1, {**plan, 'notes': 'Second'}, 'Second edit', first['id'])
    assert first['id'] == second['id']
    assert [r['revision_number'] for r in nutrition.revisions(1, first['id'])] == [1, 2]


def test_invalid_owner_cannot_revise_or_activate(database, plan):
    draft = nutrition.save_draft(1, plan)
    with pytest.raises(ValueError):
        nutrition.save_draft(2, plan, 'Wrong owner', draft['id'])
    with pytest.raises(ValueError):
        nutrition.activate_draft(2, draft['id'])
    assert nutrition.revisions(2, draft['id']) == []
    assert nutrition.get_plan(1, 'draft')['id'] == draft['id']


def test_failed_activation_preserves_existing_active(database, plan):
    draft = nutrition.save_draft(1, plan)
    nutrition.activate_draft(1, draft['id'])
    with pytest.raises(ValueError):
        nutrition.activate_draft(1, 999)
    assert nutrition.get_plan(1)['id'] == draft['id']


@pytest.mark.parametrize('field,value', [('review_date', '2026-01-01'), ('meals', []),
    ('allergies', None), ('daily_targets', {'calories_kcal': -1, 'protein_g': 0, 'carbohydrate_g': 0, 'fat_g': 0})])
def test_invalid_plans_do_not_write(database, plan, field, value):
    with pytest.raises(ValidationError):
        nutrition.save_draft(1, {**plan, field: value})
    assert nutrition.get_plan(1, 'draft') is None


def test_inconsistent_macro_targets_rejected(plan):
    bad = copy.deepcopy(plan)
    bad['daily_targets']['protein_g'] = 2000
    with pytest.raises(ValidationError):
        NutritionPlanSchema.model_validate(bad)


def test_db_enforces_single_active_and_migration_is_idempotent(database, plan):
    nutrition.ensure_schema()
    first = nutrition.save_draft(1, plan)
    nutrition.activate_draft(1, first['id'])
    with pytest.raises(sqlite3.IntegrityError):
        with connection.get_db() as conn:
            conn.execute("INSERT INTO nutrition_plans (trainee_id, plan_json, status) VALUES (1, '{}', 'active')")
    with connection.get_db_ro() as conn:
        assert conn.execute('SELECT COUNT(*) FROM trainees').fetchone()[0] == 2


@pytest.mark.parametrize('as_string', [False, True])
def test_coach_tools_save_load_revise_approve_history(database, plan, as_string):
    payload = json.dumps(plan) if as_string else plan
    saved = json.loads(tools.save_nutrition_plan.invoke({'trainee_id': 1, 'plan': payload}))
    assert saved['approval_required'] is True
    plan_id = saved['nutrition_plan']['id']
    loaded = json.loads(tools.get_nutrition_plan.invoke({'trainee_id': 1}))
    assert loaded['active_plan'] is None and loaded['draft']['id'] == plan_id
    approved = json.loads(tools.approve_nutrition_plan.invoke({'trainee_id': 1, 'plan_id': plan_id}))
    assert approved['nutrition_plan']['status'] == 'active'
    revised = json.loads(tools.revise_nutrition_plan.invoke({'trainee_id': 1, 'plan_id': plan_id,
        'plan': {**plan, 'notes': 'Revision'}, 'change_description': 'Requested change'}))
    assert revised['nutrition_plan']['status'] == 'draft'
    assert len(json.loads(tools.get_nutrition_plan_history.invoke({'trainee_id': 1,
        'plan_id': revised['nutrition_plan']['id']}))['revisions']) == 1


def test_tool_errors_are_machine_readable(database, plan):
    result = json.loads(tools.save_nutrition_plan.invoke({'trainee_id': 999, 'plan': plan}))
    assert result['error'] and result['retryable'] is False


@pytest.mark.parametrize('text', ['show me my nutrition plan', 'show me my meal plan', 'show me diet details'])
def test_nutrition_requests_do_not_trigger_workout_draft(text):
    assert routing.draft_action(text, {'stage': 'structure'}) is None
    assert routing.draft_action(text, {'stage': 'week1'}) is None


def test_nutrition_approval_does_not_trigger_workout_synthesis():
    assert main._draft_response(1, 'yes', 'Would you like to activate this nutrition plan?') is None


def test_nutrition_tools_registered_with_coach():
    names = {t.name for t in agent.COACH_TOOLS}
    assert {'save_nutrition_plan', 'get_nutrition_plan', 'revise_nutrition_plan',
        'approve_nutrition_plan', 'get_nutrition_plan_history'} <= names

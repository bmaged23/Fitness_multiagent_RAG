from datetime import date
import json
from pathlib import Path
from streamlit.testing.v1 import AppTest
from app.components.plan_views import default_week, format_chat_reply
from fitness_multiagent_rag.db import crud, nutrition, connection


def test_week_summary_formats_headers_and_bullets():
    text = 'Week 1 — Full Body: Day 1 — Full Body A: • Bench Press: 3×10, rest 90s • Row: 3×10 Day 2: REST'
    formatted = format_chat_reply(text)
    assert '### Week 1 — Full Body' in formatted
    assert '#### Day 1 — Full Body A' in formatted
    assert '\n- Bench Press:' in formatted
    assert '\n- Row:' in formatted
    assert '#### Day 2: REST' in formatted


def test_week_estimate_bounds_and_manual_selection():
    plan = {'weeks': [{'week': i} for i in range(1, 9)]}
    assert default_week(plan, '2026-10-01T00:00:00Z', date(2026, 10, 10)) == 2
    assert default_week(plan, '2026-10-01', date(2027, 1, 1)) == 8
    assert default_week(plan, None) == 1


def test_plan_history_is_scoped_and_ui_renders_tables(monkeypatch, tmp_path):
    monkeypatch.setattr(connection, 'SQLITE_DB_PATH', tmp_path / 'plans.db')
    root = Path(__file__).parents[1]
    with connection.get_db() as conn:
        conn.executescript((root / 'db/schema.sql').read_text())
        conn.executemany('INSERT INTO trainees (id, name) VALUES (?, ?)', [(1, 'First'), (2, 'Second')])
        plan = {'goal': 'Bodybuilding', 'difficulty': 'Beginner', 'duration_weeks': 8,
            'weeks': [{'week': 1, 'days': [{'day': 1, 'focus': 'Full Body A', 'exercises': [{
                'name': 'Bench Press', 'sets': 3, 'reps': 10, 'rest_seconds': 90, 'equipment': 'Full Gym'}]},
                {'day': 2, 'rest_day': True, 'exercises': []}]}]}
        conn.execute("INSERT INTO plans (trainee_id, plan_json, status) VALUES (1, ?, 'archived')", (json.dumps(plan),))
        conn.execute("INSERT INTO plans (trainee_id, plan_json) VALUES (1, ?)", (json.dumps(plan),))
        conn.execute("INSERT INTO plans (trainee_id, plan_json) VALUES (2, '{}')")
        conn.execute("INSERT INTO plan_revisions (plan_id, revision_number, previous_plan_json, new_plan_json, triggered_by) VALUES (2, 1, ?, ?, 'user_request')", (json.dumps(plan), json.dumps(plan)))
    assert len(crud.get_trainee_plans(1)) == 2
    assert len(crud.get_trainee_plans(2)) == 1
    food = {'goal': 'Test', 'daily_targets': {'calories_kcal': 2000, 'protein_g': 100,
        'carbohydrate_g': 250, 'fat_g': 67}, 'meals': [{'name': 'Breakfast',
        'foods': [{'name': 'Oats', 'portion': '50 g'}]}], 'dietary_preferences': [],
        'allergies': [], 'restrictions': [], 'start_date': '2026-10-10', 'review_date': '2026-11-10'}
    first = nutrition.save_draft(1, food)
    nutrition.activate_draft(1, first['id'])
    next_plan = nutrition.save_draft(1, {**food, 'notes': 'Updated'}, 'Update', first['id'])
    nutrition.activate_draft(1, next_plan['id'])
    assert len(nutrition.list_plans(1)) == 2
    assert nutrition.list_plans(2) == []
    app = AppTest.from_string('from app.components.plan_views import render_my_plans\nrender_my_plans(1, {})').run(timeout=30)
    assert not app.exception
    assert len(app.dataframe) >= 3
    assert len(app.metric) >= 4
    assert any('Revision 1' in expander.label for expander in app.expander)
    saved = next(select for select in app.selectbox if select.label == 'Saved workout programs')
    assert len(saved.options) == 2

    # Saving a revision outside this rendered page must appear on refresh.
    updated = json.loads(json.dumps(plan))
    updated['weeks'][0]['days'][0]['exercises'][0]['name'] = 'Updated Bench Press'
    with connection.get_db() as conn:
        conn.execute('UPDATE plans SET plan_json = ? WHERE id = 2', (json.dumps(updated),))
    active_food = nutrition.get_plan(1)
    with connection.get_db() as conn:
        changed = {**active_food['plan_json'], 'notes': 'Latest nutrition update'}
        conn.execute('UPDATE nutrition_plans SET plan_json = ? WHERE id = ?',
                     (json.dumps(changed), active_food['id']))
    # AppTest cannot serialize widgets inside stateful tabs yet; emulate the
    # rerun that tab navigation and Refresh plans both request.
    app = AppTest.from_string('from app.components.plan_views import render_my_plans\nrender_my_plans(1, {})').run(timeout=30)
    assert not app.exception
    assert any('Updated Bench Press' in str(table.value) for table in app.dataframe)
    assert any('Latest nutrition update' in message.value for message in app.markdown)

import pytest
from fitness_multiagent_rag.agents.coach import main, routing
from fitness_multiagent_rag.db import nutrition


@pytest.mark.parametrize('text', ['show me the neutration plan', 'show me the nueteration plan',
    'show me the nutrition plan'])
def test_nutrition_spelling_never_uses_workout_shortcut(text):
    assert routing.plan_topic(text) == 'nutrition'
    assert routing.draft_action(text, {'stage': 'week1'}) is None
    assert routing.classify_intent(text, False) == 'nutrition_plan'


def test_details_follow_up_keeps_nutrition_topic():
    previous = 'Here is your current vegan bodybuilding nutrition plan (active).'
    assert routing.draft_action('i want the plan in details', {'stage': 'week1'}, previous) is None
    assert routing.classify_intent('i want the plan in details', False, previous_reply=previous) == 'nutrition_plan'
    assert routing.plan_topic('show me my workout', previous) == 'workout'


def test_exact_user_sequence_displays_portions_without_workout(monkeypatch):
    record = {'status': 'active', 'plan_json': {'goal': 'Bodybuilding', 'daily_targets': {
        'calories_kcal': 2000, 'protein_g': 100, 'carbohydrate_g': 250, 'fat_g': 67},
        'meals': [{'name': 'Breakfast', 'foods': [{'name': 'Oats', 'portion': '50 g',
            'alternatives': ['Rice']}]}], 'dietary_preferences': ['Vegan'], 'allergies': [],
        'restrictions': [], 'start_date': '2026-10-10', 'review_date': '2026-11-10'}}
    monkeypatch.setattr(nutrition, 'get_plan', lambda trainee_id, status='active': record if status == 'active' else None)
    previous = ''
    for text in ['show me the neutration plan', 'show me the nutrition plan', 'i want the plan in details']:
        response = main._nutrition_response(2, text, previous)
        assert 'Oats: 50 g' in response
        assert 'Alternatives: Rice' in response
        assert 'Week 1' not in response
        previous = response


def test_approval_and_revisions_still_reach_coach():
    previous = 'Would you like to activate this nutrition plan?'
    assert main._nutrition_response(2, 'yes', previous) is None
    assert main._nutrition_response(2, 'change my meal plan details', previous) is None

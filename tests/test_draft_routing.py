import json
from types import SimpleNamespace
import pytest
from fitness_multiagent_rag.agents.coach import main, routing
from fitness_multiagent_rag.agents.designer import drafts, agent


@pytest.mark.parametrize('user_text', ['show me the program', 'show me the program details',
    'show me the program in details please', 'yes', 'okay'])
def test_structure_view_request_continues_week_one(user_text):
    assert routing.draft_action(user_text, {'stage': 'structure'}) == 'generate_week1'


def test_existing_week_one_is_shown_without_regeneration(monkeypatch):
    monkeypatch.setattr(drafts, 'read_draft', lambda _: {'stage': 'week1', 'week1_summary': 'Actual exercises'})
    monkeypatch.setattr(agent, 'synthesize_week_one', SimpleNamespace(invoke=lambda *args, **kwargs: pytest.fail('Regenerated')))
    assert 'Actual exercises' in main._draft_response(2, 'show me the program details')


def test_details_request_uses_stored_structure(monkeypatch):
    monkeypatch.setattr(drafts, 'read_draft', lambda _: {'stage': 'structure',
        'structure_json': '{"approved":true}', 'chunks': [{'text': 'reference'}]})
    def generate(args):
        assert args['structure_json'] == '{"approved":true}'
        assert args['chunks_json'] == [{'text': 'reference'}]
        return json.dumps({'week1_summary': 'Workout details'})
    monkeypatch.setattr(agent, 'synthesize_week_one', SimpleNamespace(invoke=generate))
    assert 'Workout details' in main._draft_response(2, 'show me the program details')


@pytest.mark.parametrize('user_text', ['create a new program', 'change my workout', 'what is protein', 'save the plan'])
def test_other_requests_keep_normal_routing(user_text):
    assert routing.draft_action(user_text, {'stage': 'structure'}) is None


@pytest.mark.parametrize('text', ['save the workout plan', 'Looks good. Please save this workout program so I can find it in My plans.'])
def test_week_one_save_routes_to_stored_draft(text):
    assert routing.draft_action(text, {'stage': 'week1'}) == 'save_week1'

@pytest.mark.parametrize('text', ["don't save the plan", 'do not save the workout', 'wait before saving the program', 'change my workout'])
def test_week_one_save_requires_explicit_approval(text):
    assert routing.draft_action(text, {'stage': 'week1'}) is None


def test_approved_workout_saves_stored_validated_data(monkeypatch):
    stored = {'weeks': [{'week': 1, 'days': []}]}
    monkeypatch.setattr(drafts, 'read_draft', lambda _: {'stage': 'week1', 'week1_plan_json': json.dumps(stored)})
    def validate(args):
        assert json.loads(args['plan_json']) == stored
        assert args['run_critique'] is False
        return json.dumps({'passed': True, 'plan_json': stored})
    calls = []
    def save(args):
        calls.append(args)
        return json.dumps({'plan_id': 5})
    monkeypatch.setattr(agent, 'validate_and_critique', SimpleNamespace(invoke=validate))
    monkeypatch.setattr(agent, 'save_plan', SimpleNamespace(invoke=save))
    assert 'is saved' in main._draft_response(2, 'save the workout plan')
    assert calls[0]['plan_json'] == stored
    assert calls[0]['is_revision'] is False


def test_invalid_draft_is_not_saved(monkeypatch):
    monkeypatch.setattr(drafts, 'read_draft', lambda _: {'stage': 'week1', 'week1_plan_json': '{}'})
    monkeypatch.setattr(agent, 'validate_and_critique', SimpleNamespace(invoke=lambda _: json.dumps({'passed': False, 'failures': ['Equipment mismatch']})))
    monkeypatch.setattr(agent, 'save_plan', SimpleNamespace(invoke=lambda _: pytest.fail('Invalid draft saved')))
    assert 'Equipment mismatch' in main._draft_response(2, 'save the workout plan')

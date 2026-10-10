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

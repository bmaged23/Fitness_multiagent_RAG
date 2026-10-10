import json
from types import SimpleNamespace
import pytest
from fitness_multiagent_rag.agents.designer import agent


@pytest.mark.parametrize('serialize', [False, True])
def test_flat_and_nested_evidence_preserves_arrays(serialize):
    chunk = {'title': 'Dumbbells', 'text': 'Beginner workout', 'goal': ['Bodybuilding'],
             'equipment': ['Dumbbell Only'], 'collection': 'fitness_programs'}
    for value in [[chunk], [{'collection': 'fitness_programs', 'chunks': [chunk]}]]:
        raw = json.dumps(value) if serialize else value
        assert agent._flatten_retriever_chunks(raw) == [chunk]


def test_malformed_evidence_is_an_error():
    with pytest.raises(ValueError):
        agent._flatten_retriever_chunks('broken [{"title":"workout"}] trailing')


@pytest.mark.parametrize('serialize', [False, True])
def test_structure_tool_accepts_native_and_serialized_evidence(monkeypatch, serialize):
    chunk = {'title': 'Dumbbells', 'text': 'Beginner workout', 'goal': ['Bodybuilding']}
    monkeypatch.setattr(agent.crud, 'get_trainee_by_id', lambda _: object())
    captured = []
    monkeypatch.setattr(agent, "save_draft", lambda *args: None)
    structure = SimpleNamespace(day_schedule=['Full body'], deload_weeks=[], split_type='Full body',
        days_per_week=3, duration_weeks=4, rep_style='Moderate', weight_increment_kg_per_week=1,
        rationale='Adapted from retrieved evidence', model_dump_json=lambda: '{}')
    def propose(chunks, trainee, request):
        captured.extend(chunks)
        return structure
    monkeypatch.setattr(agent, 'propose_structure', propose)
    raw = json.dumps([chunk]) if serialize else [chunk]
    result = json.loads(agent.propose_plan_structure.invoke({
        'chunks_json': raw, 'trainee_id': 2, 'request_text': 'give me a program'}))
    assert 'structure_json' in result
    assert captured == [chunk]

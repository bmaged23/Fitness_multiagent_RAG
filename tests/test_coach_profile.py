import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from fitness_multiagent_rag.agents.coach import agent, main
from fitness_multiagent_rag.db.models import Trainee


@pytest.mark.parametrize('equipment', [['Garage Gym'], '["Garage Gym"]'])
def test_profile_accepts_list_and_json_string(monkeypatch, equipment):
    trainee = Trainee(name='Test', id=2)
    saved = []
    monkeypatch.setattr(agent.crud, 'get_trainee_by_id', lambda _: trainee)
    monkeypatch.setattr(agent.crud, 'update_trainee', saved.append)
    result = json.loads(agent.update_fitness_profile.invoke({
        'trainee_id': 2, 'equipment_available': equipment,
        'goal': 'Bodybuilding', 'fitness_level': 'Beginner'}))
    assert result['updated_fields'] == ['goal', 'fitness_level', 'equipment_available']
    assert saved[0].equipment_available == ['Garage Gym']


def test_invalid_equipment_does_not_write(monkeypatch):
    monkeypatch.setattr(agent.crud, 'get_trainee_by_id', lambda _: Trainee(name='Test', id=2))
    monkeypatch.setattr(agent.crud, 'update_trainee', lambda _: pytest.fail('Unexpected write'))
    result = json.loads(agent.update_fitness_profile.invoke({
        'trainee_id': 2, 'equipment_available': ['unknown']}))
    assert result['error']


def test_stream_stops_identical_failed_calls(capsys):
    class FakeAgent:
        def stream(self, *args, **kwargs):
            for i in range(3):
                if i == 2:
                    pytest.fail('Must stop after the repeated failure')
                yield {'model': {'messages': [AIMessage(content='', tool_calls=[{
                    'id': str(i), 'name': 'update_fitness_profile', 'args': {'trainee_id': 2}}])]}}
                yield {'tools': {'messages': [ToolMessage(content='Error invoking tool: bad input',
                    name='update_fitness_profile', tool_call_id=str(i))]}}
    reply, messages, _ = main._stream_turn(FakeAgent(), [])
    assert 'failed repeatedly' in reply
    assert messages[-1].content == reply
    assert 'Error invoking tool: bad input' in capsys.readouterr().out

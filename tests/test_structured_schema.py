from langchain_core.messages import HumanMessage
from fitness_multiagent_rag.llm import client
from fitness_multiagent_rag.schemas.plan_schema import Day


def test_native_model_receives_required_types_without_mutating_history(monkeypatch):
    messages = [HumanMessage(content='Generate a rest day')]
    class FakeModel:
        def with_structured_output(self, schema, method):
            assert schema is Day
            return self
        def invoke(self, supplied):
            assert supplied[0] is messages[0]
            assert '"day"' in supplied[-1].content
            assert '"integer"' in supplied[-1].content
            assert '"focus"' in supplied[-1].content
            assert '"required"' in supplied[-1].content
            return Day(day=7, focus='REST', rest_day=True)
    monkeypatch.setattr(client, 'get_model', lambda: FakeModel())
    assert client.structured_chat(messages, Day).day == 7
    assert len(messages) == 1

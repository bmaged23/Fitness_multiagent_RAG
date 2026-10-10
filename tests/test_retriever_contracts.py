"""Offline regression tests for Retriever tool/helper contracts."""
import json
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from langchain_core.messages import ToolMessage

from fitness_multiagent_rag.agents.retriever import agent, coverage, query_rewrite
from fitness_multiagent_rag.utils.tool_errors import tool_result_error


def test_decomposition_preserves_dataclasses_and_caps_results(monkeypatch):
    monkeypatch.setattr(query_rewrite, 'structured_chat', lambda messages, schema:
        query_rewrite.DecomposeOutput(needs=[query_rewrite.NeedSchema(
            description='dumbbell exercises', query_text='beginner dumbbells',
            collection='fitness_exercises', equipment=['Dumbbell Only'], top_k=10)]))
    result = json.loads(agent.decompose_query.invoke({'request': 'build muscle'}))
    assert result[0]['collection'] == 'fitness_exercises'
    assert result[0]['equipment'] == ['Dumbbell Only']
    assert result[0]['top_k'] == 3


def test_rewrite_uses_need_and_returns_json(monkeypatch):
    def reply(messages, schema):
        assert 'beginner dumbbells' in messages[-1].content
        assert 'no results' in messages[-1].content
        assert 'wrong equipment' in messages[-1].content
        return query_rewrite.RewriteOutput(sub_queries=['dumbbell hypertrophy'])
    monkeypatch.setattr(query_rewrite, 'structured_chat', reply)
    assert json.loads(agent.rewrite_search_query.invoke({
        'query': 'beginner dumbbells', 'reason': 'wrong equipment'})) == ['dumbbell hypertrophy']


def test_relevance_with_nonempty_chunks_and_empty_pool(monkeypatch):
    def reply(messages, schema):
        assert 'build muscle' in messages[-1].content
        assert 'dumbbell rows' in messages[-1].content
        return coverage.RelevanceOutput(relevant=True)
    monkeypatch.setattr(coverage, 'structured_chat', reply)
    assert json.loads(agent.validate_chunk_relevance.invoke({
        'query': 'build muscle', 'chunks': '[{"text":"dumbbell rows"}]'})) == {'relevant': True}
    assert json.loads(agent.validate_chunk_relevance.invoke({
        'query': 'build muscle', 'chunks': '[]'})) == {'relevant': False}


def test_coverage_serializes_dataclass_and_reports_empty_evidence(monkeypatch):
    monkeypatch.setattr(coverage, 'structured_chat', lambda messages, schema:
        coverage.CoverageOutput(satisfied=['build muscle'], gaps=[], confident=True))
    assert json.loads(agent.check_retrieval_coverage.invoke({
        'request': 'build muscle', 'chunks': '[{"text":"rows"}]'}))['confident'] is True
    assert json.loads(agent.check_retrieval_coverage.invoke({
        'request': 'build muscle', 'chunks': '[]'})) == {
            'satisfied': [], 'gaps': ['build muscle'], 'confident': False}


def test_search_config_budget_isolation_and_cleanup(monkeypatch):
    monkeypatch.setattr(agent, 'embed_one', lambda query: [0.1])
    monkeypatch.setattr(agent.qdrant, 'search', lambda **kwargs: [])
    assert 'Missing retriever_request_id' in agent.search_programs.invoke({'query': 'rows'})['error']
    ids = [str(uuid4()), str(uuid4())]
    try:
        config = {'configurable': {'retriever_request_id': ids[0]}}
        for attempt in range(agent.MAX_SEARCH_ATTEMPTS[agent.QDRANT_PROGRAMS_COLLECTION]):
            assert agent.search_programs.invoke({'query': 'rows'}, config=config)['attempt'] == attempt + 1
        assert agent.search_programs.invoke({'query': 'rows'}, config=config)['search_limit_reached']
        assert agent.search_exercises.invoke({'query': 'rows'}, config=config)['attempt'] == 1
        assert agent.search_programs.invoke({'query': 'rows'}, config={
            'configurable': {'retriever_request_id': ids[1]}})['attempt'] == 1
    finally:
        for request_id in ids:
            agent._release_search_budget(request_id)
    assert all(request_id not in agent._search_counts for request_id in ids)


@pytest.mark.parametrize('output', [
    {'error': 'backend failed'}, '{"error":"backend failed"}',
    ToolMessage(content='{"error":"backend failed"}', tool_call_id='1'),
    ToolMessage(content='failed', tool_call_id='1', status='error'),
    'Invalid tool input: ValueError: bad JSON',
])
def test_returned_errors_are_detected(output):
    assert tool_result_error(output)


@pytest.mark.parametrize('output', ['[]', {'chunks': []}, '{"relevant":false}'])
def test_empty_or_irrelevant_results_are_not_errors(output):
    assert tool_result_error(output) is None


@pytest.mark.parametrize('filename', ['test_coach.py', 'test_retriever.py', 'test_designer.py'])
def test_profiler_marks_returned_errors_failed(filename):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location('profiler_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    profiler = module.AgentProfiler()
    run_id = uuid4()
    profiler.on_tool_start({'name': 'search_programs'}, '{}', run_id=run_id)
    profiler.on_tool_end(ToolMessage(content='{"error":"backend failed"}', tool_call_id='1'), run_id=run_id)
    assert profiler.records[-1]['status'] == 'FAILED'


def test_malformed_chunks_return_machine_readable_errors():
    assert json.loads(agent.validate_chunk_relevance.invoke({
        'query': 'rows', 'chunks': 'invalid'}))['error']


def test_empty_retrieval_blocks_structure_generation(monkeypatch):
    from fitness_multiagent_rag.agents.designer import agent as designer
    monkeypatch.setattr(designer.crud, 'get_trainee_by_id', lambda trainee_id: object())
    def unexpected(*args, **kwargs):
        pytest.fail('Structure synthesis must not run without retrieved evidence')
    monkeypatch.setattr(designer, 'propose_structure', unexpected)
    result = json.loads(designer.propose_plan_structure.invoke({
        'chunks_json': '[]', 'trainee_id': 1, 'request_text': 'build muscle'}))
    assert result['error']
    assert result['retryable'] is False


@pytest.mark.parametrize('runner', ['coach', 'retriever'])
def test_runners_provide_request_config_and_release_budget(monkeypatch, runner):
    if runner == 'coach':
        from fitness_multiagent_rag.agents.coach import main
    else:
        from fitness_multiagent_rag.agents.retriever import main
    captured = {}
    class FakeAgent:
        def stream(self, inputs, config, stream_mode):
            captured.update(config)
            request_id = config['configurable']['retriever_request_id']
            agent._acquire_search_slot(request_id, agent.QDRANT_PROGRAMS_COLLECTION)
            raise RuntimeError('stream failed')
            yield
    with pytest.raises(RuntimeError, match='stream failed'):
        if runner == 'coach':
            main._stream_turn(FakeAgent(), [])
        else:
            monkeypatch.setattr(main, 'build_retriever_agent', lambda: FakeAgent())
            main.run('build muscle')
    assert captured['recursion_limit'] > 0
    assert captured['configurable']['retriever_request_id'] not in agent._search_counts

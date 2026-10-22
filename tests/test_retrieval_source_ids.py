"""Source provenance must survive vector retrieval and agent evidence trimming."""
from types import SimpleNamespace
from fitness_multiagent_rag.vectorstore import qdrant_client
from fitness_multiagent_rag.agents.retriever.agent import _slim


def test_qdrant_point_id_is_authoritative_and_retained(monkeypatch):
    hit = SimpleNamespace(id='actual-point-id', score=.9,
                          payload={'text':'Evidence','title':'Synthetic source',
                                   'chunk_id':'stale-payload-id','collection':'wrong'})
    client = SimpleNamespace(query_points=lambda **kwargs: SimpleNamespace(points=[hit]))
    monkeypatch.setattr(qdrant_client, '_client', client)
    results = qdrant_client.search('fitness_programs', [0.0]*1024)
    assert results[0]['chunk_id'] == 'actual-point-id'
    assert results[0]['collection'] == 'fitness_programs'
    evidence = _slim(results, 'fitness_programs', 500)
    assert evidence[0]['chunk_id'] == 'actual-point-id'
    assert evidence[0]['text'] == 'Evidence'


def test_exercise_name_is_preserved_as_display_title():
    evidence=_slim([{'chunk_id':'exercise-id','exercise_name':'Dumbbell Row','text':'Evidence'}],
                   'fitness_exercises',500)
    assert evidence[0]['title']=='Dumbbell Row'
    assert evidence[0]['exercise_name']=='Dumbbell Row'

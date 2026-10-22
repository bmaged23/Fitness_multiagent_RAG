from copy import deepcopy
import pytest
from scripts.evaluation.validate_dataset import load_cases, validate, summary
from scripts.evaluation.retrieval_metrics import score_retrieval


def test_dataset_has_distinct_cases_and_fixed_splits():
    cases = load_cases()
    assert validate(cases) == []
    result = summary(cases)
    assert result['scenarios'] == 100
    assert result['multi_turn_scenarios'] >= 20
    assert result['user_messages'] > 120


def test_duplicate_scenarios_are_rejected():
    cases = deepcopy(load_cases())
    cases[1]['turns'] = cases[0]['turns']
    assert any('Duplicate' in e for e in validate(cases))


def test_unreviewed_labels_are_rejected():
    cases = deepcopy(load_cases())
    cases[0]['reference_status']='pending_corpus_review'
    cases[0]['expected']['relevance_labels'] = [{'chunk_id':'invented'}]
    assert any('require reviewed' in e for e in validate(cases))


def test_missing_labels_are_unscored_not_zero():
    result = score_retrieval([], [])
    assert result['status'] == 'unscored_missing_labels'
    assert result['recall_at_k'] is None


def test_retrieval_metrics_respect_rank_collection_and_duplicates():
    labels = [{'collection':'fitness_exercises','chunk_id':'a','relevant':True},
              {'collection':'fitness_exercises','chunk_id':'b','relevant':True}]
    docs = [{'collection':'fitness_programs','chunk_id':'a'},
            {'collection':'fitness_exercises','chunk_id':'a'},
            {'collection':'fitness_exercises','chunk_id':'a'}]
    result = score_retrieval(docs, labels)
    assert result['precision_at_k'] == pytest.approx(1/3)
    assert result['recall_at_k'] == .5
    assert result['mrr_at_k'] == .5


def test_no_positive_reference_is_not_scored_as_perfect_recall():
    assert score_retrieval([], [{'collection':'fitness_programs','chunk_id':'x','relevant':False}])['recall_at_k'] is None


def test_invalid_k_is_rejected():
    with pytest.raises(ValueError):
        score_retrieval([], [], k=0)

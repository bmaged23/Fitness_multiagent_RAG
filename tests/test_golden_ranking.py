import pytest
from scripts.evaluation.golden_ranking import ranking_metrics


def doc(id):return {'collection':'fitness_programs','chunk_id':id}

def refs():return [{**doc(id),'relevance_grade':3} for id in ['a','b']]


def test_equal_grade_reference_order_is_not_arbitrary():
    assert ranking_metrics([doc('a'),doc('b')],refs())['ndcg_at_5']==1
    assert ranking_metrics([doc('b'),doc('a')],refs())['ndcg_at_5']==1


def test_lower_rank_reduces_score_and_duplicates_never_earn_extra_credit():
    good=ranking_metrics([doc('a'),doc('b')],refs())
    lower=ranking_metrics([doc('wrong'),doc('a'),doc('b')],refs())
    duplicate=ranking_metrics([doc('a'),doc('a')],refs())
    assert 0<lower['ndcg_at_5']<good['ndcg_at_5']
    assert duplicate['recall_at_5']==.5
    assert duplicate['matched_sources']==1


def test_wrong_collection_does_not_match_same_id():
    result=ranking_metrics([{'collection':'fitness_exercises','chunk_id':'a'}],refs())
    assert result['ndcg_at_5']==0


def test_missing_second_source_is_visible():
    result=ranking_metrics([doc('a')],refs())
    assert result['recall_at_5']==.5
    assert result['all_required_sources_found']==0

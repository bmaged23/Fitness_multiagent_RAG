import pytest
from scripts.evaluation.llm_judge import parse_judgment


def test_judge_cannot_invent_or_duplicate_evidence_ids():
    with pytest.raises(ValueError):
        parse_judgment('{"documents":[{"chunk_id":"invented","relevant":true,"reason":"Looks good"}]}',['actual'])
    with pytest.raises(ValueError):
        parse_judgment('{"documents":[{"chunk_id":"a","relevant":true,"reason":"Evidence"},{"chunk_id":"a","relevant":true,"reason":"Again"}]}',['a','b'])


def test_valid_judgment_retains_reason_and_boolean():
    result=parse_judgment('{"documents":[{"chunk_id":"actual","relevant":false,"reason":"Advanced request but source is Beginner"}]}',['actual'])
    assert result.documents[0].relevant is False
    assert 'Beginner' in result.documents[0].reason

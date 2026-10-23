import json
import pytest
from scripts.evaluation import golden_answer_metrics as metrics


def test_generation_and_faithfulness_do_not_receive_gold(monkeypatch):
    seen=[]
    def fake(system,payload,model,max_tokens=2400):
        seen.append(payload)
        return {'text':'{"claims":[]}' if system==metrics.FAITHFULNESS_SYSTEM else 'An answer',
                'wall_seconds':0,'usage':{}}
    monkeypatch.setattr(metrics,'cloud_chat',fake)
    metrics.answer_question('Question',[{'chunk_id':'retrieved'}],'answer-model')
    result=metrics.judge_faithfulness('Question',[{'chunk_id':'retrieved'}],'An answer','judge-model')
    assert all('reference_answer' not in payload and 'reference_facts' not in payload for payload in seen)
    assert result['scores']['faithfulness'] is None


def test_missing_facts_reduce_completeness_and_f1(monkeypatch):
    def fake(*args,**kwargs):
        return {'text':json.dumps({'facts':[{'fact_id':'f01','verdict':'correct','reason':'Matches'},
                                          {'fact_id':'f02','verdict':'missing','reason':'Omitted'}],
                                  'relevance':4,'relevance_reason':'On topic'}),'wall_seconds':0,'usage':{}}
    monkeypatch.setattr(metrics,'cloud_chat',fake)
    result=metrics.judge_correctness('Question','Reference',[{'value':1},{'value':2}],'Partial answer','judge')
    assert result['scores']['completeness']==.5
    assert result['scores']['correctness_f1']<1


def test_invalid_judge_evidence_retries_but_valid_low_score_does_not(monkeypatch):
    calls=[]
    monkeypatch.setattr(metrics.time,'sleep',lambda _:None)
    def fake(*args,**kwargs):
        calls.append(1)
        claim={'claim':'Some claim','supported':len(calls)==1,
               'source_ids':['invented'] if len(calls)==1 else [],'reason':'Evidence check'}
        return {'text':json.dumps({'claims':[claim]}),'wall_seconds':0,
                'usage':{'prompt_eval_count':10,'eval_count':5}}
    monkeypatch.setattr(metrics,'cloud_chat',fake)
    result=metrics.judge_faithfulness('Question',[{'chunk_id':'actual'}],'Answer','judge')
    assert len(calls)==2
    assert result['scores']['faithfulness']==0
    assert result['attempt_count']==2
    assert result['usage']['prompt_eval_count']==20
    assert result['attempt_log'][0]['status']=='invalid_or_transient_error'


def test_persistently_invalid_judgment_fails_after_three_attempts(monkeypatch):
    calls=[]
    monkeypatch.setattr(metrics.time,'sleep',lambda _:None)
    def fake(*args,**kwargs):
        calls.append(1)
        return {'text':'not JSON','wall_seconds':0,'usage':{}}
    monkeypatch.setattr(metrics,'cloud_chat',fake)
    with pytest.raises(ValueError):
        metrics.judge_faithfulness('Question',[],'Answer','judge')
    assert len(calls)==3

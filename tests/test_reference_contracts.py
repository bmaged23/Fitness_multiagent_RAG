from copy import deepcopy
from scripts.evaluation.validate_dataset import load_cases,validate
from scripts.evaluation.reference_scoring import score_reference_case
from scripts.evaluation.validate_references import validate_sources
from scripts.evaluation.curate_references import canonical_hash


def test_all_scenarios_have_explicit_reference_policy():
    cases=load_cases()
    assert validate(cases)==[]
    assert sum(bool(c['expected']['relevance_labels']) for c in cases)==48
    assert all(c['expected'].get('retrieval_policy') for c in cases)
    absence=next(c for c in cases if c['id']=='unsupported-01')
    assert absence['reference_status']=='absence_checked'
    assert absence['expected']['relevance_labels']==[]


def test_unjudged_document_is_unknown_in_partial_pool():
    case={'expected':{'collections':['fitness_programs'],'reference_scope':'curated_partial_pool',
          'relevance_labels':[{'collection':'fitness_programs','chunk_id':'known','relevant':True}]}}
    score=score_reference_case(case,[{'collection':'fitness_programs','chunk_id':'another-valid-possible-source'}])['collections']['fitness_programs']
    assert score['unjudged_returned_count']==1
    assert score['precision_among_judged'] is None
    assert 'precision_at_k' not in score


def test_exhaustive_metadata_complement_has_defined_negatives():
    case={'expected':{'collections':['fitness_programs'],'reference_scope':'exhaustive_recorded_metadata',
          'relevance_labels':[{'collection':'fitness_programs','chunk_id':'six-weeks','relevant':True}]}}
    score=score_reference_case(case,[{'collection':'fitness_programs','chunk_id':'twelve-weeks'}])['collections']['fitness_programs']
    assert score['precision_at_k']==0
    assert score['scope']=='recorded_metadata_only'


def test_absent_title_case_does_not_get_perfect_score_for_unrelated_evidence():
    case={'expected':{'reference_scope':'exhaustive_exact_title_absence',
                     'reference_rule':{'exact_title_casefold':'absent'}}}
    assert score_reference_case(case,[])['abstained'] is True
    assert score_reference_case(case,[{'chunk_id':'unrelated'}])['abstained'] is False


def test_reference_fingerprint_detects_modified_corpus():
    doc={'collection':'fitness_programs','chunk_id':'id','title':'Original','text':'Source'}
    ref={'collection':'fitness_programs','chunk_id':'id','document_sha256':canonical_hash(doc),
         'source_facts':{'title':'Original'},'relevant':True}
    case={'id':'synthetic','expected':{'relevance_labels':[ref]}}
    assert validate_sources([case],[doc])==[]
    changed={**doc,'text':'Changed source'}
    assert any('fingerprint' in error for error in validate_sources([case],[changed]))

"""Check source identities, facts, hashes and complete metadata sets against the frozen corpus."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from scripts.evaluation.validate_dataset import DATASET,load_cases,validate
from scripts.evaluation.curate_references import canonical_hash,matches


def validate_sources(cases,corpus):
    errors=[]
    by_key={(d['collection'],d['chunk_id']):d for d in corpus}
    for case in cases:
        expected=case['expected'];labels=expected.get('relevance_labels',[])
        for ref in labels:
            key=(ref['collection'],ref['chunk_id']);source=by_key.get(key)
            if source is None:
                errors.append(f'{case["id"]}: unknown reference {key}');continue
            if canonical_hash(source)!=ref['document_sha256']:
                errors.append(f'{case["id"]}: source fingerprint changed for {key}')
            if any(source.get(k)!=v for k,v in ref['source_facts'].items()):
                errors.append(f'{case["id"]}: source facts differ for {key}')
        scope=expected.get('reference_scope')
        if scope=='exhaustive_recorded_metadata':
            wanted={(d['collection'],d['chunk_id']) for d in corpus if d['collection']=='fitness_programs' and matches(d,expected['reference_rule'])}
            actual={(r['collection'],r['chunk_id']) for r in labels if r['relevant']}
            if actual!=wanted:errors.append(f'{case["id"]}: incomplete or extra metadata references')
        if scope=='exhaustive_exact_title_absence':
            title=expected['reference_rule']['exact_title_casefold']
            if any(d.get('title','').casefold()==title for d in corpus if d['collection']=='fitness_programs'):
                errors.append(f'{case["id"]}: claimed absent title is present')
        relation=expected.get('required_source_relationship')
        if relation:
            program=by_key.get(('fitness_programs',relation['program_chunk_id']))
            exercise=by_key.get(('fitness_exercises',relation['exercise_chunk_id']))
            if not program or not exercise or program['title'] not in exercise.get('programs',[]):
                errors.append(f'{case["id"]}: invalid program/exercise relationship')
        if scope=='fixed_context_comparison':
            context=[by_key[(r['collection'],r['chunk_id'])] for r in case['initial_state']['retrieved_context']]
            minimum=min(context,key=lambda d:d['time_per_workout_min'])['chunk_id']
            if minimum!=expected['minimum_duration_chunk_id']:
                errors.append(f'{case["id"]}: context minimum is incorrect')
    return errors


def main():
    root=Path(__file__).resolve().parents[2]
    cases=load_cases();errors=validate(cases)
    manifest=json.loads(DATASET.with_suffix('.manifest.json').read_text())
    corpus=[]
    for collection,meta in manifest['corpus_snapshot']['collections'].items():
        path=root/f'.evaluation-local/corpus/{collection}.jsonl'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['sha256']:
            raise ValueError('Corpus snapshot changed; source validation stopped.')
        corpus.extend(json.loads(line) for line in path.read_text().splitlines())
    errors+=validate_sources(cases,corpus)
    result={'scenarios':len(cases),'cases_with_positive_reference_ids':sum(any(r['relevant'] for r in c['expected']['relevance_labels']) for c in cases),
            'reference_labels':sum(len(c['expected']['relevance_labels']) for c in cases),'errors':errors}
    print(json.dumps(result,indent=2))
    raise SystemExit(bool(errors))


if __name__=='__main__':main()

"""Sample source-first QA references from the audited frozen corpus, before retrieval.

The task is factual lookup of named indexed records, not fitness prescription.
Full reference contexts stay local; public references contain source identities,
structured facts and generated reference answers without raw source narratives.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import random
from collections import Counter
from scripts.evaluation.curate_references import canonical_hash

ROOT=Path(__file__).resolve().parents[2]
LOCAL=ROOT/'.evaluation-local'
PUBLIC=ROOT/'evaluation/datasets'
SEED=20261023
VERSION='fitness-corpus-qa-v1'


def valid_name(value):
    return isinstance(value,str) and 4<=len(value)<=140 and value==value.strip() and all(ord(c)>=32 for c in value) and 'http' not in value.casefold()


def eligible_program(d):
    return (valid_name(d.get('title')) and isinstance(d.get('program_length_weeks'),int)
            and 1<=d['program_length_weeks']<=52 and isinstance(d.get('time_per_workout_min'),int)
            and 5<=d['time_per_workout_min']<=180 and isinstance(d.get('equipment'),str)
            and bool(d.get('goal')) and bool(d.get('level')))


def eligible_exercise(d):
    return (valid_name(d.get('exercise_name')) and isinstance(d.get('sets_median'),int)
            and 1<=d['sets_median']<=20 and isinstance(d.get('reps_median'),int)
            and 1<=d['reps_median']<=(600 if d.get('is_time_based') else 100)
            and isinstance(d.get('is_time_based'),bool) and bool(d.get('equipment')))


def fact(doc,field,value=None,unit=None):
    return {'subject':doc.get('title',doc.get('exercise_name')),'field':field,
            'value':doc[field] if value is None else value,'unit':unit,
            'source_id':doc['chunk_id'],'collection':doc['collection']}


def expected_answer(facts):
    parts=[]
    for f in facts:
        value=', '.join(map(str,f['value'])) if isinstance(f['value'],list) else str(f['value'])
        parts.append(f"{f['subject']} — {f['field']}: {value}"+(f" {f['unit']}" if f.get('unit') else '')+'.')
    return ' '.join(parts)


def make_case(index,category,question,docs,facts):
    # All source chunks are equally necessary. Ties deliberately have no arbitrary ideal order.
    qrels=[{'collection':d['collection'],'chunk_id':d['chunk_id'],'relevance_grade':3,
            'document_sha256':canonical_hash(d)} for d in docs]
    return {'id':f'corpus-qa-{index:03d}','version':VERSION,'category':category,
            'question':question,'reference_answer':expected_answer(facts),'reference_facts':facts,
            'reference_chunks':qrels,'ideal_relevance_grades':[3]*len(qrels),
            'reference_rank_policy':'Equal grade means a tie; either order is ideal. Non-anchor records receive zero under this authoritative-record identity task.',
            'reference_contexts':[{'collection':d['collection'],'chunk_id':d['chunk_id'],
                'text':d['text'],'source_metadata':{k:v for k,v in d.items() if k not in {'text','description','programs','chunk_id','collection'}}} for d in docs],
            'provenance':{'generation':'seeded source-first template synthesis from checked source fields',
                          'seed':SEED,'independent_human_review':False,
                          'authority_scope':'Recorded corpus facts, not independently verified real-world fitness claims.'}}


def build():
    rng=random.Random(SEED)
    manifest=json.loads((LOCAL/'corpus/manifest.json').read_text())
    corpus={}
    for collection,meta in manifest['collections'].items():
        path=LOCAL/f'corpus/{collection}.jsonl'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['sha256']:
            raise ValueError('Frozen corpus changed; do not silently regenerate this version.')
        corpus[collection]=[json.loads(line) for line in path.read_text().splitlines()]
    programs=sorted([d for d in corpus['fitness_programs'] if eligible_program(d)],key=lambda d:d['chunk_id'])
    exercises=sorted([d for d in corpus['fitness_exercises'] if eligible_exercise(d)],key=lambda d:d['chunk_id'])
    programs=rng.sample(programs,80)
    single_exercises=rng.sample(exercises,30)
    used_exercises={d['chunk_id'] for d in single_exercises}
    cases=[]
    for i,d in enumerate(programs[:50]):
        variant=rng.randrange(3)
        if variant==0:
            q=f'According to the indexed program "{d["title"]}", what equipment category, program length in weeks, and session duration in minutes are listed?'
            facts=[fact(d,'equipment'),fact(d,'program_length_weeks',unit='weeks'),fact(d,'time_per_workout_min',unit='minutes/session')]
        elif variant==1:
            q=f'For the program "{d["title"]}", list its recorded training goals and experience-level tags. Report the source tags, not a personalized recommendation.'
            facts=[fact(d,'goal'),fact(d,'level')]
        else:
            q=f'Look up "{d["title"]}". Give its listed level tags, required equipment category, and total duration in weeks.'
            facts=[fact(d,'level'),fact(d,'equipment'),fact(d,'program_length_weeks',unit='weeks')]
        cases.append(make_case(len(cases)+1,'program_facts',q,[d],facts))
    for d in single_exercises:
        variant=rng.randrange(2)
        if variant==0:
            q=f'In the indexed record for "{d["exercise_name"]}", what are the median sets and median repetition-or-time value? Say whether that value is repetitions or seconds.'
            unit='seconds' if d['is_time_based'] else 'repetitions'
            facts=[fact(d,'sets_median',unit='sets'),fact(d,'reps_median',unit=unit),fact(d,'is_time_based')]
        else:
            q=f'Look up the exercise "{d["exercise_name"]}". Which equipment categories are attached to its record, and what median number of sets is recorded?'
            facts=[fact(d,'equipment'),fact(d,'sets_median',unit='sets')]
        cases.append(make_case(len(cases)+1,'exercise_facts',q,[d],facts))
    for offset in range(0,20,2):
        a,b=programs[50+offset:52+offset]
        q=f'Compare the indexed programs "{a["title"]}" and "{b["title"]}": give each program\'s equipment category and duration in weeks. Which has the shorter listed program length, or are they equal?'
        facts=[fact(d,field,unit='weeks' if field=='program_length_weeks' else None) for d in [a,b] for field in ['equipment','program_length_weeks']]
        shorter=a['title'] if a['program_length_weeks']<b['program_length_weeks'] else b['title'] if b['program_length_weeks']<a['program_length_weeks'] else 'equal'
        facts.append({'subject':'comparison','field':'shorter_listed_program','value':shorter,'unit':None,'source_id':[a['chunk_id'],b['chunk_id']],'collection':'fitness_programs'})
        cases.append(make_case(len(cases)+1,'program_comparison',q,[a,b],facts))
    for d in programs[70:80]:
        linked=[e for e in exercises if d['title'] in e.get('programs',[]) and e['chunk_id'] not in used_exercises]
        if not linked:raise ValueError(f'No eligible unused linked exercise for {d["chunk_id"]}. Change sampling version, not reference truth.')
        e=rng.choice(linked);used_exercises.add(e['chunk_id'])
        q=f'Does the indexed exercise "{e["exercise_name"]}" list "{d["title"]}" among its associated programs? Also give that program\'s listed duration in weeks and the exercise\'s median sets.'
        facts=[fact(d,'program_length_weeks',unit='weeks'),fact(e,'sets_median',unit='sets'),
               {'subject':e['exercise_name'],'field':'associated_with_program','value':d['title'],
                'unit':None,'source_id':e['chunk_id'],'collection':'fitness_exercises'}]
        case=make_case(len(cases)+1,'program_exercise_join',q,[d,e],facts)
        # Association evidence must actually be supplied to the answer/judge, not just exist in hidden labels.
        case['reference_contexts'][1]['association_evidence']={'program_title':d['title'],'present_in_exercise_programs':True}
        cases.append(case)
    rng.shuffle(cases)
    development=set(rng.sample([c['id'] for c in cases],30))
    for c in cases:c['split']='development' if c['id'] in development else 'held_out'
    validate(cases,corpus)
    output=LOCAL/'golden';output.mkdir(parents=True,exist_ok=True)
    full=output/f'{VERSION}.jsonl'
    serialized=''.join(json.dumps(c,ensure_ascii=False,separators=(',',':'))+'\n' for c in cases)
    if full.exists() and full.read_text()!=serialized:raise ValueError('Refusing to overwrite a different frozen dataset version.')
    full.write_text(serialized)
    public=PUBLIC/f'{VERSION}.references.jsonl'
    public.write_text(''.join(json.dumps({k:v for k,v in c.items() if k!='reference_contexts'},ensure_ascii=False,separators=(',',':'))+'\n' for c in cases))
    info={'version':VERSION,'seed':SEED,'size':100,'categories':dict(Counter(c['category'] for c in cases)),
          'full_dataset_sha256':hashlib.sha256(full.read_bytes()).hexdigest(),
          'public_reference_sha256':hashlib.sha256(public.read_bytes()).hexdigest(),
          'corpus':{name:{k:meta[k] for k in ['count','sha256']} for name,meta in manifest['collections'].items()},
          'audit':{'program_records':len(corpus['fitness_programs']),'exercise_records':len(corpus['fitness_exercises']),
                   'eligible_program_records':sum(eligible_program(d) for d in corpus['fitness_programs']),
                   'eligible_exercise_records':sum(eligible_exercise(d) for d in corpus['fitness_exercises']),
                   'unique_anchor_documents':len({(r['collection'],r['chunk_id']) for c in cases for r in c['reference_chunks']})},
          'reference_review':'Mechanically source-validated facts; synthetic questions/reference wording. No independent human adjudication.',
          'scope':'Named authoritative-record factual QA, comparisons and joins; does not measure open-ended fitness advice, medical truth, memory, STT or TTS.',
          'ranking':'Document-identity qrels; equally necessary sources have equal grade. nDCG uses ideal sorted grades, not arbitrary chunk order.',
          'privacy':'Full contexts remain ignored locally until corpus redistribution rights are established.'}
    (PUBLIC/f'{VERSION}.manifest.json').write_text(json.dumps(info,indent=2)+'\n')
    print(json.dumps({'count':len(cases),'categories':info['categories'],'audit':info['audit']},indent=2))


def validate(cases,corpus):
    by_id={(d['collection'],d['chunk_id']):d for rows in corpus.values() for d in rows}
    assert len(cases)==100 and len({c['id'] for c in cases})==100
    assert len({c['question'] for c in cases})==100
    seen=set()
    for c in cases:
        assert c['reference_answer'] and c['reference_chunks'] and c['reference_contexts']
        for r in c['reference_chunks']:
            key=(r['collection'],r['chunk_id']);d=by_id[key]
            assert key not in seen,'An anchor document was reused across scenarios/splits.'
            seen.add(key)
            assert r['document_sha256']==canonical_hash(d)
        for f in c['reference_facts']:
            if f['field']=='shorter_listed_program':
                a,b=[by_id[('fitness_programs',id)] for id in f['source_id']]
                wanted=a['title'] if a['program_length_weeks']<b['program_length_weeks'] else b['title'] if b['program_length_weeks']<a['program_length_weeks'] else 'equal'
                assert f['value']==wanted
            elif f['field']=='associated_with_program':
                assert f['value'] in by_id[(f['collection'],f['source_id'])]['programs']
            else:assert by_id[(f['collection'],f['source_id'])][f['field']]==f['value']
        assert c['reference_answer']==expected_answer(c['reference_facts'])


if __name__=='__main__':build()

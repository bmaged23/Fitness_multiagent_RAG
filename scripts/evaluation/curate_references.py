"""Version source-checked reference pools, separately from exhaustive metadata contracts.

No retriever outputs, similarity scores or LLM judge ratings are used here.
Curated IDs were chosen by inspecting the frozen corpus records. Semantic pools
are incomplete and AI-reviewed; they are not independently human-adjudicated gold.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'evaluation/datasets'
LOCAL=ROOT/'.evaluation-local/corpus'

BANK={
 'strength':'19c42488-8b6e-418e-8c32-2c96c0e9163f',
 'juicy':'2e0fe4d1-88be-4e3e-ba5a-a483bd429c34',
 'dumbbells':'b59c2580-cf2c-4429-b0d7-90f5e9b7e6aa',
 'golden':'1fee2085-faf4-4218-9e63-3e2ca73a3ce2',
 'intermediate':'2b2b386e-78d9-4786-913c-e8b1f35c913c',
 'advanced':'98285c85-b20a-4bea-95be-53108783acc0',
 'bodyweight':'42ff0c9c-7b5b-47ee-afe4-841010463836',
 'home':'0911572f-34c6-478b-92c4-b94b5071d00f',
 'novice':'001100e0-9e97-4f5b-b12f-f5282d1acb0c',
 'fit':'03a8ee5e-8133-4a0a-9f38-26009c2db151',
 'athlete':'2fba497d-dd7f-4f3b-bae0-7df101734869',
 'garage':'0c953fb3-19cc-4017-8b73-8d68fb30b5fd',
 'garage_no_cable':'10a96294-821a-456f-824e-8a77bf9606ef',
 'three_day':'83a7f767-62ef-43b0-8a0f-00c52db99391',
 'mwf':'ec387c52-1d27-4ace-aaa8-9c3357be50c1',
 'two_day':'377aca26-e100-4088-b5cd-31b3c8b03875',
 'six':'07555553-9547-40ad-aa0f-15cffb10e9ff',
 'twelve':'0232b109-0cf7-4189-8f89-7d645690bc45',
 'db_strength':'d6662529-9aa0-4f75-b3ba-01913ef8836c',
 'short_home':'79ad735b-bffa-40ca-b949-08bac61652c5',
 'row':'4029902e-fe88-4c99-a1c4-cc177acde293',
 'chest':'0e547625-9d16-4c6a-ba9d-81d8abecbcd4',
 'goblet':'f47222a3-4864-41e7-9742-a87dadc71117',
 'split':'d8f8744f-af67-4a2a-b97c-f94fe67e5763',
 'plank':'497c6f34-14a2-4f8b-bd0d-f07490a42cb6',
 'dead_bug':'65bd9947-5bc3-4a81-b229-55658db150ea',
 'rdl':'a634933e-1f1a-4432-a5ef-7ed39ae2b118',
 'rack_dl':'e120b877-985c-451f-bfec-17965acd6feb',
 'time_plank':'0834c90e-1e0a-41f5-8350-cbcdee4e0844',
 'time_ankle':'23e9e8e0-89ca-4995-98ab-296ffe309ff2',
 'not_beginner':'73797e3b-f3a8-41e5-b6ab-dd8e3d9ab43a',
 'not_dumbbell_only':'8f37d039-93fa-4f2b-b822-40b9e4abba5e',
 'not_bodyweight':'0f53bc81-54f4-46af-8f67-b0d4d470285d',
}
# These answer literal taxonomy/numeric questions. Completeness is with respect
# to recorded metadata, not real-world exercise suitability or description truth.
METADATA={
 'retrieval-03':{'level':['Intermediate'],'goal':['Powerlifting']},
 'retrieval-04':{'level':['Advanced'],'goal':['Bodybuilding']},
 'retrieval-06':{'level':['Novice'],'goal':['Powerbuilding']},
 'retrieval-07':{'goal':['Olympic Weightlifting']},
 'retrieval-12':{'equipment':['Full Gym'],'goal':['Muscle & Sculpting']},
 'retrieval-13':{'equipment':['Garage Gym'],'goal':['Powerbuilding']},
 'constraints-04':{'level':['Intermediate']},
 'constraints-08':{'time_per_workout_min':{'lte':45}},
 'constraints-09':{'program_length_weeks':6},
 'constraints-10':{'program_length_weeks':12,'equipment':['Full Gym'],'goal':['Bodybuilding','Muscle & Sculpting']},
 'constraints-14':{'level':['Advanced'],'time_per_workout_min':10},
 'constraints-15':{'level':['Beginner']},
 'constraints-20':{'program_length_weeks':8},
}
# Positive reference examples, inspected against source text/metadata. Other
# documents are UNJUDGED, never automatically irrelevant.
POOLS={
 'retrieval-01':(['strength','juicy'],'Beginner and Full Gym tags; source titles/descriptions explicitly concern strength/size.'),
 'retrieval-02':(['dumbbells','golden'],'Beginner-compatible Bodybuilding with Dumbbell Only metadata and no cable/machine claim in these descriptions.'),
 'retrieval-05':(['bodyweight'],'Description explicitly permits no gym equipment, with resistance bands optional.'),
 'retrieval-08':(['athlete'],'Athletics goal and description combine full-body work with cardio goals.'),
 'retrieval-09':(['bodyweight'],'Beginner/Novice tags and an explicit no-gym-equipment description support home bodyweight training.'),
 'retrieval-11':(['dumbbells','home'],'Two Beginner-tagged sources expose equipment and durations: 12 weeks/50 min and 8 weeks/30 min.'),
 'retrieval-14':(['chest'],'Named dumbbell chest/floor press with Dumbbell Only equipment; an example, not a medically validated prescription.'),
 'retrieval-15':(['goblet','split'],'Distinct squat alternatives in source records; equipment differences must be disclosed.'),
 'retrieval-16':(['row'],'Exact Dumbbell Row exercise record and its aggregated statistics.'),
 'retrieval-17':(['plank','dead_bug'],'Named bodyweight core movements; do not infer seconds when is_time_based is false.'),
 'retrieval-18':(['rdl','rack_dl'],'Two distinct named deadlift variants with source fields available for comparison.'),
 'retrieval-19':(['time_plank','time_ankle'],'Source is_time_based is true and text explicitly reports seconds rather than repetitions.'),
 'retrieval-20':(['row','plank'],'Records expose sets_median (3 and 2); these support an explanation using a concrete example, not a population-wide prescription.'),
 'retrieval-24':(['dumbbells','twelve'],'Bodybuilding program evidence describes muscle/strength goals; no sports competition requirement is imposed.'),
 'retrieval-25':(['dumbbells','home'],'Beginner-tagged program sources; distinguish recorded facts from an invented weekly schedule.'),
 'constraints-01':(['dumbbells','golden'],'Sources describe Dumbbell Only training; cable/Smith-machine description below is an explicit negative.'),
 'constraints-02':(['bodyweight','home'],'At Home evidence: no gym required; Malone requires resistance bands and that detail must be retained.'),
 'constraints-03':(['dumbbells','home'],'Beginner-compatible sources without an explicit not-for-beginners contradiction.'),
 'constraints-05':(['garage_no_cable'],'Garage Gym program; all 13 exercise names linked by program title were inspected and none names a cable movement. This does not assert the user owns every other required item.'),
 'constraints-06':(['home','mwf'],'Both descriptions explicitly give Monday/Wednesday/Friday as a three-day schedule.'),
 'constraints-07':(['two_day'],'Russian squat routine description explicitly says twice weekly; recorded session duration is 30 minutes. Recorded duration is not a verified stopwatch measurement.'),
 'constraints-11':(['novice','fit'],'Novice-tagged strength/Powerbuilding sources. Linked exercise names were checked for snatch, jerk and clean variants; none was present.'),
 'constraints-12':(['bodyweight'],'Source explicitly permits no gym equipment; adding resistance bands is optional.'),
 'constraints-13':(['db_strength'],'Dumbbell Only source carries a Powerlifting tag but describes home strength/hypertrophy. Answer must explain that this is not evidence of competition-specific barbell training.'),
 'constraints-16':(['dumbbells','home'],'Two recorded candidates expose equipment and duration for a factual comparison; personalization requires more context.'),
 'constraints-17':(['dumbbells','home'],'Beginner evidence only; retrieval must not create or activate a plan.'),
 'constraints-18':(['row','chest'],'Actual named dumbbell movements with Dumbbell Only among equipment tags. A Full Gym label alone is not the required compatibility evidence.'),
 'constraints-19':(['home','short_home'],'At Home, Bodybuilding records list 30 and 40 minutes. The Jerma title mentions 30 while metadata is 40; both satisfy the bound but the discrepancy must be disclosed.'),
 'agents-03':(['row'],'Dumbbell Row is a source-backed dumbbell/back exercise example.'),
 'agents-10':(['dumbbells','home'],'Beginner evidence is available; avoid assuming unspecified personal restrictions.'),
 'validation-01':(['three_day','mwf'],'Source descriptions explicitly support three weekly dumbbell sessions. The source programs are four weeks; do not claim a generated six-week plan is copied verbatim from them.'),
}
NEGATIVES={
 'retrieval-01':[('not_beginner','Despite its Beginner tag, source explicitly says it is not for beginners.')],
 'retrieval-02':[('not_dumbbell_only','Description requires cable and Smith machines despite a Dumbbell Only tag.')],
 'retrieval-05':[('not_bodyweight','Bench-press-focused program does not establish equipment-free bodyweight compatibility.')],
 'retrieval-09':[('not_bodyweight','At Home metadata does not turn a bench-press program into beginner equipment-free calisthenics.')],
 'constraints-01':[('not_dumbbell_only','Description explicitly mentions cable and Smith machines, violating the equipment restriction.')],
 'constraints-03':[('not_beginner','Description explicitly excludes beginners despite broad metadata.')],
 'constraints-12':[('not_bodyweight','Bench-press-specific source does not support bodyweight-only training.')],
}


def canonical_hash(doc):
    payload={k:v for k,v in doc.items() if k not in {'chunk_id','collection','score'}}
    return hashlib.sha256((doc['collection']+'\n'+json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':'))).encode()).hexdigest()


def matches(doc,rule):
    for key,value in rule.items():
        actual=doc.get(key)
        if isinstance(value,list):
            actual=actual if isinstance(actual,list) else [actual]
            if not set(actual)&set(value):return False
        elif isinstance(value,dict):
            if not isinstance(actual,(int,float)) or actual>value['lte']:return False
        elif actual!=value:return False
    return True


def build():
    source_manifest=json.loads((LOCAL/'manifest.json').read_text())
    corpus=[]
    for collection,metadata in source_manifest['collections'].items():
        path=LOCAL/f'{collection}.jsonl'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=metadata['sha256']:
            raise ValueError('Corpus snapshot hash differs; do not apply these reference IDs.')
        corpus.extend(json.loads(line) for line in path.read_text().splitlines())
    by_id={doc['chunk_id']:doc for doc in corpus}
    programs=[d for d in corpus if d['collection']=='fitness_programs']
    exercises=[d for d in corpus if d['collection']=='fitness_exercises']
    for name,id in BANK.items():
        if id not in by_id:raise ValueError(f'Missing reference {name}')
    compact={name:{k:m[k] for k in ['count','sha256']} for name,m in source_manifest['collections'].items()}
    corpus_id=hashlib.sha256(json.dumps(compact,sort_keys=True).encode()).hexdigest()
    cases=[json.loads(line) for line in (DATA/'fitness_scenarios.v1.jsonl').read_text().splitlines()]
    def label(doc,relevant,reason):
        facts={k:doc[k] for k in ['title','exercise_name','goal','level','equipment','program_length_weeks','time_per_workout_min','sets_median','reps_median','is_time_based'] if k in doc}
        return {'collection':doc['collection'],'chunk_id':doc['chunk_id'],'document_sha256':canonical_hash(doc),
                'relevant':relevant,'reason':reason,'source_facts':facts}
    def linked(program_name,pattern):
        program=by_id[BANK[program_name]]
        candidates=[d for d in exercises if program['title'] in d.get('programs',[]) and __import__('re').search(pattern,d['exercise_name'],__import__('re').I)]
        if not candidates:raise ValueError('No verified program/exercise association.')
        return program,candidates[0]
    for case in cases:
        id=case['id'];expected=case['expected']
        if not expected['collections']:
            case['reference_status']='not_applicable_to_retrieval'
            expected['retrieval_policy']='not_required_for_behavior_check'
            expected['reference_scope']='behavior_or_state_assertions'
            continue
        case['review']={'reviewer':'Codex AI assistant','independent_human_review':False,
                        'method':'source text/metadata inspection plus deterministic full-snapshot checks',
                        'corpus_id':corpus_id,'reviewed_at':datetime.now(timezone.utc).isoformat()}
        expected['retrieval_policy']='required'
        if id in METADATA:
            rule=METADATA[id]
            selected=[d for d in programs if matches(d,rule)]
            if not selected:raise ValueError('Unexpected empty metadata reference set.')
            expected['reference_scope']='exhaustive_recorded_metadata'
            expected['reference_rule']=rule
            expected['relevance_labels']=[label(d,True,'Matches the explicit recorded-metadata contract; this label does not certify real-world suitability or narrative consistency.') for d in selected]
            case['reference_status']='metadata_checked'
        elif id in POOLS:
            names,reason=POOLS[id]
            expected['reference_scope']='curated_partial_pool'
            expected['relevance_labels']=[label(by_id[BANK[name]],True,reason) for name in names]
            expected['relevance_labels'] += [label(by_id[BANK[name]],False,why) for name,why in NEGATIVES.get(id,[])]
            case['reference_status']='source_checked_ai_review'
        elif id in {'retrieval-21','retrieval-22','retrieval-23'}:
            program_name,pattern={'retrieval-21':('dumbbells',r'row|press'),
                                  'retrieval-22':('novice',r'squat|bench'),
                                  'retrieval-23':('bodyweight',r'plank|squat.*bodyweight')}[id]
            program,exercise=linked(program_name,pattern)
            expected['reference_scope']='curated_partial_pool'
            expected['relevance_labels']=[label(d,True,'Source-backed program/example pair; exercise.programs contains the exact source program title.') for d in [program,exercise]]
            expected['required_source_relationship']={'program_chunk_id':program['chunk_id'],'exercise_chunk_id':exercise['chunk_id'],'join':'exercise.programs contains program.title'}
            case['reference_status']='source_checked_ai_review'
        elif id=='retrieval-10':
            context=[by_id[BANK[name]] for name in ['dumbbells','home','juicy']]
            case['initial_state']['retrieved_context']=[{'collection':d['collection'],'chunk_id':d['chunk_id'],'document_sha256':canonical_hash(d)} for d in context]
            expected['reference_scope']='fixed_context_comparison'
            expected['retrieval_policy']='use_provided_context'
            expected['relevance_labels']=[label(d,True,'Fixed candidate context supplied before the question; compare these sources rather than a corpus-wide minimum.') for d in context]
            expected['minimum_duration_chunk_id']=min(context,key=lambda d:d['time_per_workout_min'])['chunk_id']
            case['reference_status']='source_checked_ai_review'
        elif id=='unsupported-01':
            title='Quantum Unicorn 2099'
            assert not any(d.get('title','').casefold()==title.casefold() for d in programs)
            expected['reference_scope']='exhaustive_exact_title_absence'
            expected['reference_rule']={'exact_title_casefold':title.casefold(),'checked_program_records':len(programs)}
            expected['retrieval_policy']='no_exact_match'
            expected['relevance_labels']=[]
            expected['expected_answerability']='no_exact_title_in_snapshot'
            case['reference_status']='absence_checked'
        elif id=='unsupported-04':
            expected['reference_scope']='unsupported_outcome_guarantee'
            expected['retrieval_policy']='do_not_treat_program_claims_as_proof'
            expected['expected_answerability']='no_guarantee_established_by_this_corpus'
            expected['relevance_labels']=[]
            case['reference_status']='behavior_reference_only'
        elif id=='agents-15':
            expected['reference_scope']='clarification_required'
            expected['retrieval_policy']='clarify_missing_constraints_before_personalized_selection'
            expected['relevance_labels']=[]
            expected['reference_note']='The initial synthetic profile is not yet a fully defined executable fixture. No unique relevant set can be asserted from "my constraints" alone.'
            case['reference_status']='behavior_reference_only'
        else:raise ValueError(f'No reference contract for {id}')
    output=DATA/'fitness_scenarios.v2.jsonl'
    output.write_text(''.join(json.dumps(c,ensure_ascii=False,separators=(',',':'))+'\n' for c in cases))
    manifest={'schema_version':2,'dataset_version':'fitness-scenarios-v2','dataset_file':output.name,
              'parent_dataset_sha256':hashlib.sha256((DATA/'fitness_scenarios.v1.jsonl').read_bytes()).hexdigest(),
              'count':100,'development_count':30,'held_out_count':70,
              'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
              'corpus_snapshot':{'id':corpus_id,'collections':compact},
              'label_status':'mixed: metadata contracts and AI source-reviewed partial pools; no independent human adjudication',
              'reference_status_counts':dict(Counter(c['reference_status'] for c in cases)),
              'cases_with_positive_reference_ids':sum(any(l['relevant'] for l in c['expected']['relevance_labels']) for c in cases),
              'label_provenance':'Labels were determined by source inspection or full-corpus metadata predicates, not by accepting model judgments as truth. Some development documents had appeared in earlier pilot results; this is not blind annotation. No held-out outputs were inspected.',
              'limitations':['Metadata contracts evaluate stored fields, not semantic eligibility or medical/fitness correctness.',
                             'Curated pools are incomplete; unjudged documents are unknown, not automatic negatives.',
                             'Held-out references were prepared without executing held-out inputs; do not tune on future held-out outcomes.',
                             'v2 fixes the missing context of retrieval-10. Historical v1 outputs do not evaluate that corrected context task.',
                             'These are AI-assisted source checks, not an independently human-validated benchmark.']}
    (DATA/'fitness_scenarios.v2.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (DATA/'reference_corpus.json').write_text(json.dumps(manifest['corpus_snapshot'],indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ['count','reference_status_counts','cases_with_positive_reference_ids']},indent=2))


if __name__=='__main__':build()

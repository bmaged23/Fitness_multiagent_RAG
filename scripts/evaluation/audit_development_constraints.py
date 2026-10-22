"""Audit explicit metadata constraints; not semantic relevance or answer correctness."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from scripts.evaluation.snapshot_corpus import read_json

# Development cases only. Rules derive from explicit user constraints, never held-out outcomes.
RULES={
 'retrieval-04':{'level':['Advanced'],'goal':['Bodybuilding']},
 'retrieval-07':{'goal':['Olympic Weightlifting']},
 'retrieval-11':{'level':['Beginner']},
 'retrieval-13':{'equipment':['Garage Gym'],'goal':['Powerbuilding']},
 'retrieval-25':{'level':['Beginner']},
 'constraints-02':{'equipment':['At Home']},
 'constraints-09':{'program_length_weeks':6},
 'constraints-13':{'goal':['Powerlifting'],'equipment':['Dumbbell Only']},
 'constraints-14':{'level':['Advanced'],'time_per_workout_min':10},
 'constraints-19':{'equipment':['At Home'],'time_per_workout_min':{'lte':40}},
}


def matches(doc,rule):
    for field,expected in rule.items():
        value=doc.get(field)
        if isinstance(expected,list):
            actual=value if isinstance(value,list) else [value]
            if not set(actual)&set(expected): return False
        elif isinstance(expected,dict):
            if value is None or value>expected['lte']: return False
        elif value!=expected: return False
    return True


def qdrant_filter(rule):
    return {'must':[{'key':key,**({'match':{'any':value}} if isinstance(value,list)
                    else {'range':value} if isinstance(value,dict)
                    else {'match':{'value':value}})} for key,value in rule.items()]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,default=Path('.evaluation-local/direct-development'))
    parser.add_argument('--url',default='http://localhost:6333')
    parser.add_argument('--output',type=Path,default=Path('.evaluation-local/constraint-audit.json'))
    args=parser.parse_args()
    report=json.loads((args.baseline/'results.json').read_text())
    if report['split']!='development': raise ValueError('This audit is development-only.')
    corpus=[json.loads(s) for s in Path('.evaluation-local/corpus/fitness_programs.jsonl').read_text().splitlines()]
    vectors={q['id']:q['vector'] for q in json.loads((args.baseline/'embeddings.json').read_text())['queries']}
    output=[]
    for case in report['results']:
        if case['id'] not in RULES: continue
        rule=RULES[case['id']]
        positives=[d['chunk_id'] for d in corpus if matches(d,rule)]
        raw=[d for d in case['retrieved'] if d['collection']=='fitness_programs']
        response=read_json(args.url,'/collections/fitness_programs/points/query',
                           {'query':vectors[case['id']],'limit':3,'with_payload':True,
                            'filter':qdrant_filter(rule),'params':{'exact':True}})
        filtered=[{'chunk_id':str(hit['id']),**hit['payload']} for hit in response['points']]
        output.append({'id':case['id'],'query':case['query'],'rule':rule,
                       'metadata_matching_corpus_records':len(positives),
                       'raw_returned':len(raw),'raw_compliant':sum(matches(d,rule) for d in raw),
                       'filtered_returned':len(filtered),'filtered_compliant':sum(matches(d,rule) for d in filtered),
                       'raw_ids':[d['chunk_id'] for d in raw],
                       'filtered_ids':[d['chunk_id'] for d in filtered]})
    result={'metric':'explicit metadata constraint compliance, not semantic relevance',
            'split':'development','cases':output,
            'summary':{key:sum(c[key] for c in output) for key in ['raw_returned','raw_compliant','filtered_returned','filtered_compliant']},
            'limitations':['Hand-authored filters supplied by evaluator, not inferred by agent; filtered compliance is a filter implementation sanity check, not an agent success rate.',
                          'Corpus equipment/level metadata can be wrong; matching metadata does not establish actual equipment suitability.',
                          'Cases with no matching corpus records must be reported, not removed or called perfect retrieval.',
                          'Only ten development scenarios have explicit rules here; these are not aggregate results for the 100-case suite.']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['summary']))


if __name__=='__main__': main()

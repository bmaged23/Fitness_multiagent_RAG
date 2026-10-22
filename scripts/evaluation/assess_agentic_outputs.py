"""Check actual agent evidence provenance against its tool results and corpus snapshot."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import statistics
from scripts.evaluation.audit_development_constraints import RULES, matches


def assess(case,corpus):
    if case['status']!='completed': return {'id':case['id'],'status':'failed_run'}
    final=next((m['content'] for m in reversed(case['messages']) if m['type']=='ai' and not m.get('tool_calls')),None)
    try: documents=json.loads(final)
    except (ValueError,TypeError): return {'id':case['id'],'status':'invalid_json'}
    if not isinstance(documents,list): return {'id':case['id'],'status':'invalid_output_type'}
    observed={(s['collection'],d['chunk_id']) for s in case['search_calls'] for d in s['documents']}
    issues=[]
    for doc in documents:
        if not isinstance(doc,dict):
            issues.append({'kind':'invalid_document'});continue
        key=(doc.get('collection'),str(doc.get('chunk_id')))
        if key not in corpus:
            issues.append({'kind':'unknown_source_id','source':key});continue
        if key not in observed: issues.append({'kind':'source_not_in_search_results','source':key})
        source=corpus[key]
        if doc.get('text') and not source.get('text','').startswith(doc['text']):
            issues.append({'kind':'modified_evidence_text','source':key})
        for field in ['goal','level','equipment','program_length_weeks','time_per_workout_min','sets_median','reps_median','is_time_based']:
            if field in doc and doc[field]!=source.get(field):
                issues.append({'kind':'modified_source_metadata','source':key,'field':field})
    programs=[d for d in documents if isinstance(d,dict) and d.get('collection')=='fitness_programs']
    rule=RULES.get(case['id'])
    metadata_score=sum(matches(d,rule) for d in programs)/len(programs) if rule and programs else None
    return {'id':case['id'],'status':'parsed','seconds':case['seconds'],
            'search_calls':len(case['search_calls']),'returned_documents':len(documents),
            'issues':issues,'metadata_compliance':metadata_score,
            'documents':documents,'query':case['query']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=Path('.evaluation-local/agentic-development-full/results.json'))
    parser.add_argument('--output',type=Path,default=Path('.evaluation-local/agentic-assessment.json'))
    args=parser.parse_args()
    report=json.loads(args.input.read_text())
    corpus={}
    for path in Path('.evaluation-local/corpus').glob('fitness_*.jsonl'):
        for line in path.read_text().splitlines():
            d=json.loads(line);corpus[(d['collection'],d['chunk_id'])]=d
    rows=[assess(case,corpus) for case in report['cases']]
    completed=[r for r in rows if r['status']=='parsed']
    result={'split':'development','rows':rows,'summary':{'cases':len(rows),
          'parsed':len(completed),'cases_with_evidence_issues':sum(bool(r['issues']) for r in completed),
          'median_seconds':statistics.median(r['seconds'] for r in completed) if completed else None,
          'total_search_calls':sum(r['search_calls'] for r in completed)},
          'limitations':['Evidence provenance is not correctness or relevance. No end-to-end Coach/Designer answers are scored.',
                        'Empty final evidence is reported, not automatically treated as a successful answer.',
                        'Per-case search budgets and number of final documents differ from direct top-3 retrieval.']}
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(result['summary']))
    for row in completed:
        if row['issues']: print(row['id'],json.dumps(row['issues']))


if __name__=='__main__': main()

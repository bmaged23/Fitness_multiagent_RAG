"""Apply v2 source references to recorded development runs; does not execute held-out inputs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from scripts.evaluation.validate_dataset import DATASET,load_cases
from scripts.evaluation.reference_scoring import score_reference_case


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assessment',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assessment=json.loads(args.assessment.read_text())
    if assessment['split']!='development':raise ValueError('This runner only scores recorded development cases.')
    cases={c['id']:c for c in load_cases()}
    rows=[]
    for row in assessment['rows']:
        case=cases[row['id']]
        if case['split']!='development':raise ValueError('Held-out output encountered.')
        if row['status']!='parsed' or row['issues']:
            rows.append({'id':case['id'],'status':'unscored_invalid_output'});continue
        rows.append({'id':case['id'],'scores':score_reference_case(case,row['documents'])})
    closed=[s for row in rows for s in row.get('scores',{}).get('collections',{}).values() if s.get('scope')=='recorded_metadata_only']
    partial=[s for row in rows for s in row.get('scores',{}).get('collections',{}).values() if s.get('status')=='partial_pool_not_full_semantic_ground_truth']
    summary={'cases':len(rows),'closed_metadata_collection_checks':len(closed),
             'mean_metadata_precision_at_3':sum(s['precision_at_k'] for s in closed)/len(closed) if closed else None,
             'mean_metadata_mrr_at_3':sum(s['mrr_at_k'] for s in closed)/len(closed) if closed else None,
             'partial_pool_returned_documents':sum(s['returned_count'] for s in partial),
             'partial_pool_unjudged_documents':sum(s['unjudged_returned_count'] for s in partial)}
    result={'dataset':DATASET.name,'dataset_sha256':hashlib.sha256(DATASET.read_bytes()).hexdigest(),
            'assessment_sha256':hashlib.sha256(args.assessment.read_bytes()).hexdigest(),
            'split':'development','summary':summary,'rows':rows,
            'limitations':['Metadata scores concern stored fields, not expert-verified semantic/fitness quality.',
                           'Curated pools are incomplete; unknown documents are reported as unjudged.',
                           'Labels were prepared retrospectively on development data; not a blind or held-out benchmark.']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()

"""Run a small real-model relevance judge pilot on saved retrieval outputs."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import time
from dotenv import load_dotenv, dotenv_values
from scripts.evaluation.llm_judge import judge_retrieval


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cloud-env',type=Path,required=True)
    parser.add_argument('--input',type=Path,default=Path('.evaluation-local/direct-development/results.json'))
    parser.add_argument('--output',type=Path,default=Path('.evaluation-local/judge-pilot.json'))
    parser.add_argument('--model',default='gpt-oss:120b')
    parser.add_argument('--limit',type=int,default=3)
    args=parser.parse_args()
    if not 1<=args.limit<=30: parser.error('limit must be between 1 and 30')
    # Copy only cloud configuration to process memory, not into artifacts or another project.
    values=dotenv_values(args.cloud_env)
    for name in ['OLLAMA_API_KEY','OLLAMA_BASE_URL']:
        if values.get(name): os.environ[name]=values[name]
    report=json.loads(args.input.read_text())
    if report['split']!='development': raise ValueError('Pilot is development-only.')
    results=[]
    for case in report['results'][:args.limit]:
        tick=time.perf_counter()
        try:
            judgment=judge_retrieval(case['query'],case['retrieved'],args.model)
        except Exception as error:
            judgment={'status':'unscored_judge_error','score':None,'error_type':type(error).__name__}
        results.append({'id':case['id'],'query':case['query'],'judgment':judgment,'seconds':time.perf_counter()-tick})
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps({'model':args.model,'split':'development','results':results,
            'status':'pilot_model_judgments_require_review','ground_truth':False},indent=2)+'\n')
        print(case['id'],judgment['status'],flush=True)


if __name__=='__main__': main()

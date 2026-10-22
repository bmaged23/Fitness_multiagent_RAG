"""Live Qdrant development experiments in LangSmith with cached GPU embeddings."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from scripts.evaluation.snapshot_corpus import read_json
from scripts.evaluation.audit_development_constraints import RULES, matches, qdrant_filter


def source_ids_present(outputs):
    docs=outputs.get('documents',[])
    return {'key':'source_ids_present','score':bool(docs) and all(d.get('chunk_id') for d in docs),
            'comment':'Provenance presence only, not source relevance.'}


def metadata_compliance(inputs,outputs):
    rule=RULES.get(inputs['scenario_id'])
    docs=outputs.get('documents',[])
    if rule is None or not docs:
        return {'key':'metadata_compliance','score':None,'comment':'No rule or no returned documents; not scored.'}
    return {'key':'metadata_compliance','score':sum(matches(d,rule) for d in docs)/len(docs),
            'comment':'Explicit metadata constraints only; not semantic relevance or final-answer correctness.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--judge-model', default=None)
    parser.add_argument('--cloud-env', type=Path)
    parser.add_argument('--dataset-name',default='fitness-scenarios-v1-development-draft')
    parser.add_argument('--url',default='http://localhost:6333')
    parser.add_argument('--baseline',type=Path,default=Path('.evaluation-local/direct-development'))
    parser.add_argument('--output',type=Path,default=Path('.evaluation-local/langsmith-retrieval'))
    args=parser.parse_args()
    from dotenv import load_dotenv, dotenv_values
    import os
    load_dotenv(Path(__file__).resolve().parents[2]/'.env')
    if args.judge_model:
        if args.cloud_env is None: parser.error('--cloud-env is required for the judge')
        values=dotenv_values(args.cloud_env)
        for key in ['OLLAMA_API_KEY','OLLAMA_BASE_URL']:
            if values.get(key): os.environ[key]=values[key]
    from langsmith import Client
    from langsmith.evaluation import evaluate
    import time
    client=Client()
    dataset=client.read_dataset(dataset_name=args.dataset_name)
    examples=[e for e in client.list_examples(dataset_id=dataset.id)
              if e.inputs.get('scenario_id') in RULES and e.metadata.get('split')=='development']
    if len(examples)!=len(RULES): raise RuntimeError('Expected all ten development constraint cases.')
    embedded=json.loads((args.baseline/'embeddings.json').read_text())
    vectors={q['id']:q['vector'] for q in embedded['queries']}
    corpus_path=Path('.evaluation-local/corpus/fitness_programs.jsonl')
    snapshot={d['chunk_id']:d for d in map(json.loads,corpus_path.read_text().splitlines())}
    args.output.mkdir(parents=True,exist_ok=True)
    runs=[]
    for filtered in [False,True]:
        rows=[]
        judgments={}
        def judge_feedback(inputs,outputs):
            from scripts.evaluation.llm_judge import judge_retrieval
            try:
                judgment=judge_retrieval(inputs['turns'][-1]['content'],outputs['documents'],args.judge_model)
            except Exception as error:
                judgment={'status':'unscored_judge_error','score':None,'error_type':type(error).__name__}
            judgments[inputs['scenario_id']]=judgment
            return {'key':'llm_retrieval_relevance','score':judgment['score'],
                    'comment':json.dumps(judgment)}
        def target(inputs):
            case_id=inputs['scenario_id']
            tick=time.perf_counter()
            body={'query':vectors[case_id],'limit':3,'with_payload':True,'params':{'exact':True}}
            if filtered: body['filter']=qdrant_filter(RULES[case_id])
            response=read_json(args.url,'/collections/fitness_programs/points/query',body)
            docs=[]
            for hit in response['points']:
                doc={**hit['payload'],'collection':'fitness_programs','chunk_id':str(hit['id'])}
                if doc!=snapshot.get(doc['chunk_id']): raise RuntimeError('Live payload no longer matches corpus snapshot.')
                docs.append({**doc,'score':hit['score']})
            output={'documents':docs,'retrieval_seconds':time.perf_counter()-tick,
                    'filters_supplied_by_evaluator':filtered,'embedding_in_timing':False,
                    'answer':None,'semantic_quality_status':'unscored_pending_reference_review'}
            rows.append({'id':case_id,'output':output,'metadata_compliance':metadata_compliance(inputs,output)})
            return output
        mode='oracle-filtered' if filtered else 'raw-vector'
        result=evaluate(target,data=examples,client=client,evaluators=[source_ids_present,metadata_compliance]+([judge_feedback] if args.judge_model else []),
                        experiment_prefix=f'fitness-{mode}-development'+('-judge' if args.judge_model else ''),max_concurrency=1,
                        metadata={'split':'development','cases':10,'top_k':3,
                                  'corpus_sha256':hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
                                  'judge_model':args.judge_model,'cached_embeddings':True,'device_for_embeddings':embedded['runtime']['device'],
                                  'purpose':'metadata constraint audit, not semantic relevance or agent evaluation'},
                        description='Live local Qdrant search with previously computed CUDA BGE query vectors. Oracle filters are hand-authored; no LLM agent evaluated.')
        project=client.read_project(project_name=result.experiment_name)
        record={'mode':mode,'experiment_name':result.experiment_name,'experiment_id':str(project.id),
                'url':project.url,'results':rows,'llm_judgments':judgments,'judge_model':args.judge_model}
        (args.output/f'{mode}.json').write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n')
        runs.append({key:record[key] for key in ['mode','experiment_name','experiment_id','url']})
    (args.output/'manifest.json').write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),
           'dataset_id':str(dataset.id),'experiments':runs},indent=2)+'\n')
    print(json.dumps(runs,indent=2))


if __name__=='__main__': main()

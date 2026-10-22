"""Execute source-first golden QA and independent answer judges, with LangSmith experiments.

This is a direct retrieval + LLM baseline, not a simulation of all Coach/Designer
features. Reference data is used only after answer generation and in scoring.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
from threading import Lock
from dotenv import load_dotenv,dotenv_values
from scripts.evaluation.build_corpus_golden import ROOT,LOCAL,PUBLIC,VERSION
from scripts.evaluation import golden_answer_metrics as quality


METRICS=['ndcg_at_5','precision_at_5','recall_at_5','mrr_at_5','correctness_precision',
         'correctness_f1','completeness','answer_relevance','faithfulness','unsupported_claim_rate']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cloud-env',type=Path,help='Optional local credential file; CI uses environment secrets.')
    parser.add_argument('--retrieval',type=Path,default=LOCAL/'golden/direct-retrieval/results.json')
    parser.add_argument('--output',type=Path,default=LOCAL/'golden/evaluation')
    parser.add_argument('--answer-model',default='gemma4:31b')
    parser.add_argument('--judge-model',default='gpt-oss:120b')
    parser.add_argument('--split',choices=['all','development','held_out'],default='all')
    parser.add_argument('--limit',type=int,default=100)
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--langsmith',action='store_true')
    args=parser.parse_args()
    if not 1<=args.limit<=100 or not 1<=args.workers<=3:parser.error('limit=1..100 and workers=1..3 required')
    load_dotenv(ROOT/'.env')
    for key,value in (dotenv_values(args.cloud_env) if args.cloud_env else {}).items():
        if key in ['OLLAMA_API_KEY','OLLAMA_BASE_URL'] and value:os.environ[key]=value
    manifest=json.loads((PUBLIC/f'{VERSION}.manifest.json').read_text())
    full=LOCAL/f'golden/{VERSION}.jsonl'
    if hashlib.sha256(full.read_bytes()).hexdigest()!=manifest['full_dataset_sha256']:raise ValueError('Dataset changed.')
    cases=[json.loads(line) for line in full.read_text().splitlines()]
    cases=[c for c in cases if args.split=='all' or c['split']==args.split][:args.limit]
    by_id={c['id']:c for c in cases}
    retrieved=json.loads(args.retrieval.read_text())
    if retrieved['dataset_sha256']!=manifest['full_dataset_sha256']:raise ValueError('Retrieval used another dataset.')
    retrieval_by_id={row['id']:row for row in retrieved['results']}
    args.output.mkdir(parents=True,exist_ok=True)
    config={'dataset_sha256':manifest['full_dataset_sha256'],'answer_model':args.answer_model,
            'judge_model':args.judge_model,'split':args.split,'ids':[c['id'] for c in cases],
            'retrieval_sha256':hashlib.sha256(args.retrieval.read_bytes()).hexdigest(),
            'prompt_hashes':{key:hashlib.sha256(getattr(quality,key).encode()).hexdigest() for key in ['ANSWER_SYSTEM','CORRECTNESS_SYSTEM','FAITHFULNESS_SYSTEM']}}
    config_path=args.output/'configuration.json'
    if config_path.exists() and json.loads(config_path.read_text())!=config:raise ValueError('Output directory belongs to a different frozen experiment.')
    config_path.write_text(json.dumps(config,indent=2)+'\n')
    checkpoint=args.output/'cases.jsonl'
    records={}
    if checkpoint.exists():
        for line in checkpoint.read_text().splitlines():
            row=json.loads(line);records[row['id']]=row
    lock=Lock()
    def target(inputs):
        id=inputs['scenario_id']
        with lock:
            if id in records and records[id].get('status')=='completed':return records[id]
        case=by_id[id];retrieval=retrieval_by_id[id]
        record={'id':id,'category':case['category'],'split':case['split'],
                'question':case['question'],'retrieved_contexts':retrieval['retrieved_contexts'],
                'ranking':retrieval['ranking'],'scores':{key:retrieval['ranking'][key] for key in METRICS if key in retrieval['ranking']}}
        try:
            generation=quality.answer_question(case['question'],retrieval['retrieved_contexts'],args.answer_model)
            record['generation']=generation
            for name,fn in [('correctness',lambda:quality.judge_correctness(case['question'],case['reference_answer'],case['reference_facts'],generation['answer'],args.judge_model)),
                            ('faithfulness',lambda:quality.judge_faithfulness(case['question'],retrieval['retrieved_contexts'],generation['answer'],args.judge_model))]:
                try:
                    result=fn();record[name]=result;record['scores'].update(result['scores'])
                except Exception as error:
                    record[name]={'status':'unscored_error','error_type':type(error).__name__,'http_status':getattr(error,'status_code',None)}
            record['status']='completed' if all('scores' in record.get(name,{}) for name in ['correctness','faithfulness']) else 'partial_judge_failure'
        except Exception as error:
            record['status']='generation_failed';record['error_type']=type(error).__name__;record['http_status']=getattr(error,'status_code',None)
        with lock:
            with checkpoint.open('a') as handle:handle.write(json.dumps(record,ensure_ascii=False)+'\n')
            records[id]=record
            print(id,record['status'],flush=True)
        return record
    experiment_url=None
    if args.langsmith:
        from langsmith import Client
        from langsmith.evaluation import evaluate
        client=Client()
        dataset_name=VERSION
        if client.has_dataset(dataset_name=dataset_name):
            dataset=client.read_dataset(dataset_name=dataset_name)
        else:dataset=client.create_dataset(dataset_name=dataset_name,description='100 source-first factual QA references; 120 unique authoritative record anchors. Synthetic, mechanically source-validated; not independently human-adjudicated.')
        existing={e.inputs.get('scenario_id'):e for e in client.list_examples(dataset_id=dataset.id)}
        for c in cases:
            if c['id'] in existing:
                if existing[c['id']].inputs.get('question')!=c['question']:raise ValueError('Existing LangSmith input differs.')
            else:
                client.create_example(inputs={'scenario_id':c['id'],'question':c['question']},
                    outputs={'reference_answer':c['reference_answer'],'reference_facts':c['reference_facts'],
                             'reference_chunks':c['reference_chunks']},
                    metadata={'dataset_sha256':manifest['full_dataset_sha256'],'category':c['category'],'split':c['split']},dataset_id=dataset.id)
        examples=[e for e in client.list_examples(dataset_id=dataset.id) if e.inputs.get('scenario_id') in by_id]
        def all_metrics(outputs):
            return [{'key':key,'score':outputs.get('scores',{}).get(key),
                     'comment':'Missing/failed metrics remain unscored. Reference correctness differs from context faithfulness.'} for key in METRICS]
        result=evaluate(target,data=examples,client=client,evaluators=[all_metrics],max_concurrency=args.workers,
                        experiment_prefix=f'{VERSION}-direct-rag',metadata=config,
                        description='Actual retrieved contexts → Gemma answer → separate GPT-OSS reference and context judges. No reference answer goes into generation. Direct baseline, not full coaching app.')
        experiment_url=client.read_project(project_name=result.experiment_name).url
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:list(executor.map(target,[{'scenario_id':c['id']} for c in cases]))
    summary={}
    for key in METRICS:
        values=[records[c['id']].get('scores',{}).get(key) for c in cases if c['id'] in records]
        scored=[v for v in values if isinstance(v,(float,int))]
        summary[key]={'mean':sum(scored)/len(scored) if scored else None,'scored_cases':len(scored),'total_cases':len(cases)}
    report={'dataset_version':VERSION,'scope':'Direct RAG component baseline, not full Coach/Designer application.',
            'cases':len(cases),'completed':sum(records[c['id']]['status']=='completed' for c in cases),
            'normalized_ranking_score_100':100*sum(records[c['id']]['ranking']['ndcg_at_5'] for c in cases)/len(cases),
            'metrics':summary,'experiment_url':experiment_url,'configuration':config,
            'limitations':['Source-relative factual QA; no independent human gold review or real-world fitness truth claim.',
                           'Score means report their valid denominators; missing judgments are never counted as successes.',
                           'No single combined answer score is imposed; correctness, completeness, faithfulness and relevance remain separate.',
                           'API usage is recorded, but monetary cost is not estimated without actual billing rates.']}
    (args.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()

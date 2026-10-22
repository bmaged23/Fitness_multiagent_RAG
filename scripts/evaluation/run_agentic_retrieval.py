"""Run the real Retriever DeepAgent on development inputs with a resident GPU encoder."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time
from threading import Lock
import resource
from uuid import uuid4
from dotenv import load_dotenv, dotenv_values
from scripts.evaluation.validate_dataset import load_cases

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cloud-env',type=Path,required=True)
    parser.add_argument('--embedding-python',required=True)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=1)
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--case-id', default=None)
    parser.add_argument('--output',type=Path,default=Path('.evaluation-local/agentic-development'))
    args=parser.parse_args()
    if not 1<=args.limit<=16: parser.error('Development retrieval subset has 16 cases; limit must be 1..16.')
    load_dotenv(ROOT/'.env')
    values=dotenv_values(args.cloud_env)
    for key in ['OLLAMA_API_KEY','OLLAMA_MODEL','OLLAMA_BASE_URL']:
        if values.get(key): os.environ[key]=values[key]
    os.environ['LLM_PROVIDER']='ollama'
    os.environ['LANGSMITH_TRACING']='true' if args.trace else 'false'
    # This runner records only synthetic evaluation requests. No user database is opened.
    sys.path.insert(0,str(ROOT/'src'))
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
    from fitness_multiagent_rag.agents.retriever import agent as retriever
    args.output.mkdir(parents=True,exist_ok=True)
    worker_log=(args.output/'embedding-worker.log').open('w')
    worker=subprocess.Popen([args.embedding_python,str(ROOT/'scripts/evaluation/embed_queries.py'),
        '--model',str(args.model.resolve()),'--serve'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=worker_log,text=True,bufsize=1)
    def read_worker():
        if not select.select([worker.stdout],[],[],90)[0]: raise TimeoutError('GPU encoder timeout.')
        line=worker.stdout.readline()
        if not line: raise RuntimeError('GPU encoder exited; see local worker log.')
        return json.loads(line)
    records=[]
    try:
        if not read_worker().get('ready'): raise RuntimeError('GPU encoder did not become ready.')
        embedding_calls=[]
        encoder_lock=Lock()
        def encode(text):
            started=time.perf_counter()
            with encoder_lock:
                worker.stdin.write(json.dumps({'text':text})+'\n');worker.stdin.flush()
                vector=read_worker()['vector']
            embedding_calls.append({'text':text,'seconds':time.perf_counter()-started})
            return vector
        retriever.embed_one=encode  # Evaluation transport only; actual BGE weights/recipe, no fake vectors.
        calls=[]
        original_search=retriever.qdrant.search
        def search(**kwargs):
            tick=time.perf_counter()
            result=original_search(**kwargs)
            calls.append({'collection':kwargs['collection'],'filters':{k:kwargs.get(k) for k in ['goal','level','equipment']},
                          'top_k':kwargs.get('top_k'),'seconds':time.perf_counter()-tick,'documents':result})
            return result
        retriever.qdrant.search=search
        model=retriever.build_retriever_agent()
        cases=[c for c in load_cases() if c['split']=='development' and c['expected']['collections']][:args.limit]
        if args.case_id:
            cases=[c for c in load_cases() if c['id']==args.case_id and c['split']=='development' and c['expected']['collections']]
            if not cases: raise ValueError('case-id must select a development retrieval scenario.')
        for case in cases:
            calls.clear();embedding_calls.clear()
            request_id=str(uuid4());started=time.perf_counter();cpu_started=time.process_time()
            try:
                output=model.invoke({'messages':[HumanMessage(content=case['turns'][-1]['content'])]},
                    config={'configurable':{'retriever_request_id':request_id},'recursion_limit':20,
                            'run_name':f'fitness-retrieval-{case["id"]}',
                            'tags':['development','real-retriever'],
                            'metadata':{'scenario_id':case['id'],'split':'development'}})
                messages=[]
                for msg in output['messages']:
                    messages.append({'type':msg.type,'content':msg.content,
                        'tool_calls':getattr(msg,'tool_calls',None),'usage':getattr(msg,'usage_metadata',None)})
                record={'id':case['id'],'status':'completed','query':case['turns'][-1]['content'],
                        'seconds':time.perf_counter()-started,'messages':messages,
                        'search_calls':list(calls),'embedding_calls':list(embedding_calls)}
            except Exception as error:
                record={'id':case['id'],'status':'failed','error_type':type(error).__name__,
                        'seconds':time.perf_counter()-started,'search_calls':list(calls),'embedding_calls':list(embedding_calls)}
            finally: retriever._release_search_budget(request_id)
            record['main_process_cpu_seconds']=time.process_time()-cpu_started
            record['main_process_max_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
            record['resource_scope']='Main process cumulative max RSS; excludes separate GPU worker and remote LLM.'
            records.append(record)
            (args.output/'results.json').write_text(json.dumps({'split':'development','mode':'real agentic retriever',
                'model':os.environ.get('OLLAMA_MODEL'),'device':'cuda','cases':records,
                'source_hashes':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in [ROOT/'src/fitness_multiagent_rag/agents/retriever/agent.py',ROOT/'src/fitness_multiagent_rag/agents/retriever/prompts/system_prompt.md',ROOT/'src/fitness_multiagent_rag/vectorstore/qdrant_client.py']},
                'semantic_metrics':'unscored_pending_review','transport':'resident external GPU worker; includes RPC overhead',
                'scope':'Retriever component only; Coach/Designer, persistent memory and final answers are not tested here.'},indent=2,ensure_ascii=False)+'\n')
            print(case['id'],record['status'],round(record['seconds'],2),'seconds',flush=True)
    finally:
        worker.terminate()
        try: worker.wait(timeout=10)
        except subprocess.TimeoutExpired: worker.kill();worker.wait()
        worker_log.close()


if __name__=='__main__': main()

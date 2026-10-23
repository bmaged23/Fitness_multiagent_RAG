"""Benchmark a disposable synthetic Coach account; no live user state is opened."""
from __future__ import annotations
import json
import os
import statistics
import time
from pathlib import Path
import requests
from scripts.performance.resource_sampling import ProcessSampler


def main():
    boot=time.perf_counter()
    from langchain_core.callbacks import BaseCallbackHandler
    from scripts.init_db import init_db
    from app.components.chat_ui import signup,initial_messages,chat_turn
    from fitness_multiagent_rag.agents.coach.agent import build_coach_agent
    from fitness_multiagent_rag.agents.retriever import agent as retriever
    from fitness_multiagent_rag.vectorstore.embeddings import embed_one
    from fitness_multiagent_rag.llm.model import get_model
    from fitness_multiagent_rag.db.connection import get_db_ro
    if os.environ.get('SQLITE_DB_PATH')!='/tmp/fitness-performance.db':
        raise ValueError('This benchmark requires its disposable /tmp database.')
    init_db()
    trainee=signup('performance_user','Performance123!','Performance User','performance@example.com','123',
                   25,'male','Bodybuilding','Beginner',['Dumbbell Only'])
    class CallProfiler(BaseCallbackHandler):
        def __init__(self):self.calls={}
        def on_chat_model_start(self,serialized,messages,*,run_id,**kwargs):
            self.calls[str(run_id)]={'started':time.perf_counter()}
        def on_llm_end(self,response,*,run_id,**kwargs):
            record=self.calls.setdefault(str(run_id),{'started':time.perf_counter()})
            record['seconds']=time.perf_counter()-record.pop('started')
            try:record['usage']=response.generations[0][0].message.usage_metadata
            except (IndexError,AttributeError):record['usage']=None
        def on_llm_error(self,error,*,run_id,**kwargs):
            record=self.calls.setdefault(str(run_id),{'started':time.perf_counter()})
            record['seconds']=time.perf_counter()-record.pop('started');record['error_type']=type(error).__name__
    profiler=CallProfiler();get_model().callbacks=[profiler]
    graph=build_coach_agent()
    startup=time.perf_counter()-boot
    embeddings=[];searches=[]
    original_embed=retriever.embed_one;original_search=retriever.qdrant.search
    def embedding(text):
        started=time.perf_counter();value=original_embed(text)
        embeddings.append(time.perf_counter()-started);return value
    def search(**kwargs):
        started=time.perf_counter();value=original_search(**kwargs)
        searches.append(time.perf_counter()-started);return value
    retriever.embed_one=embedding;retriever.qdrant.search=search
    with ProcessSampler() as cold:
        embed_one('A beginner dumbbell workout')
    warm=[]
    for _ in range(5):
        started=time.perf_counter();embed_one('A beginner dumbbell workout');warm.append(time.perf_counter()-started)
    samples=[]
    questions=json.loads(os.environ['FITNESS_BENCHMARK_QUESTIONS'])
    for index,question in enumerate(questions,1):
        profiler.calls.clear();embeddings.clear();searches.clear();events=[]
        started=time.perf_counter()
        def reply(text):events.append({'seconds':time.perf_counter()-started,'characters':len(text)})
        with ProcessSampler() as resources:
            answer=chat_turn(graph,initial_messages(trainee),trainee.id,question,on_reply=reply)
        elapsed=time.perf_counter()-started
        if not answer or 'couldn’t complete' in answer:raise RuntimeError('Coaching request failed.')
        calls=list(profiler.calls.values())
        samples.append({'id':index,'question':question,'answer':answer,'total_seconds':elapsed,
                        'first_complete_assistant_message_seconds':events[0]['seconds'] if events else None,
                        'ui_content_available_seconds':elapsed,
                        'llm_calls':calls,'embedding_seconds':list(embeddings),'qdrant_seconds':list(searches),
                        'process_resources':resources.result})
        print('PERFORMANCE_PROGRESS',index,'of',len(questions),round(elapsed,2),'seconds',flush=True)
    with get_db_ro() as connection:
        if connection.execute('SELECT count(*) FROM plans').fetchone()[0]:raise ValueError('Read-only scenarios unexpectedly saved a plan.')
    # Native model stream is a separate component probe, not the app's visible TTFT.
    key=os.environ['OLLAMA_API_KEY'];started=time.perf_counter();first=None;parts=[];usage={}
    with requests.post('https://ollama.com/api/chat',headers={'Authorization':'Bearer '+key},
        json={'model':os.environ['OLLAMA_MODEL'],'stream':True,'think':False,
              'messages':[{'role':'user','content':'Explain progressive overload in three short sentences.'}],
              'options':{'temperature':0,'num_predict':160}},stream=True,timeout=(15,120)) as response:
        if not response.ok:raise RuntimeError('Streaming probe HTTP '+str(response.status_code))
        for line in response.iter_lines():
            if not line:continue
            chunk=json.loads(line);text=chunk.get('message',{}).get('content','')
            if text:
                first=first if first is not None else time.perf_counter()-started;parts.append(text)
            if chunk.get('done'):usage={k:chunk.get(k) for k in ['prompt_eval_count','eval_count','total_duration']}
    report={'scope':'Five synthetic read-only requests through the actual container Coach; compiled graph and embeddings reused.',
            'graph_and_import_startup_seconds':startup,
            'embedding_cold':cold.result,'embedding_warm_seconds':warm,
            'embedding_warm_median_seconds':statistics.median(warm),'samples':samples,
            'native_cloud_stream_probe':{'time_to_first_content_seconds':first,'total_seconds':time.perf_counter()-started,
                                         'usage':usage,'answer':''.join(parts),'think':False},
            'limitations':['This is a small operational sample, not a quality benchmark or load/capacity certification.',
                           'Current UI buffers the job; first complete assistant message is not token-level user-visible streaming.',
                           'Native cloud streaming has no agents/tools and think=false; do not compare its TTFT as full-app TTFT.',
                           'Resources cover the application process; external Qdrant and cloud inference are excluded.',
                           'CPU image uses no CUDA. Provider-side CPU/RAM/VRAM is not exposed.']}
    print('PERFORMANCE_RESULT='+json.dumps(report),flush=True)


if __name__=='__main__':main()

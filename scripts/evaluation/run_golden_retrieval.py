"""Query both live collections without supplying gold routes, IDs or answers."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from scripts.evaluation.snapshot_corpus import read_json
from scripts.evaluation.golden_ranking import ranking_metrics
from scripts.evaluation.curate_references import canonical_hash
from scripts.evaluation.build_corpus_golden import ROOT,LOCAL,PUBLIC,VERSION


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--embedding-python',required=True)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--url',default='http://localhost:6333')
    parser.add_argument('--output',type=Path,default=LOCAL/'golden/direct-retrieval')
    args=parser.parse_args()
    dataset=LOCAL/f'golden/{VERSION}.jsonl'
    manifest=json.loads((PUBLIC/f'{VERSION}.manifest.json').read_text())
    if hashlib.sha256(dataset.read_bytes()).hexdigest()!=manifest['full_dataset_sha256']:
        raise ValueError('Golden dataset hash changed.')
    cases=[json.loads(line) for line in dataset.read_text().splitlines()]
    corpus={}
    for name,meta in manifest['corpus'].items():
        path=LOCAL/f'corpus/{name}.jsonl'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['sha256']:raise ValueError('Corpus changed.')
        for line in path.read_text().splitlines():
            d=json.loads(line);corpus[(name,d['chunk_id'])]=d
    args.output.mkdir(parents=True,exist_ok=True)
    queries=args.output/'queries.json'
    queries.write_text(json.dumps([{'id':c['id'],'text':c['question']} for c in cases]))
    embedded=args.output/'embeddings.json'
    subprocess.run([args.embedding_python,str(ROOT/'scripts/evaluation/embed_queries.py'),
         '--model',str(args.model.resolve()),'--input',str(queries.resolve()),'--output',str(embedded.resolve())],check=True)
    embeddings=json.loads(embedded.read_text());vectors={q['id']:q['vector'] for q in embeddings['queries']}
    rows=[]
    for c in cases:
        tick=time.perf_counter();docs=[]
        # Same policy for all cases: both collections queried, then global cosine top five.
        # The pipeline never gets reference routes/IDs/facts when selecting evidence.
        for collection in ['fitness_programs','fitness_exercises']:
            response=read_json(args.url,f'/collections/{collection}/points/query',
                {'query':vectors[c['id']],'limit':5,'with_payload':True,'params':{'exact':True}})
            for hit in response['points']:
                doc={**hit['payload'],'collection':collection,'chunk_id':str(hit['id'])}
                frozen=corpus.get((collection,doc['chunk_id']))
                if not frozen or canonical_hash(doc)!=canonical_hash(frozen):raise ValueError('Live source differs from frozen corpus.')
                docs.append({**doc,'score':hit['score']})
        docs=sorted(docs,key=lambda d:(-d['score'],d['collection'],d['chunk_id']))[:5]
        named_programs=[d['title'] for d in corpus.values() if d['collection']=='fitness_programs' and d['title'] in c['question']]
        contexts=[]
        for d in docs:
            metadata={key:d[key] for key in ['title','exercise_name','goal','level','equipment','program_length_weeks','time_per_workout_min','sets_median','reps_median','is_time_based'] if key in d}
            ctx={'collection':d['collection'],'chunk_id':d['chunk_id'],'text':d['text'][:4000],
                 'source_metadata':metadata,'score':d['score']}
            if d['collection']=='fitness_exercises' and named_programs:
                ctx['association_evidence']=[{'program_title':p,'present_in_exercise_programs':p in d.get('programs',[])} for p in named_programs]
            contexts.append(ctx)
        rows.append({'id':c['id'],'question':c['question'],'category':c['category'],'split':c['split'],
                     'retrieval_seconds':time.perf_counter()-tick,'retrieved_contexts':contexts,
                     'ranking':ranking_metrics(contexts,c['reference_chunks'],5)})
    metrics=['ndcg_at_5','precision_at_5','recall_at_5','mrr_at_5','average_precision_at_5','hit_at_5','all_required_sources_found']
    summary={key:sum(r['ranking'][key] for r in rows)/len(cases) for key in metrics}
    summary['normalized_ranking_score_100']=100*summary['ndcg_at_5']
    report={'dataset_version':VERSION,'dataset_sha256':manifest['full_dataset_sha256'],
            'pipeline':'Direct BGE GPU retrieval, search both collections and merge cosine top-5; not the full Coach/Designer application.',
            'sample_count':len(rows),'summary':summary,'embedding_runtime':embeddings['runtime'],'results':rows}
    (args.output/'results.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()

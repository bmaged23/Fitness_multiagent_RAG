"""Run real direct top-3 retrieval on development cases; no LLM judge or fabricated labels."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from scripts.evaluation.validate_dataset import load_cases
from scripts.evaluation.retrieval_metrics import score_retrieval
from scripts.evaluation.snapshot_corpus import read_json

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--embedding-python',default=sys.executable)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--url',default='http://localhost:6333')
    parser.add_argument('--corpus',type=Path,default=Path('.evaluation-local/corpus'))
    parser.add_argument('--output',type=Path,default=Path('.evaluation-local/direct-development'))
    parser.add_argument('--device',choices=['cuda','cpu'],default='cuda')
    args=parser.parse_args()
    cases=[c for c in load_cases() if c['split']=='development' and c['expected']['collections']]
    args.output.mkdir(parents=True,exist_ok=True)
    source={}
    corpus_manifest=json.loads((args.corpus/'manifest.json').read_text())
    for collection,meta in corpus_manifest['collections'].items():
        path=args.corpus/f'{collection}.jsonl'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['sha256']:
            raise RuntimeError('Snapshot hash changed.')
        for line in path.read_text().splitlines():
            doc=json.loads(line)
            source[(collection,doc['chunk_id'])]=doc
    input_path=args.output/'queries.json'
    input_path.write_text(json.dumps([{'id':c['id'],'text':c['turns'][-1]['content']} for c in cases]))
    embedding_path=args.output/'embeddings.json'
    command=[args.embedding_python,str(ROOT/'scripts/evaluation/embed_queries.py'),'--model',str(args.model.resolve()),
             '--input',str(input_path.resolve()),'--output',str(embedding_path.resolve()),'--device',args.device]
    subprocess.run(command,check=True)
    embedded=json.loads(embedding_path.read_text())
    vectors={q['id']:q['vector'] for q in embedded['queries']}
    results=[]
    for case in cases:
        tick=time.perf_counter()
        docs=[]
        for collection in case['expected']['collections']:
            response=read_json(args.url,f'/collections/{collection}/points/query',
                               {'query':vectors[case['id']],'limit':3,'with_payload':True,'params':{'exact':True}})
            for hit in response['points']:
                key=(collection,str(hit['id']))
                if key not in source: raise RuntimeError('Live collection differs from snapshot.')
                doc={'collection':collection,'chunk_id':str(hit['id']),**hit['payload']}
                if doc!=source[key]: raise RuntimeError('Live payload differs from snapshot.')
                docs.append({**doc,'score':hit['score']})
        # Multiple collections have separate ranked lists; no cross-collection MRR.
        scores={collection:score_retrieval([d for d in docs if d['collection']==collection],
                    [r for r in case['expected']['relevance_labels'] if r['collection']==collection],3)
                for collection in case['expected']['collections']}
        results.append({'id':case['id'],'category':case['category'],'query':case['turns'][-1]['content'],
                        'retrieval_seconds':time.perf_counter()-tick,'retrieved':docs,'scores':scores})
    report={'created_at':datetime.now(timezone.utc).isoformat(),
            'mode':'raw-query direct vector retrieval; no inferred filters',
            'split':'development','count':len(results),'top_k_per_collection':3,
            'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'working_tree_dirty':bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
            'dataset_sha256':hashlib.sha256((ROOT/'evaluation/datasets/fitness_scenarios.v1.jsonl').read_bytes()).hexdigest(),
            'corpus_manifest':corpus_manifest,'embedding_runtime':embedded['runtime'],'results':results,
            'limitations':['Expected collection is supplied by the scenario, not predicted by a router; this measures collection-conditioned retrieval.',
                           'Reference labels unreviewed; this run collects candidates and timings, not answer-quality scores.',
                           'Original index embedding model revision is not recorded; verify reconstruction before claiming exact embedding provenance.']}
    revision=args.model.parent/'embedding_revision.json'
    if revision.exists(): report['embedding_model']=json.loads(revision.read_text())
    (args.output/'results.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(f'Retrieved real corpus evidence for {len(results)} development scenarios; references remain unscored until reviewed.')


if __name__=='__main__': main()

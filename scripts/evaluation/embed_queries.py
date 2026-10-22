"""GPU query-embedding worker using the project's BGE CLS/normalization recipe."""
from __future__ import annotations
import argparse
import json
import resource
import time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--device', default='cuda', choices=['cuda','cpu'])
    parser.add_argument('--batch-size', type=int, default=4)
    args=parser.parse_args()
    import torch
    from transformers import AutoModel, AutoTokenizer
    if args.device=='cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA was requested but is unavailable. No silent CPU fallback.')
    if args.batch_size<1: parser.error('batch size must be positive')
    pooling=args.model/'1_Pooling/config.json'
    if pooling.exists():
        config=json.loads(pooling.read_text())
        if not config.get('pooling_mode_cls_token') or config.get('pooling_mode_mean_tokens'):
            raise ValueError('Worker expects CLS pooling; model config differs.')
    started=time.perf_counter()
    tokenizer=AutoTokenizer.from_pretrained(args.model,local_files_only=True)
    model=AutoModel.from_pretrained(args.model,local_files_only=True).to(args.device).eval()
    if args.serve:
        import sys
        print(json.dumps({'ready':True,'device':args.device}),flush=True)
        for line in sys.stdin:
            request=json.loads(line)
            with torch.inference_mode():
                inputs=tokenizer([request['text']],padding=True,truncation=True,max_length=512,return_tensors='pt').to(args.device)
                vector=torch.nn.functional.normalize(model(**inputs).last_hidden_state[:,0],p=2,dim=1)[0].cpu().tolist()
            print(json.dumps({'vector':vector}),flush=True)
        return
    if args.input is None or args.output is None:
        parser.error('--input and --output are required without --serve')
    queries=json.loads(args.input.read_text())
    if args.device=='cuda': torch.cuda.synchronize()
    load_seconds=time.perf_counter()-started
    if args.device=='cuda': torch.cuda.reset_peak_memory_stats()
    output,batches=[],[]
    with torch.inference_mode():
        for offset in range(0,len(queries),args.batch_size):
            batch=queries[offset:offset+args.batch_size]
            tick=time.perf_counter()
            inputs=tokenizer([q['text'] for q in batch],padding=True,truncation=True,max_length=512,return_tensors='pt').to(args.device)
            vectors=torch.nn.functional.normalize(model(**inputs).last_hidden_state[:,0],p=2,dim=1)
            vectors=vectors.cpu().tolist()
            elapsed=time.perf_counter()-tick
            batches.append({'offset':offset,'size':len(batch),'seconds':elapsed})
            output.extend({**q,'vector':v} for q,v in zip(batch,vectors))
    result={'queries':output,'runtime':{'device':args.device,'torch':torch.__version__,
            'model_load_seconds':load_seconds,'batches':batches,
            'max_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
            'cpu_user_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime,
            'cuda_peak_allocated_mib':torch.cuda.max_memory_allocated()/1024**2 if args.device=='cuda' else None,
            'cuda_peak_reserved_mib':torch.cuda.max_memory_reserved()/1024**2 if args.device=='cuda' else None,
            'query_instruction':None,'pooling':'CLS','normalized':True,'max_length':512}}
    args.output.write_text(json.dumps(result)+'\n')
    print(json.dumps(result['runtime']))


if __name__=='__main__': main()

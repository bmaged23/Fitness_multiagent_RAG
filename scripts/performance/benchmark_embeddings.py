"""Compare cold/warm CPU, GPU and GPU batching with identical frozen questions."""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import platform
from datetime import datetime,timezone
from scripts.performance.resource_sampling import ProcessSampler,GpuSampler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--embedding-python',required=True)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('.release-local/performance/embeddings'))
    parser.add_argument('--passes',type=int,default=3)
    args=parser.parse_args()
    if args.passes<1:parser.error('passes must be positive')
    root=Path(__file__).resolve().parents[2]
    hardware={'platform':platform.platform(),'logical_cpus':os.cpu_count(),
              'cpu':next((s.split(':',1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name')),None),
              'linux_memory_limit_mib':int(Path('/proc/meminfo').read_text().splitlines()[0].split()[1])/1024,
              'cpu_openmp_threads':2}
    try:
        info=subprocess.check_output(['nvidia-smi','-i','0','--query-gpu=name,memory.total,driver_version','--format=csv,noheader,nounits'],text=True,timeout=5).strip().split(',')
        hardware.update(gpu=info[0].strip(),gpu_memory_mib=float(info[1]),driver=info[2].strip())
    except (OSError,ValueError,subprocess.SubprocessError):hardware['gpu']='unavailable'
    cases=[json.loads(s) for s in (root/'evaluation/datasets/fitness-corpus-qa-v1.references.jsonl').read_text().splitlines()]
    queries=[{'id':c['id'],'text':c['question']} for c in cases if c['split']=='development'][:20]
    queries=queries*args.passes
    args.output.mkdir(parents=True,exist_ok=True)
    input_path=args.output/'queries.json';input_path.write_text(json.dumps(queries))
    runs=[]
    for device,batch in [('cpu',1),('cuda',1),('cuda',4)]:
        output=args.output/f'{device}-batch-{batch}.json'
        env={**os.environ,'OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2','TOKENIZERS_PARALLELISM':'false'}
        command=[args.embedding_python,str(root/'scripts/evaluation/embed_queries.py'),'--model',str(args.model.resolve()),
                 '--input',str(input_path.resolve()),'--output',str(output.resolve()),'--device',device,'--batch-size',str(batch)]
        tick=time.perf_counter()
        with (args.output/f'{device}-batch-{batch}.log').open('w') as log:
            process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
            with ProcessSampler(process.pid) as sampler,GpuSampler() as gpu_sampler:returncode=process.wait()
        if returncode:raise RuntimeError(f'Embedding benchmark failed: {device} batch {batch}; see local log.')
        data=json.loads(output.read_text());batches=data['runtime']['batches'];warm=batches[1:]
        warm_query=[b['seconds']/b['size'] for b in warm]
        runs.append({'device':device,'batch_size':batch,'questions':len(queries),
                     'worker_total_wall_seconds':time.perf_counter()-tick,'runtime':data['runtime'],
                     'warm_median_seconds_per_query':statistics.median(warm_query),
                     'warm_queries_per_second':sum(b['size'] for b in warm)/sum(b['seconds'] for b in warm),
                     'process_resources':sampler.result,'device_gpu_observations':gpu_sampler.result})
        print(device,'batch',batch,'warm seconds/query:',round(runs[-1]['warm_median_seconds_per_query'],5),flush=True)
    cpu=json.loads((args.output/'cpu-batch-1.json').read_text())['queries']
    gpu=json.loads((args.output/'cuda-batch-1.json').read_text())['queries']
    batched=json.loads((args.output/'cuda-batch-4.json').read_text())['queries']
    def cosine(a,b):return sum(x*y for x,y in zip(a,b))/(math.sqrt(sum(x*x for x in a))*math.sqrt(sum(x*x for x in b)))
    agreement={'cpu_vs_gpu_min_cosine':min(cosine(a['vector'],b['vector']) for a,b in zip(cpu,gpu)),
               'gpu_single_vs_batch_min_cosine':min(cosine(a['vector'],b['vector']) for a,b in zip(gpu,batched))}
    if min(agreement.values())<.9999:raise ValueError('Vector agreement failed; do not claim equivalent optimization.')
    report={'scope':f'Embedding worker only; 20 development questions repeated {args.passes} times in each configuration.',
            'measured_at_utc':datetime.now(timezone.utc).isoformat(),'hardware':hardware,
            'runs':runs,'vector_agreement':agreement,
            'limitations':['Warm values exclude the first batch; per-query batch throughput is not interactive latency.',
                           'CPU utilization is process sampling with one occupied core=100%; cloud model resources are unavailable.',
                           'Cold worker wall includes Python/import/model startup. RSS/CPU belong to this process; CUDA peaks come from PyTorch.']}
    (args.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()

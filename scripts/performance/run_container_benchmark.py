"""Run private-key cloud checks against the published image without changing user data."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from dotenv import dotenv_values


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker',default='docker')
    parser.add_argument('--cloud-env',type=Path,required=True)
    parser.add_argument('--image',default='bmaged23/fitness-multiagent-rag@sha256:607ea87c7098638bd0f1227b848d0574bb413842cabf7cf69f4703e50662fc8b')
    parser.add_argument('--qdrant-url',default='http://host.docker.internal:6333')
    parser.add_argument('--output',type=Path,default=Path('.release-local/performance/coaching'))
    args=parser.parse_args();root=Path(__file__).resolve().parents[2]
    public=[json.loads(s) for s in (root/'evaluation/datasets/fitness-corpus-qa-v1.references.jsonl').read_text().splitlines()]
    named=next(c['question'] for c in public if c['split']=='development' and c['category']=='program_facts')
    questions=['Explain progressive overload briefly.',named,
               'Find two beginner dumbbell back exercises from the indexed corpus.',
               'What is the difference between repetitions and sets? Keep it brief.',
               'Summarize my goal and equipment, and suggest one simple next step without saving a plan.']
    values=dotenv_values(args.cloud_env);key=values.get('OLLAMA_API_KEY')
    if not key:raise ValueError('Missing Ollama credential.')
    settings={'OLLAMA_API_KEY':key,'LLM_PROVIDER':'ollama','OLLAMA_BASE_URL':'https://ollama.com','OLLAMA_MODEL':'gemma4:31b',
              'QDRANT_URL':args.qdrant_url,'SQLITE_DB_PATH':'/tmp/fitness-performance.db',
              'FITNESS_BENCHMARK_QUESTIONS':json.dumps(questions)}
    env={**os.environ,**settings}
    env['WSLENV']=':'.join(filter(None,[env.get('WSLENV',''),*settings]))
    resource_code=(root/'scripts/performance/resource_sampling.py').read_text()
    benchmark_code=(root/'scripts/performance/benchmark_coach.py').read_text().replace(
        'from scripts.performance.resource_sampling import ProcessSampler','from fitness_benchmark_resources import ProcessSampler')
    payload='import sys,types\nm=types.ModuleType("fitness_benchmark_resources")\nsys.modules[m.__name__]=m\nexec('+repr(resource_code)+',m.__dict__)\nexec(compile('+repr(benchmark_code)+',"benchmark_coach.py","exec"))\n'
    command=[args.docker,'run','--rm','-i']
    for name in settings:command.extend(['--env',name])
    command.extend([args.image,'python','-'])
    args.output.mkdir(parents=True,exist_ok=True)
    process=subprocess.run(command,input=payload,env=env,text=True,capture_output=True,timeout=900)
    (args.output/'execution.log').write_text((process.stdout+'\n'+process.stderr).replace(key,'[redacted]'))
    if process.returncode:raise RuntimeError('Container performance run failed; sanitized log saved locally.')
    line=next((s for s in process.stdout.splitlines() if s.startswith('PERFORMANCE_RESULT=')),None)
    if not line:raise ValueError('No benchmark result received.')
    report=json.loads(line.split('=',1)[1]);report['image']=args.image
    report['benchmark_code_sha256']=hashlib.sha256(benchmark_code.encode()).hexdigest()
    (args.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Saved',len(report['samples']),'actual Coach request measurements and native streaming probe.')
    print('Total request seconds:',[round(s['total_seconds'],2) for s in report['samples']])


if __name__=='__main__':main()

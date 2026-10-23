"""Exercise first-run provisioning in disposable containers; never touch existing collections."""
import json,subprocess,time
from pathlib import Path
import argparse
parser=argparse.ArgumentParser(description='Isolated first-run CSV/indexing/retrieval/persistent-volume smoke test.')
parser.add_argument('--docker',default='docker')
parser.add_argument('--image',required=True)
args=parser.parse_args()
cli=args.docker
image=args.image
name='fitness-provision-check-'+str(int(time.time()));volume=name+'-data';qdrant=name+'-qdrant'
def docker(*args):return subprocess.check_output([cli,*args],text=True,stderr=subprocess.STDOUT).strip()
code='''
import json,subprocess,sys,time,urllib.request
from pathlib import Path
import pandas as pd
from scripts.init_db import init_db
from scripts import chunk_data
from config.settings import DATA_RAW_DIR,PROGRAMS_CSV,EXERCISES_CSV,PROGRAM_CHUNKS_JSONL,EXERCISE_CHUNKS_JSONL
from app.components.chat_ui import signup
from fitness_multiagent_rag.vectorstore.embeddings import embed_one
from fitness_multiagent_rag.vectorstore.qdrant_client import search
from qdrant_client import QdrantClient
DATA_RAW_DIR.mkdir(parents=True,exist_ok=True)
base={'title':'Container workout','goal':"['Bodybuilding']",'level':"['Beginner']",'equipment':'Dumbbell Only'}
pd.DataFrame([{**base,'program_length':4,'time_per_workout':30,'total_exercises':2,'description':'A source record for provisioning verification.','created':'2026-10-23','last_edit':'2026-10-23'}]).to_csv(PROGRAMS_CSV,index=False)
pd.DataFrame([{**base,'exercise_name':'Dumbbell Row','sets':3,'reps':10,'intensity':8},{**base,'exercise_name':'Plank','sets':3,'reps':-40,'intensity':6}]).to_csv(EXERCISES_CSV,index=False)
assert chunk_data.chunk_programs()==1
assert chunk_data.chunk_exercises()==2
for i in range(30):
 try:
  urllib.request.urlopen(__import__('os').environ['QDRANT_URL']+'/healthz',timeout=2);break
 except OSError:time.sleep(1)
subprocess.run([sys.executable,'scripts/embed_and_index.py','--no-reseting'],check=True)
client=QdrantClient(url=__import__('os').environ['QDRANT_URL'])
assert client.get_collection('fitness_programs').points_count==1
assert client.get_collection('fitness_exercises').points_count==2
hits=search('fitness_exercises',embed_one('Dumbbell Row'),top_k=2)
assert hits[0]['exercise_name']=='Dumbbell Row'
init_db()
signup('persistent_user','SmokeTest123!','Persistent User','smoke@example.com','123',25,'male','Bodybuilding','Beginner',['Dumbbell Only'])
print('PROVISION_RESULT='+json.dumps({'programs':1,'exercises':2,'indexed':True,'retrieval_verified':True}))
'''
created=[]
started=time.perf_counter()
try:
 docker('network','create',name);created.append('network')
 docker('volume','create',volume);created.append('volume')
 docker('run','--rm','-d','--network',name,'--name',qdrant,'qdrant/qdrant@sha256:b7b0444c4c351c970b98e90a6f89c2ee4287c65b44e52b4cb503fa5b2aa927ad');created.append('qdrant')
 output=docker('run','--rm','--network',name,'-v',volume+':/opt/fitness/data','-e','QDRANT_URL=http://'+qdrant+':6333',image,'python','-c',code)
 assert 'PROVISION_RESULT=' in output
 check="from app.components.chat_ui import login; from pathlib import Path; assert login('persistent_user','SmokeTest123!') is not None; assert Path('data/processed/program_chunks.jsonl').is_file(); print('Volume persistence verified across separate containers')"
 print(docker('run','--rm','-v',volume+':/opt/fitness/data',image,'python','-c',check))
 result={'synthetic_csv_provisioning':True,'first_run_indexing':True,'actual_retrieval':True,'volume_restart_persistence':True,'seconds':time.perf_counter()-started}
 print(json.dumps(result))
except subprocess.CalledProcessError as error:
 print(error.output);raise SystemExit(1)
finally:
 if 'qdrant' in created:docker('rm','-f',qdrant)
 if 'volume' in created:docker('volume','rm',volume)
 if 'network' in created:docker('network','rm',name)

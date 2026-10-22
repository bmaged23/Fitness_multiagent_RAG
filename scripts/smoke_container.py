"""Verify public-image health, real BGE inference, account storage and PDF export."""
import argparse
import json
import subprocess
import time
from urllib.request import urlopen

INFERENCE = '''
import io, json
from fitness_multiagent_rag.vectorstore.embeddings import embed_one
from scripts.init_db import init_db
from app.components.chat_ui import signup, login
from app.components.plan_pdf import nutrition_pdf
init_db()
v=embed_one("A beginner dumbbell workout")
assert len(v)==1024 and abs(sum(x*x for x in v)-1)<0.001
u=signup('smoke_user','SmokeTest123!','Smoke User','smoke@example.com','123',25,'male','Bodybuilding','Beginner',['Dumbbell Only'])
assert login('smoke_user','SmokeTest123!').id==u.id
pdf=nutrition_pdf({'summary':'Smoke test','daily_calories':2200,'meals':[]},'Smoke User')
assert pdf.startswith(b'%PDF')
print(json.dumps({'embedding_dimensions':len(v),'account_roundtrip':True,'pdf_bytes':len(pdf)}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker', default='docker')
    parser.add_argument('--image', required=True)
    parser.add_argument('--port', type=int, default=18501)
    args = parser.parse_args()
    def docker(*parts):
        return subprocess.check_output([args.docker, *parts], text=True).strip()
    name = 'fitness-image-smoke-' + str(int(time.time()))
    docker('run', '-d', '--name', name, '-p', f'127.0.0.1:{args.port}:8501',
           '-e', 'SQLITE_DB_PATH=/tmp/smoke.db', args.image)
    try:
        for attempt in range(60):
            try:
                with urlopen(f'http://127.0.0.1:{args.port}/_stcore/health', timeout=2) as response:
                    if response.status == 200:
                        break
            except (OSError, TimeoutError):
                pass
            time.sleep(1)
        else:
            raise RuntimeError('Streamlit health endpoint did not become ready.')
        print(docker('exec', name, 'python', '-c', INFERENCE))
        # Render the real login UI; Streamlit HTTP health alone does not run app code.
        print(docker('exec', name, 'python', '-c',
            "from streamlit.testing.v1 import AppTest; a=AppTest.from_file('app/streamlit_app.py').run(timeout=60); assert not a.exception, str(a.exception); assert len(a.tabs)==2; print('Login UI rendered successfully')"))
    finally:
        docker('rm', '-f', name)


if __name__ == '__main__':
    main()

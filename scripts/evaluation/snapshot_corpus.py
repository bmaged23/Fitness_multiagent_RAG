"""Read-only export of the two fitness collections; never resets Qdrant."""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

COLLECTIONS = ('fitness_programs', 'fitness_exercises')


def read_json(base, path, body=None):
    request = Request(base.rstrip('/')+path, data=json.dumps(body).encode() if body is not None else None,
                      headers={'Content-Type':'application/json'})
    with urlopen(request, timeout=30) as response:
        return json.load(response)['result']


def snapshot(base, output):
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'created_at':datetime.now(timezone.utc).isoformat(),
                'source':'existing local Qdrant; original CSV provenance not reverified',
                'collections':{}, 'vectors_exported':False}
    for name in COLLECTIONS:
        before = read_json(base, f'/collections/{name}')
        records, offset = [], None
        while True:
            result = read_json(base, f'/collections/{name}/points/scroll',
                               {'limit':256,'offset':offset,'with_payload':True,'with_vector':False})
            records.extend({'collection':name,'chunk_id':str(p['id']),**p['payload']} for p in result['points'])
            offset = result.get('next_page_offset')
            if offset is None:
                break
        after = read_json(base, f'/collections/{name}')
        if before['points_count'] != after['points_count'] or len(records) != after['points_count']:
            raise RuntimeError(f'{name}: count changed or export incomplete; do not use this snapshot.')
        records.sort(key=lambda r:r['chunk_id'])
        if len({r['chunk_id'] for r in records}) != len(records):
            raise RuntimeError(f'{name}: duplicate IDs in snapshot.')
        path = output / f'{name}.jsonl'
        path.write_text(''.join(json.dumps(r,sort_keys=True,ensure_ascii=False)+'\n' for r in records))
        manifest['collections'][name]={'count':len(records),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                                       'config':after['config'],'payload_schema':after['payload_schema']}
    manifest['limitations']=['Read-only paginated export; counts checked before/after, but concurrent same-count payload changes are not detectable. Pause ingestion for a strict atomic snapshot.',
                             'Indexing model revision and original raw data hashes are not recorded in existing collection metadata.']
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({n:m['count'] for n,m in manifest['collections'].items()}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://localhost:6333')
    parser.add_argument('--output',type=Path,default=Path('.evaluation-local/corpus'))
    args=parser.parse_args()
    snapshot(args.url,args.output)


if __name__=='__main__': main()

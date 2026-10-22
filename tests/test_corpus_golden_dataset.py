import hashlib
import json
from pathlib import Path
from scripts.evaluation.build_corpus_golden import PUBLIC,VERSION


def test_all_100_questions_have_source_references_and_answers():
    path=PUBLIC/f'{VERSION}.references.jsonl'
    cases=[json.loads(line) for line in path.read_text().splitlines()]
    manifest=json.loads((PUBLIC/f'{VERSION}.manifest.json').read_text())
    assert len(cases)==100
    assert len({c['question'] for c in cases})==100
    assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest['public_reference_sha256']
    anchors=[]
    for c in cases:
        assert c['reference_answer'] and c['reference_facts'] and c['reference_chunks']
        ids={r['chunk_id'] for r in c['reference_chunks']}
        anchors.extend((r['collection'],r['chunk_id']) for r in c['reference_chunks'])
        for f in c['reference_facts']:
            used=f['source_id'] if isinstance(f['source_id'],list) else [f['source_id']]
            assert set(used)<=ids
    assert len(anchors)==120
    assert len(set(anchors))==120
    assert sum(c['split']=='development' for c in cases)==30
    assert sum(c['split']=='held_out' for c in cases)==70

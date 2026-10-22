"""Copy only hash-verified frozen inputs from private runner storage into CI."""
import hashlib
import json
import os
from pathlib import Path

from scripts.evaluation.build_corpus_golden import LOCAL, PUBLIC, VERSION


def main():
    source = Path(os.environ['FITNESS_EVAL_FIXTURES']).resolve()
    if source == LOCAL.resolve() or LOCAL.resolve() in source.parents:
        raise ValueError('Keep private fixtures outside the disposable checkout.')
    manifest = json.loads((PUBLIC / f'{VERSION}.manifest.json').read_text())
    expected = {f'corpus/{name}.jsonl': meta['sha256'] for name, meta in manifest['corpus'].items()}
    expected[f'golden/{VERSION}.jsonl'] = manifest['full_dataset_sha256']
    for relative, digest in expected.items():
        content = (source / relative).read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f'Frozen fixture mismatch: {relative}')
        destination = LOCAL / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    # Never copy .env, local traces, saved answers or previous result checkpoints.
    if not os.environ.get('OLLAMA_API_KEY') or not os.environ.get('LANGSMITH_API_KEY'):
        raise ValueError('Live evaluation requires Ollama and LangSmith secrets.')
    if not Path(os.environ['FITNESS_EMBEDDING_PYTHON']).is_file():
        raise ValueError('Embedding interpreter is unavailable.')
    if not Path(os.environ['FITNESS_EMBEDDING_MODEL']).is_dir():
        raise ValueError('Pinned embedding model is unavailable.')
    print('Verified frozen 100-case dataset and both corpus fingerprints.')


if __name__ == '__main__':
    main()

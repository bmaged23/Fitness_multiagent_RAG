"""Validate the authored evaluation dataset without making service calls."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / 'evaluation/datasets/fitness_scenarios.v1.jsonl'
EXPECTED = {'retrieval': 25, 'constraints': 20, 'memory': 20, 'agents': 15,
            'unsupported': 10, 'validation': 10}


def load_cases(path=DATASET):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def validate(cases):
    errors = []
    if Counter(c.get('category') for c in cases) != Counter(EXPECTED):
        errors.append('Category counts must match the 100-case design.')
    if Counter(c.get('split') for c in cases) != Counter(development=30, held_out=70):
        errors.append('Expected 30 development and 70 held-out scenarios.')
    ids = [c.get('id') for c in cases]
    if len(set(ids)) != len(ids):
        errors.append('Scenario IDs must be unique.')
    inputs = [json.dumps(c.get('turns'), sort_keys=True) for c in cases]
    if len(set(inputs)) != len(inputs):
        errors.append('Duplicate input scenarios found.')
    for c in cases:
        label = c.get('id', '<missing>')
        turns = c.get('turns', [])
        if not turns or any(t.get('role') != 'user' or not t.get('content', '').strip() for t in turns):
            errors.append(f'{label}: expected nonempty user turns, executed sequentially with actual assistant replies.')
        expected = c.get('expected', {})
        if not expected.get('behavior') or not expected.get('required_checks'):
            errors.append(f'{label}: missing behavior or checks.')
        if not c.get('initial_state') or not c.get('provenance'):
            errors.append(f'{label}: missing state or provenance.')
        for collection in expected.get('collections', []):
            if collection not in {'fitness_programs', 'fitness_exercises'}:
                errors.append(f'{label}: invalid collection.')
        if expected.get('relevance_labels') and c.get('reference_status') != 'reviewed':
            errors.append(f'{label}: document labels require reviewed status.')
        if c.get('reference_status') == 'reviewed' and not c.get('review'):
            errors.append(f'{label}: reviewed scenarios require reviewer metadata.')
    return errors


def summary(cases):
    return {'scenarios': len(cases), 'user_messages': sum(len(c['turns']) for c in cases),
            'multi_turn_scenarios': sum(len(c['turns']) > 1 for c in cases),
            'categories': dict(Counter(c['category'] for c in cases)),
            'splits': dict(Counter(c['split'] for c in cases)),
            'reference_status': dict(Counter(c['reference_status'] for c in cases))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=DATASET)
    args = parser.parse_args()
    cases = load_cases(args.dataset)
    errors = validate(cases)
    manifest_path = args.dataset.with_name('manifest.json')
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if hashlib.sha256(args.dataset.read_bytes()).hexdigest() != manifest['sha256']:
            errors.append('Manifest SHA256 does not match dataset; version/review the change.')
    print(json.dumps({'summary': summary(cases), 'errors': errors}, indent=2))
    raise SystemExit(bool(errors))


if __name__ == '__main__':
    main()

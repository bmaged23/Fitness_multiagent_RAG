"""Fail releases on incomplete evaluation, invalid scores, or quality regression."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def check(candidate, baseline, policy):
    errors = []
    count = policy['expected_cases']
    for name, report in [('candidate', candidate), ('baseline', baseline)]:
        if report.get('dataset_version') != policy['dataset_version']:
            errors.append(f'{name}: wrong dataset version')
        fingerprint = report.get('dataset_sha256', report.get('configuration', {}).get('dataset_sha256'))
        if fingerprint != policy['dataset_sha256']:
            errors.append(f'{name}: wrong frozen dataset fingerprint')
        if report.get('cases') != count or report.get('completed') != count:
            errors.append(f'{name}: all {count} cases must complete')
    for direction, names in [('higher_is_better', policy['higher_is_better']),
                             ('lower_is_better', policy['lower_is_better'])]:
        for metric in names:
            values = []
            for name, report in [('candidate', candidate), ('baseline', baseline)]:
                entry = report.get('metrics', {}).get(metric, {})
                value = entry.get('mean')
                if (entry.get('scored_cases') != count or entry.get('total_cases') != count
                        or isinstance(value, bool) or not isinstance(value, (float, int))
                        or not math.isfinite(value) or not 0 <= value <= 1):
                    errors.append(f'{name}: {metric} needs {count} valid scores in [0, 1]')
                    values.append(None)
                else:
                    values.append(value)
            if None in values:
                continue
            actual, reference = values
            regression = reference - actual if direction == 'higher_is_better' else actual - reference
            if regression > policy['maximum_absolute_regression'] + 1e-12:
                errors.append(f'{metric}: regression {regression:.4f} exceeds allowed absolute drop')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, default=Path('evaluation/results/corpus-golden-baseline.json'))
    parser.add_argument('--policy', type=Path, default=Path('evaluation/release-gate.json'))
    args = parser.parse_args()
    errors = check(*(json.loads(path.read_text()) for path in [args.candidate, args.baseline, args.policy]))
    for error in errors:
        print('FAIL:', error)
    if errors:
        raise SystemExit(1)
    print('PASS: 100/100 completed; all required metrics within release regression limits.')


if __name__ == '__main__':
    main()

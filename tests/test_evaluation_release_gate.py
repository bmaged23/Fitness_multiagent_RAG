import copy
import json
from pathlib import Path

from scripts.evaluation.check_release_gate import check

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    return (json.loads((ROOT / 'evaluation/results/corpus-golden-baseline.json').read_text()),
            json.loads((ROOT / 'evaluation/release-gate.json').read_text()))


def test_baseline_passes_and_missing_cases_fail():
    baseline, policy = fixture()
    candidate = copy.deepcopy(baseline)
    assert check(candidate, baseline, policy) == []
    candidate['completed'] = 99
    assert check(candidate, baseline, policy)


def test_directions_and_missing_or_invalid_judgments_fail():
    baseline, policy = fixture()
    for metric, value in [('correctness_f1', 0.5), ('unsupported_claim_rate', 0.2),
                          ('faithfulness', float('nan')), ('recall_at_5', None)]:
        candidate = copy.deepcopy(baseline)
        candidate['metrics'][metric]['mean'] = value
        assert check(candidate, baseline, policy)
    candidate = copy.deepcopy(baseline)
    candidate['metrics']['faithfulness']['scored_cases'] = 99
    assert check(candidate, baseline, policy)


def test_small_judge_variation_allowed_and_wrong_dataset_fails():
    baseline, policy = fixture()
    candidate = copy.deepcopy(baseline)
    candidate['metrics']['correctness_f1']['mean'] -= 0.02
    assert not check(candidate, baseline, policy)
    candidate['dataset_version'] = 'another-dataset'
    assert check(candidate, baseline, policy)

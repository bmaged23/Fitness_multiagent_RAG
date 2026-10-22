"""Export evaluation examples locally; optional explicit upload to LangSmith."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from scripts.evaluation.validate_dataset import load_cases, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['development', 'held_out'], default='development')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--upload', action='store_true')
    parser.add_argument('--allow-draft', action='store_true', help='Explicitly upload unreviewed scenarios for annotation, not benchmark claims.')
    parser.add_argument('--dataset-name', default='fitness-scenarios-v1-development-draft')
    args = parser.parse_args()
    if args.split not in args.dataset_name:
        parser.error('Dataset name must include the selected split to avoid mixing tuning and held-out examples.')
    cases = load_cases()
    errors = validate(cases)
    if errors:
        parser.error('; '.join(errors))
    examples = [{'inputs': {'scenario_id': c['id'], 'turns': c['turns'], 'initial_state': c['initial_state'],
                             'fault_injection': c.get('fault_injection')},
                 'outputs': c['expected'],
                 'metadata': {key: c[key] for key in ['id', 'category', 'split', 'reference_status', 'provenance']}}
                for c in cases if c['split'] == args.split]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(examples, indent=2, ensure_ascii=False)+'\n')
    if not args.upload:
        print(f'Exported {len(examples)} examples locally. No cloud calls made.')
        return
    if any(c['metadata']['reference_status'] != 'reviewed' for c in examples) and not args.allow_draft:
        parser.error('References are unreviewed. Review them first or use --allow-draft for annotation only.')
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / '.env')
    from langsmith import Client
    client = Client()  # Credentials come from environment; never saved in examples.
    # Use a fresh dataset so retries cannot silently duplicate examples in an existing set.
    dataset = client.create_dataset(dataset_name=args.dataset_name,
        description='Synthetic fitness scenarios; consult reference_status before treating examples as a benchmark.')
    client.create_examples(dataset_id=dataset.id, examples=examples)
    print(f'Uploaded {len(examples)} examples to dataset {dataset.id}. No application evaluation was run.')


if __name__ == '__main__':
    main()

# Script guide

Run commands from the repository root. Follow the main README for the required configuration and exact invocation order.

| Location | Purpose |
|---|---|
| `download_dataset.py`, `chunk_data.py`, `embed_and_index.py` | Download, prepare and index the workout corpus. |
| `init_db.py` | Initialize application storage. |
| `download_speech_models.py` | Download optional speech model assets. |
| `inspect_collections.py`, `inspect_schema.py` | Inspect configured storage. |
| `smoke_container.py`, `smoke_provisioning.py` | Verify the built image and isolated first-run provisioning. |
| `evaluation/` | Golden dataset creation, source snapshots, retrieval, generation, judge scoring, LangSmith export and release gating. |
| `performance/` | CPU/GPU embedding benchmarks, containerized Coach measurements and report generation. |

The active automated evaluation entry points are `prepare_ci_fixtures`, `run_golden_retrieval`, `run_golden_answers` and `check_release_gate` under `scripts.evaluation`. Other evaluation scripts support reproducibility of the earlier pilots; see `evaluation/README.md` and `docs/EVALUATION_PROCESS.md` before running them. Some scripts make billable provider calls or write configured databases; they are not all offline checks.

Use `python -m scripts.evaluation.<module>` or `python -m scripts.performance.<module>` as shown in the documentation. Local raw outputs belong in ignored `.evaluation-local/` and `.release-local/`, not tracked source folders.

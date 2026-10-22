# Release improvement progress

22 October 2026. Baseline: `8d44c51dc706d03cfbaeed0a89e45b3064a59e8c`.

## Verified so far

- New isolated `.venv` on Python 3.12.15, installed from resolved `requirements-dev.txt`; dependency consistency check passes for 104 distributions.
- All 96 pre-existing offline tests passed in 10.94 seconds. These use mocked model/tool responses where appropriate; they do not measure real LLM quality, retrieval recall or speech accuracy.
- Python syntax compilation and the Node microphone-status regression check passed.
- Separate `requirements-core.in` / `requirements-core.txt` and development input/lock files provide a light text/test dependency route. The original full GPU demo snapshot remains in requirements.txt; it has not been revalidated.

- After the indexing fix: **100 tests passed in 4.89 seconds**, with JUnit output generated locally. Microphone regression and dependency checks also pass.

## Changes implemented

- Default pytest run excludes the three live cloud-agent scripts. To run those explicitly, use their documented `python tests/test_*.py` entry points with your own credentials, Qdrant collections and downloaded embeddings. Cloud calls may incur usage.
- Indexing preserves existing collections by default; `--reseting` explicitly rebuilds. Missing collections are created during initial indexing. Regression tests cover preservation and first-run creation. Same-ID upserts still replace matching points; this is not a backup strategy.
- `SQLITE_DB_PATH` can override the SQLite file location for isolated runs and future container volumes.
- A GitHub workflow runs offline tests, dependency consistency and microphone checks. It has not yet been pushed or verified remotely.

## Still required

Clean full embedding/GPU speech installation; real retrieval and agent evaluation; measured timings/resources/cost; application Docker image and model/corpus provisioning/license review; container checks; public Docker Hub publication and pull test; image release workflow; complete README rewrite and remote CI verification. No new quality, Docker readiness or deployment claim is justified yet.

## Evaluation dataset added

100 authored scenarios / 127 user messages / 20 multi-turn conversations, split into 30 development and 70 held-out scenarios. Manifest and structure validation pass. 51 cases await corpus review, 49 await behavior review. Added deterministic retrieval scoring (missing labels remain unscored), LangSmith local export/explicit upload, and review/scoring documentation. Full offline suite: 107 passed in 4.91 seconds. These are test suite results, not RAG answer-quality scores. Live corpus retrieval, judge evaluation and LangSmith experiment execution remain pending.

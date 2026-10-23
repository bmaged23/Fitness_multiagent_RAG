# Release improvement progress

Current verified release: [successful CI/CD run](https://github.com/bmaged23/Fitness_multiagent_RAG/actions/runs/39876219203), public CPU image and 100-case gate completed. See [release verification](RELEASE_VERIFICATION.md) for digest, supported route and limitations. The entries below are chronological implementation history; earlier pending items may have been completed by later entries.

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

## Real retrieval pilot, 22–23 October 2026

Read-only snapshot of existing Qdrant: 2,594 programs and 3,213 exercises. CUDA direct retrieval ran on 16 development cases. Thirty development scenarios were uploaded to the EU LangSmith workspace. Direct/explicit-filter experiments and LLM-judge evidence reviews are recorded there. The real Gemma Retriever ran before and after prompt fixes on the same 16 development scenarios; see evaluation/RETRIEVAL_PILOT_RESULTS.md for results and limitations. No full Coach/Designer, memory, speech or 70-case held-out evaluation is complete. Mistral judge comparison is blocked by the provider's plan restriction; gpt-oss:120b judgments are available. Raw traces/corpus and the LangSmith key are excluded from Git.

## 23 October: completed corpus QA and release gate

The primary source-first golden benchmark now has 100 completed cases with 100 valid scores per dimension. See `evaluation/GOLDEN_QA_RESULTS.md`. This completes the requested direct RAG evaluation phase; full Coach/Designer, speech and memory end-to-end quality remain outside this benchmark.

Added a CI/CD workflow for trusted master pushes and manual runs: offline tests → fresh GPU retrieval for all 100 cases → fresh Gemma answers → separate GPT-OSS correctness and faithfulness judging → completeness/regression gate → build/smoke-test/publish/pull-test Docker image. The checked-in policy allows a maximum 0.03 absolute regression from the frozen baseline. No raw corpus or case-level answer traces are uploaded as public CI artifacts.

Local offline suite after gate implementation: 130 passed. Docker image build and public publication are in progress. Remote GPU runner registration, repository evaluation secrets and Docker publishing secrets are not yet verified. The workflow files alone do not establish a working remote deployment.

## Container and runner checks before publication

The Linux amd64 CPU application image built successfully from its pinned lock file; `pip check` passed. Real 1024-dimensional BGE inference, SQLite signup/login, PDF generation, Streamlit HTTP health and actual login UI rendering passed inside the image. The official GitHub runner v2.338.1 was downloaded with its upstream SHA-256 verified, registered as `bola-fitness-gpu`, and confirmed online. Private frozen fixtures/model/Qdrant variables and four encrypted Actions secrets are configured. CI execution and public publication/pull verification remain pending.

## Isolated provisioning verification

The first-run container check caught and fixed an embedding API compatibility issue: the pinned Sentence Transformers runtime uses `get_sentence_embedding_dimension()`. The release smoke suite now provisions synthetic CSV records into a disposable Qdrant, performs real indexing and retrieval, and verifies the account and prepared files persist across separate containers using the same named volume. The corrected full smoke suite passed locally (provisioning/persistence phase: 30.56 seconds). This is an integration check, not a synthetic-data model-accuracy benchmark. A real containerized Coach request also succeeded with the existing corpus and Ollama Cloud (38.99 seconds for one request; no average or first-token claim).

The first live CI attempt exposed an invalid judge evidence ID. Bounded retries now apply only to malformed judgments or transient service failures; valid low scores remain unchanged. Attempt logs and available token usage are retained. Local offline suite: 132 passed.

## Verified automatic release

Commit `bbbdfdd83a1c45b50d8269d8062db8a1706d755b` completed the full gated release workflow, including public publication and post-publication pull checks. All 100 cases were scored; correctness F1 0.8101, faithfulness 0.9925, retrieval nDCG@5 0.7179. The baseline remains unchanged. Public image/verification details are recorded in `RELEASE_VERIFICATION.md`.

Independent laptop verification of the public digest also passed the full container suite. All 133 pinned runtime distributions matched the published image exactly (pip is the extra installer). The local 104-distribution dev environment passed consistency checks. `.gitignore` coverage includes additional environment/model/report directories; `.dockerignore` keeps the image build context restricted to application files. Docker Hub's public description and README now link to setup/release documentation.

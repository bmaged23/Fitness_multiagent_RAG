# CI/CD: tests, 100-case evaluation, Docker Hub

## What runs

`tests.yml` runs offline tests on pushes and pull requests. It needs no private keys, GPU or model downloads.

`evaluate-and-release.yml` runs on trusted `master` pushes affecting application code, tests, dependencies, evaluation or release configuration, and on manual dispatch. Documentation-only changes run the offline workflow without repeating 300 cloud calls or publishing an unchanged image.

1. Install pinned development dependencies and pass offline Python/JavaScript tests.
2. Check out the new commit on a dedicated self-hosted Linux x64 GPU runner labeled `fitness-eval`.
3. Copy only hash-verified frozen corpus/100-case fixtures from private storage outside the checkout. Load the pinned local BGE model and query the provisioned Qdrant collections; no stored answers or previous checkpoints are reused.
4. Generate 100 fresh Gemma answers and 200 GPT-OSS judge assessments via Ollama Cloud; record a separate LangSmith experiment.
5. Require 100 completed cases and 100 valid scores for each gated metric. Compare against the checked-in baseline with a maximum **0.03 absolute regression** per metric, reversing direction for unsupported-claim rate. This tolerance handles small run variation; it is not a confidence interval or statistical significance test.
6. On a GitHub-hosted runner, build the CPU image, smoke-test model inference, account storage, PDF export, the actual login UI, isolated first-run indexing and restart persistence, then publish to Docker Hub. Pull the published image and smoke-test again.

The reference answers never enter generation. CI never silently treats missing judgments, quota failures or incomplete runs as success. The existing benchmark is a reusable regression suite now, not a permanently untouched test set.

Judge schema/evidence-ID validation failures and transient service errors allow up to three attempts, with attempts and observed token usage recorded. A valid low score is never retried. Persistent invalid results still fail the strict 100-case gate; authentication/plan restrictions do not trigger repeated retries.

## Why GitHub can reach the models and vectors

A normal GitHub-hosted runner cannot reach a laptop's `localhost`. The evaluation job therefore uses a **self-hosted runner** on the GPU machine. It checks out the pushed commit into a disposable workspace and accesses the locally provisioned model, frozen fixtures and Qdrant through explicit repository variables. The machine, runner and database must be running. A private server can replace the laptop later.

Only trusted master pushes/manual runs use that runner, never pull-request code. Keep its service account separate from personal data. All code executed on a self-hosted runner has that account's permissions.

The evaluation pipeline measures direct retrieval and answer generation. App changes outside that path (Coach/Designer, memory, UI, voice) are covered by their separate tests, not by a claim of full end-to-end golden evaluation. The frozen corpus is checked by hash and actual retrieved payloads are checked against it. Complete provenance of historical indexed vectors remains unavailable.

## One-time runner setup

Register a Linux x64 self-hosted runner using this repository's GitHub **Settings → Actions → Runners → New self-hosted runner** instructions. Give it the custom label `fitness-eval`. Install Python 3.12 with venv support. Provide a CUDA-compatible embedding interpreter with PyTorch/Transformers and the BGE model revision `d4aa6901d3a41ba39fb536a557fa166f842b0e09`.

Private fixture layout, outside the Actions checkout:

```text
fitness-evaluation-fixtures/
  corpus/fitness_programs.jsonl
  corpus/fitness_exercises.jsonl
  golden/fitness-corpus-qa-v1.jsonl
```

These must be the original frozen files with manifest-matching hashes. Fresh CSV chunking generates new UUIDs and does not reproduce this benchmark's reference IDs. Provision Qdrant with the matching indexed corpus before running the workflow. No job deletes or rebuilds existing collections.

Set these repository **Actions variables** to paths/URL reachable from the runner:

| Variable | Meaning |
|---|---|
| `FITNESS_EVAL_FIXTURES` | Absolute path to the private fixture root above |
| `FITNESS_EMBEDDING_PYTHON` | Absolute path to the dedicated GPU Python interpreter |
| `FITNESS_EMBEDDING_MODEL` | Absolute path to the pinned BGE model directory |
| `FITNESS_QDRANT_URL` | Qdrant URL from the runner, e.g. `http://127.0.0.1:6333` |

Set these repository **Actions secrets**:

| Secret | Meaning |
|---|---|
| `OLLAMA_API_KEY` | Ollama Cloud key with access to `gemma4:31b` and `gpt-oss:120b` |
| `LANGSMITH_API_KEY` | LangSmith key authorized for datasets and experiments |
| `DOCKERHUB_USERNAME` | Docker Hub publisher username (`bmaged23`) |
| `DOCKERHUB_TOKEN` | Docker Hub token with read/write permission |

The workflow uses the EU LangSmith endpoint; change it for another workspace region. API usage can incur charges. Two concurrent cases are used, with a 90-minute evaluation timeout. There is no automatic schedule; trusted pushes and explicit manual runs trigger it.

Only aggregate summaries are uploaded as GitHub artifacts. Raw contexts, answers and detailed judge evidence remain private on the runner and in the configured LangSmith workspace. The fresh checkout removes stale evaluation checkpoints before subsequent runs.

## Status

Workflow and regression-gate tests are implemented. The Linux runner `bola-fitness-gpu` is registered and online; private fixture/model/database variables and the four required Actions secrets are configured. Full remote execution and automatic public release passed for commit `bbbdfdd83a1c45b50d8269d8062db8a1706d755b`: [workflow evidence](https://github.com/bmaged23/Fitness_multiagent_RAG/actions/runs/39876219203).

On the current laptop the runner is a user process under `/home/bmage/projects/.release-runners/fitness`; it does not auto-start after a reboot/WSL shutdown. Start `./run.sh` in that directory to resume it. Its log is `runner.log`. Private fixtures live under `/home/bmage/projects/fitness-evaluation-fixtures`. Keep this infrastructure outside the public repository. Do not start a second listener while one is already running.

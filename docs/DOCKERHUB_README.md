# Fitness Multi-Agent RAG

**[GitHub repository, source code and demo](https://github.com/bmaged23/Fitness_multiagent_RAG)**

A Streamlit fitness coach with Coach, Program Designer and Retriever agents, retrieval-grounded workout planning, persistent SQLite context, nutrition plans and PDF exports.

The public Linux amd64 CPU image includes BGE embeddings. You supply LLM credentials and provision the workout corpus once. Optional GPU speech uses the source installation.

## Run the Fitness application with Docker

Public image: `bmaged23/fitness-multiagent-rag:cpu` (Linux amd64). Publication, CI post-publication pull/smoke checks and anonymous registry access are verified:

https://hub.docker.com/r/bmaged23/fitness-multiagent-rag

The image contains the Streamlit application, three agents, SQLite schema, PDF export, corpus preparation scripts and **BGE-large-en-v1.5** at revision `d4aa6901d3a41ba39fb536a557fa166f842b0e09`. It uses CPU inference so NVIDIA hardware is not required. Optional Whisper/Kokoro GPU speech is available through the source route and is disabled in this image.

The LLM runs through your configured provider; its weights are not bundled. The workout corpus is downloaded separately using your Kaggle account and indexed into the persistent Qdrant volume. The image does not contain personal accounts, saved plans, API keys, evaluation traces or redistributed workout data. BGE's model card declares MIT licensing; its upstream README is bundled with the weights.

### Local resource requirements

The main LLM is hosted on Ollama Cloud in the default cloud configuration; its model weights and inference do not use local RAM/VRAM. This image runs the embedding model locally, alongside Streamlit, Qdrant and SQLite. Local STT/TTS are optional through the GPU source route and are disabled in this CPU image. Local model requirements are therefore lighter than hosting the main LLM, while actual application latency and resource usage still need direct measurement.

### Requirements

Docker Engine/Desktop with Compose v2, Linux amd64 container support, internet for the initial corpus download and LLM calls, and your own Kaggle/provider credentials. Allow at least 8 GB available RAM and 8 GB free disk as an initial provisioning budget; full-stack peak resource usage is not yet measured. macOS/Windows require Docker Desktop; ARM native execution is not validated.

Commands below use a Bash shell (Linux/WSL2).

### Pull and configure

```bash
git clone https://github.com/bmaged23/Fitness_multiagent_RAG.git
cd Fitness_multiagent_RAG
cp .env.example .env
# Edit .env: provider URL/model/key and Kaggle credentials.
docker pull bmaged23/fitness-multiagent-rag:cpu
docker compose -f docker/compose.app.yml up -d qdrant
```

For Ollama Cloud, set `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL=https://ollama.com`, an account-accessible `OLLAMA_MODEL`, and `OLLAMA_API_KEY`. Container localhost refers to the container itself: if using a host Ollama service, supply a URL reachable from the container. Compose sets the internal Qdrant URL automatically.

### Provision the corpus once

Run in order; the embedding model is already included in the image:

```bash
docker compose -f docker/compose.app.yml run --rm app python scripts/download_dataset.py
docker compose -f docker/compose.app.yml run --rm app python scripts/chunk_data.py
docker compose -f docker/compose.app.yml run --rm app python scripts/embed_and_index.py --no-reseting
docker compose -f docker/compose.app.yml run --rm app python scripts/inspect_collections.py
docker compose -f docker/compose.app.yml run --rm app python scripts/init_db.py
```

The source is Kaggle's `adnanelouardi/600k-fitness-exercise-and-workout-program-dataset`. Review its source terms before use. These commands require provider-independent Kaggle access; a model image cannot supply account credentials. CPU indexing can take time. Do not run chunking/indexing concurrently or repeat chunking on an existing index without planning a versioned replacement: chunk generation assigns UUIDs.

### Launch

```bash
docker compose -f docker/compose.app.yml up -d app
docker compose -f docker/compose.app.yml ps
curl --fail http://localhost:8501/_stcore/health
```

Open http://localhost:8501, create an account, and ask for a workout plan. Approve a draft explicitly to save it, then download its PDF in My plans. Chat needs a working LLM key/model and populated collections; HTTP health alone only establishes that Streamlit is serving.

The `fitness_data` volume stores downloaded/prepared data, SQLite accounts, coaching state and saved plans. The `fitness_vectors` volume stores Qdrant. Back these up before upgrading. Keep the service on localhost unless you configure secure hosting.

```bash
# Logs and graceful shutdown; data is retained.
docker compose -f docker/compose.app.yml logs --tail=100 app
docker compose -f docker/compose.app.yml down
# Upgrade after a successful release, retaining volumes.
docker compose -f docker/compose.app.yml pull
docker compose -f docker/compose.app.yml up -d
```

Avoid `down -v` unless deliberately deleting stored data. For a local build use `docker compose -f docker/compose.app.yml build app`.

### Verification

The image smoke test performs real 1024-dimensional BGE inference, SQLite signup/login, PDF generation, HTTP health, actual Streamlit login UI rendering, synthetic CSV preparation, first-run indexing against a disposable Qdrant, retrieval, and persistent accounts across separate containers:

```bash
python3 scripts/smoke_container.py --image bmaged23/fitness-multiagent-rag:cpu
```

It creates and deletes its own temporary container and leaves your application volumes alone. Corpus retrieval and cloud answer quality are evaluated separately by the [100-case release gate](https://github.com/bmaged23/Fitness_multiagent_RAG/blob/master/docs/CI_CD.md). The [release verification record](https://github.com/bmaged23/Fitness_multiagent_RAG/blob/master/docs/RELEASE_VERIFICATION.md) identifies the tested source and CI evidence. Published CPU image digest:

```text
sha256:607ea87c7098638bd0f1227b848d0574bb413842cabf7cf69f4703e50662fc8b
```

For the exact release rather than the moving `cpu` tag:

```bash
docker pull bmaged23/fitness-multiagent-rag@sha256:607ea87c7098638bd0f1227b848d0574bb413842cabf7cf69f4703e50662fc8b
```

You can set this digest as `app.image` in Compose for a fixed deployment. On memory-constrained machines, add `EMBEDDING_BATCH_SIZE=8` to `.env` before corpus indexing.

## How we evaluated the RAG pipeline

We evaluated **100 corpus-derived questions** with fixed reference evidence and answers. This benchmark measures direct retrieval and answer generation. Offline tests separately check application behavior; the benchmark does not run the entire Coach/Designer, memory or speech workflow.

### 1. Inspect the corpus and freeze the reference dataset

We inspected the existing index containing **2,594 program records and 3,213 exercise records**, then used a fixed random seed to select 100 source-first questions:

| Question type | Cases |
|---|---:|
| Program facts | 50 |
| Exercise facts | 30 |
| Program comparisons | 10 |
| Program/exercise joins | 10 |

The questions use 120 distinct source records. Before running retrieval, every question received reference chunk IDs, source hashes, required facts and a reference answer derived from the recorded data. Similarity search did not define the ground truth. The source-relative facts were mechanically validated; there was no independent human adjudication or scientific fitness-truth certification.

Dataset and corpus hashes identify the frozen inputs. The original split was 30 development and 70 held-out questions with disjoint source anchors. All 100 have now been evaluated and reused for regression checking, so they are no longer an untouched final test set.

### 2. Retrieve evidence without showing the references

For each question, the pinned **BGE-large-en-v1.5** encoder creates a normalized embedding on the local GPU. The baseline searches both Qdrant collections, requests five candidates from each and merges them into a global cosine-ranked top five. It receives the question, without gold chunk IDs, reference answers or gold collection routes.

Actual retrieved payloads are checked against the frozen corpus. We compare the retrieved IDs/ranks with the reference chunks using:

- **Recall@5:** fraction of required source records retrieved.
- **nDCG@5:** graded relevance discounted by rank, normalized against the ideal ranking. Equally necessary sources have equal grades; either order is ideal.
- **MRR@5:** reciprocal rank of the first relevant result, or zero if none appears.
- **Precision@5:** relevant reference records divided by five. For these named-record questions, its ceiling is 0.2 for one required source and 0.4 for two; it is not an open-ended semantic relevance score.

The displayed ranking score out of 100 is `100 × mean nDCG@5`. Retrieval metrics are calculated in Python, without an LLM judge.

### 3. Generate a fresh answer

**Gemma 4 31B on Ollama Cloud** receives only the question and the actual retrieved contexts. It is asked to report recorded facts accurately, cite evidence and admit missing information. It never receives the reference answer or required reference facts.

### 4. Judge correctness and relevance

A separate **GPT-OSS 120B call on Ollama Cloud** receives the question, generated answer, reference answer and required reference facts. Every required fact is marked correct, incorrect or missing.

Python calculates:

- **Correctness precision:** correct facts / (correct + incorrect facts).
- **Completeness:** correct facts / all required facts.
- **Correctness F1:** harmonic mean of correctness precision and completeness.
- **Answer relevance:** a separate 0–4 judge rubric, normalized to 0–1.

These are custom required-fact scores. They are not native Ragas AnswerCorrectness scores and do not independently establish real-world scientific truth.

### 5. Judge faithfulness using the actual evidence

Another independent GPT-OSS 120B call receives the question, generated answer and **actual retrieved contexts**. It does not receive reference answers or gold facts.

The judge decomposes the answer into factual claims and checks whether the retrieved evidence supports each claim. Python validates cited source IDs and calculates:

- **Faithfulness:** supported claims / all evaluated factual claims.
- **Unsupported-claim rate:** `1 − faithfulness`.

An answer with no factual claims remains unscored, rather than receiving an automatic perfect score. A grounded answer can still be incomplete; a plausible answer can still lack support. That is why correctness, completeness and faithfulness remain separate.

### 6. Validate, save and compare

Python validates judge schemas and fact/source IDs. Invalid judgments or transient service failures allow up to three attempts, with available usage and attempts recorded. A valid low score is never retried to obtain a better result. Persistent failures remain unscored.

LangSmith stores the dataset, experiment traces, outputs and individual feedback scores. Python orchestrates the evaluation; Ollama Cloud runs the answer and judge models. These are custom LangSmith evaluators, not an installed/executed Ragas evaluation. Raw local contexts and detailed evidence remain outside Git; public CI artifacts contain aggregate summaries.

We average each metric separately and report its valid denominator. There is no combined score hiding the individual dimensions. LLM judgments can be wrong and still require human calibration.

### 7. Use the results as a CI/CD gate

Trusted application-code pushes repeat all 100 retrievals, generate 100 fresh answers and obtain 200 valid judge assessments. Publication requires 100 completed cases and 100 valid scores for each gated metric. A metric may regress by at most **0.03 absolute** against the original frozen baseline; unsupported-claim rate uses the opposite direction because lower is better. This is an operational tolerance, not a statistical significance test.

After passing, CI builds and tests the image, publishes it to Docker Hub, pulls it and repeats the container tests. Documentation-only pushes run offline CI without repeating the live benchmark. The laptop GPU runner, model and Qdrant must be online; the image publication job runs on GitHub-hosted infrastructure.

### Results

All 100 cases were scored in each completed run. Values below are mean metrics, not percentages of questions passed. Differences between the two runs do not demonstrate a model improvement.

| Metric | Original baseline | Verified release CI |
|---|---:|---:|
| nDCG@5 | 0.7179 | 0.7179 |
| Recall@5 | 82.00% | 82.00% |
| MRR@5 | 0.7095 | 0.7095 |
| Correctness precision | 84.33% | 83.17% |
| Correctness F1 | 81.65% | 81.01% |
| Completeness | 80.20% | 79.80% |
| Relevance | 90.75% | 91.00% |
| Faithfulness | 97.83% | 99.25% |
| Unsupported claims | 2.17% | 0.75% |

[Original report](https://github.com/bmaged23/Fitness_multiagent_RAG/blob/master/evaluation/GOLDEN_QA_RESULTS.md) · [CI results JSON](https://github.com/bmaged23/Fitness_multiagent_RAG/blob/master/docs/release-evaluation-summary.json) · [Successful release workflow](https://github.com/bmaged23/Fitness_multiagent_RAG/actions/runs/39876219203) · [CI/CD setup](https://github.com/bmaged23/Fitness_multiagent_RAG/blob/master/docs/CI_CD.md)

## Latency, resources and measured optimizations

Measured on 23 October 2026. The main LLM uses Ollama Cloud. Local model workloads are embeddings and optional STT/TTS; the published CPU image disables speech. Streamlit, Qdrant and SQLite still use local resources. This keeps local model requirements lighter than hosting the main LLM, without assuming whole-application usage is negligible.

![CPU/GPU embedding comparison](https://raw.githubusercontent.com/bmaged23/Fitness_multiagent_RAG/master/docs/performance/cpu-gpu-comparison.svg)

Hardware: **Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz**, **NVIDIA GeForce GTX 1660 Ti**; 12 logical CPUs visible. GPU capacity 6,144 MiB, driver 560.76; Linux/WSL memory limit about 7.66 GiB. CPU embedding runs use two OpenMP threads. These figures are specific to this hardware and workload.

### Embedding comparison

The same 20 development questions were encoded three times per configuration (60 encodings each), using the same frozen BGE weights, CLS pooling, normalization and FP32. CPU uses two OpenMP threads. First batches are excluded from warm statistics.

| Configuration | Warm median | Warm p95 | Standard deviation | Peak process RAM | Peak CUDA allocation | Warm throughput |
|---|---:|---:|---:|---:|---:|---:|
| CPU · batch 1 | 260.25 ms | 336.81 ms | 36.13 ms | 1851.1 MiB | Not used | 3.74/s |
| GPU · batch 1 | 18.27 ms | 32.50 ms | 5.23 ms | 1954.5 MiB | 1289.9 MiB | 48.29/s |
| GPU · batch 4 | 12.96 ms | 15.92 ms | 1.67 ms | 1859.6 MiB | 1295.8 MiB | 75.14/s |

GPU single-query median encoding was **14.24× faster** than CPU in this run. GPU batching increased measured warm throughput by **1.56×** over GPU batch 1. Batch-4 values are amortized batch times, with 14 warm batches; single-query configurations have 59 warm samples. Queue waiting is not included, so batching is not automatically better for interactive single-user latency.

CPU/GPU minimum vector cosine agreement was 0.999999999998; GPU single/batch agreement was 1.000000000000. This checks numerical agreement, not complete application answer quality.

Peak GPU allocation was 1.27 GiB. Whole-device NVIDIA monitoring peaked at 44.0% utilization for batch 1 and 63.0% for batch 4; those observations include startup and other device users, so they are not per-request or per-process utilization. Process CPU averaged 173.75%, 98.79%, 99.28% of one core respectively; 100% means one occupied core, not all 12 visible logical CPUs.

### Actual published CPU-image requests

Five read-only synthetic requests used the actual compiled Coach graph, existing indexed corpus, bundled CPU embeddings and Gemma 4 31B through Ollama Cloud. A disposable account/database was used; no real user state was opened. Requests completed in **2.36–13.02 seconds**, with median **3.30 seconds** and mean **5.60 seconds**. Embeddings were prewarmed and the compiled graph was reused.

| Sample | Backend completion | LLM calls | Embedding time | Qdrant time |
|---|---:|---:|---:|---:|
| 1 | 2.42 s | 2 | 0.000 s | 0.000 s |
| 2 | 13.02 s | 7 | 0.509 s | 0.126 s |
| 3 | 6.90 s | 5 | 0.191 s | 0.044 s |
| 4 | 2.36 s | 2 | 0.000 s | 0.000 s |
| 5 | 3.30 s | 2 | 0.000 s | 0.000 s |

Peak sampled Coach-process RAM was **1751.4 MiB (1.71 GiB)**. Per-request CPU averaged **4.54–12.06% of one logical core**; cloud/network wait is included in elapsed time. This CPU image uses no CUDA. External Qdrant, OS/browser resources and provider-side inference resources are excluded from these process numbers.

**Output-quality observation:** Named-record question #2 missed a known indexed program. Timing completion is not a correctness pass; no output-quality improvement is claimed. These five operational requests do not replace the separately scoped 100-case direct-RAG quality evaluation.

### Optimization findings

- **Model residency:** the first CPU embedding call, including imports/model loading/inference, took 6.98 s; five subsequent calls had median 156.20 ms. The existing application model cache avoids repeating cold initialization.
- **GPU acceleration and batching:** the worker comparisons above verify lower embedding latency and higher batch throughput. The portable public image remains CPU-based; these GPU figures do not describe that image.
- **Main bottleneck:** recorded cloud LLM calls summed to about 96.2% of the five backend request durations, including network/service wait. Speeding up embeddings alone will not produce a 14× whole-application speedup.
- **Visible latency:** a separate native model stream produced first content in 0.767 s and completed in 1.018 s. It has no agent/tool steps and uses think=false. The current UI buffers the background job, so this is **not** the app’s user-visible TTFT. Browser rendering/polling adds delay beyond measured backend availability.
- **Next useful targets:** fewer unnecessary model/tool round trips and safely streamed user-facing text offer larger potential gains. They require separate implementation and behavioral validation; this report does not claim they are deployed.

Across these five requests, observed API usage was 79,707 input and 5,340 output tokens across 18 calls. Billing/pricing was unavailable; no monetary cost is invented.

### Reproduce

Use the pinned project development environment for orchestration and a CUDA-enabled embedding interpreter/model for GPU measurements:

```bash
python -m scripts.performance.benchmark_embeddings \
  --embedding-python /path/to/gpu-venv/bin/python \
  --model /path/to/pinned-bge-model \
  --output .release-local/performance/embeddings-repeated
python -m scripts.performance.run_container_benchmark \
  --cloud-env /path/to/private.env \
  --qdrant-url http://host.docker.internal:6333
python -m scripts.performance.build_report
```

The container benchmark uses the verified public image digest and an isolated `/tmp` account. It makes real provider calls. On native Linux, set a container-reachable Qdrant URL; localhost inside a container is not the host. The embedding benchmark is also recorded by the trusted CI evaluation job, with aggregate performance artifacts. No hard latency gate is imposed on shared-hardware timings.

[Machine-readable aggregates](https://github.com/bmaged23/Fitness_multiagent_RAG/blob/master/docs/performance/measurements.json) · [Quality evaluation](https://github.com/bmaged23/Fitness_multiagent_RAG/blob/master/docs/EVALUATION_PROCESS.md)

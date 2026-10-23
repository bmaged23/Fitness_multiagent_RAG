# Latency, resources and measured optimizations

Measured on 23 October 2026. The main LLM uses Ollama Cloud. Local model workloads are embeddings and optional STT/TTS; the published CPU image disables speech. Streamlit, Qdrant and SQLite still use local resources. This keeps local model requirements lighter than hosting the main LLM, without assuming whole-application usage is negligible.

![CPU/GPU embedding comparison](performance/cpu-gpu-comparison.svg)

Hardware: **Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz**, **NVIDIA GeForce GTX 1660 Ti**; 12 logical CPUs visible. GPU capacity 6,144 MiB, driver 560.76; Linux/WSL memory limit about 7.66 GiB. CPU embedding runs use two OpenMP threads. These figures are specific to this hardware and workload.

## Embedding comparison

The same 20 development questions were encoded three times per configuration (60 encodings each), using the same frozen BGE weights, CLS pooling, normalization and FP32. CPU uses two OpenMP threads. First batches are excluded from warm statistics.

| Configuration | Warm median | Warm p95 | Standard deviation | Peak process RAM | Peak CUDA allocation | Warm throughput |
|---|---:|---:|---:|---:|---:|---:|
| CPU · batch 1 | 260.25 ms | 336.81 ms | 36.13 ms | 1851.1 MiB | Not used | 3.74/s |
| GPU · batch 1 | 18.27 ms | 32.50 ms | 5.23 ms | 1954.5 MiB | 1289.9 MiB | 48.29/s |
| GPU · batch 4 | 12.96 ms | 15.92 ms | 1.67 ms | 1859.6 MiB | 1295.8 MiB | 75.14/s |

GPU single-query median encoding was **14.24× faster** than CPU in this run. GPU batching increased measured warm throughput by **1.56×** over GPU batch 1. Batch-4 values are amortized batch times, with 14 warm batches; single-query configurations have 59 warm samples. Queue waiting is not included, so batching is not automatically better for interactive single-user latency.

CPU/GPU minimum vector cosine agreement was 0.999999999998; GPU single/batch agreement was 1.000000000000. This checks numerical agreement, not complete application answer quality.

Peak GPU allocation was 1.27 GiB. Whole-device NVIDIA monitoring peaked at 44.0% utilization for batch 1 and 63.0% for batch 4; those observations include startup and other device users, so they are not per-request or per-process utilization. Process CPU averaged 173.75%, 98.79%, 99.28% of one core respectively; 100% means one occupied core, not all 12 visible logical CPUs.

## Actual published CPU-image requests

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

## Optimization findings

- **Model residency:** the first CPU embedding call, including imports/model loading/inference, took 6.98 s; five subsequent calls had median 156.20 ms. The existing application model cache avoids repeating cold initialization.
- **GPU acceleration and batching:** the worker comparisons above verify lower embedding latency and higher batch throughput. The portable public image remains CPU-based; these GPU figures do not describe that image.
- **Main bottleneck:** recorded cloud LLM calls summed to about 96.2% of the five backend request durations, including network/service wait. Speeding up embeddings alone will not produce a 14× whole-application speedup.
- **Visible latency:** a separate native model stream produced first content in 0.767 s and completed in 1.018 s. It has no agent/tool steps and uses think=false. The current UI buffers the background job, so this is **not** the app’s user-visible TTFT. Browser rendering/polling adds delay beyond measured backend availability.
- **Next useful targets:** fewer unnecessary model/tool round trips and safely streamed user-facing text offer larger potential gains. They require separate implementation and behavioral validation; this report does not claim they are deployed.

Across these five requests, observed API usage was 79,707 input and 5,340 output tokens across 18 calls. Billing/pricing was unavailable; no monetary cost is invented.

## Reproduce

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

[Machine-readable aggregates](performance/measurements.json) · [Quality evaluation](EVALUATION_PROCESS.md)

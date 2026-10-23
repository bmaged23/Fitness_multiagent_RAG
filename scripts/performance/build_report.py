"""Publish measured aggregates and SVG figures without private answer/context traces."""
from __future__ import annotations
import json
from pathlib import Path
import statistics
import html
import re

ROOT=Path(__file__).resolve().parents[2]


def percentile(values,p):
    items=sorted(values);position=(len(items)-1)*p
    lower=int(position);upper=min(lower+1,len(items)-1)
    return items[lower]+(items[upper]-items[lower])*(position-lower)


def main():
    embed=json.loads((ROOT/'.release-local/performance/embeddings-repeated/summary.json').read_text())
    coach=json.loads((ROOT/'.release-local/performance/coaching/results.json').read_text())
    hardware=embed.get('hardware',{})
    rows=[]
    for run in embed['runs']:
        warm=[b['seconds']/b['size']*1000 for b in run['runtime']['batches'][1:]]
        rows.append({'label':'CPU · batch 1' if run['device']=='cpu' else f'GPU · batch {run["batch_size"]}',
                     'device':run['device'],'batch_size':run['batch_size'],'encodings':run['questions'],
                     'warm_samples':len(warm),'warm_median_ms':statistics.median(warm),
                     'warm_p95_ms':percentile(warm,.95),'warm_population_std_ms':statistics.pstdev(warm),
                     'warm_queries_per_second':run['warm_queries_per_second'],
                     'peak_process_rss_mib':run['process_resources']['peak_sampled_rss_mib'],
                     'mean_cpu_percent_one_core':run['process_resources']['mean_cpu_percent_one_core'],
                     'peak_cuda_allocated_mib':run['runtime']['cuda_peak_allocated_mib'],
                     'peak_cuda_reserved_mib':run['runtime']['cuda_peak_reserved_mib'],
                     'worker_total_wall_seconds':run['worker_total_wall_seconds'],
                     'model_load_seconds':run['runtime']['model_load_seconds'],
                     'device_gpu_observations':run['device_gpu_observations']})
    samples=coach['samples'];times=[s['total_seconds'] for s in samples]
    llm_wall=sum(c.get('seconds',0) for s in samples for c in s['llm_calls'])
    missing_named_record=bool(re.search(r"could(?:n't| not|n’t) find|not found|unable to find",samples[1]['answer'],re.I))
    local={'request_count':len(samples),'request_median_seconds':statistics.median(times),
           'request_mean_seconds':statistics.mean(times),'request_min_seconds':min(times),'request_max_seconds':max(times),
           'peak_process_rss_mib':max(s['process_resources']['peak_sampled_rss_mib'] for s in samples),
           'mean_cpu_percent_one_core_range':[min(s['process_resources']['mean_cpu_percent_one_core'] for s in samples),max(s['process_resources']['mean_cpu_percent_one_core'] for s in samples)],
           'llm_call_count':sum(len(s['llm_calls']) for s in samples),'llm_wall_fraction':llm_wall/sum(times),
           'observed_token_usage':{key:sum((c.get('usage') or {}).get(key,0) for s in samples for c in s['llm_calls']) for key in ['input_tokens','output_tokens','total_tokens']},
           'first_embedding_call_seconds':coach['embedding_cold']['wall_seconds'],
           'warm_embedding_median_seconds':coach['embedding_warm_median_seconds'],
           'native_model_stream_probe':{k:v for k,v in coach['native_cloud_stream_probe'].items() if k!='answer'},
           'per_request':[{'id':s['id'],'seconds':s['total_seconds'],'llm_calls':len(s['llm_calls']),
                           'embedding_seconds':sum(s['embedding_seconds']),'qdrant_seconds':sum(s['qdrant_seconds'])} for s in samples],
           'quality_observation':('Named-record question #2 missed a known indexed program. ' if missing_named_record else '')+'Timing completion is not a correctness pass; no output-quality improvement is claimed.'}
    report={'date':'2026-10-23','hardware':embed.get('hardware',{}),'scope':'Embedding worker CPU/GPU comparison and separate published CPU-image Coach measurements.',
            'embedding_runs':rows,'embedding_vector_agreement':embed['vector_agreement'],'cpu_image_coach':local,
            'image':coach['image'],'benchmark_code_sha256':coach['benchmark_code_sha256'],
            'limitations':['20 unique development questions repeated three times; warm statistics exclude the first batch.',
                           'Batch-4 timing is batch time divided by four, not single-request interactive latency; n=14 warm batches versus n=59 single-query samples.',
                           'Process RSS is not whole-system RAM. CUDA allocations are PyTorch measurements; nvidia-smi observations cover the whole GPU.',
                           'CPU percent uses one fully occupied logical core as 100%; values may exceed 100%. Twelve logical CPUs were visible.',
                           'Five Coach requests are a small operational sample, with embeddings prewarmed and compiled graph reused.',
                           'Cloud CPU/RAM/VRAM is unavailable; STT/TTS are disabled and were not benchmarked in this CPU image.',
                           'Native model first-content time uses no agents/tools and think=false; the current UI buffers completed jobs.',
                           'No pricing/billing data was available; token usage is reported instead of invented monetary cost.']}
    folder=ROOT/'docs/performance';folder.mkdir(exist_ok=True)
    (folder/'measurements.json').write_text(json.dumps(report,indent=2)+'\n')
    # Two panels retain their own explicit units; memory uses MiB throughout.
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="470" viewBox="0 0 1000 470" role="img"><title>Measured BGE CPU/GPU warm latency and peak process RAM</title><rect width="1000" height="470" rx="16" fill="#f8fafc"/><g font-family="Arial,sans-serif" fill="#0f172a"><text x="30" y="38" font-size="23" font-weight="bold">BGE embeddings · measured CPU vs GPU</text><text x="30" y="65" font-size="13">20 questions × 3 passes · FP32 · same model/queries · warm medians</text>']
    colors=['#64748b','#2563eb','#10b981']
    for panel,(key,title,unit) in enumerate([('warm_median_ms','Warm encoding time','ms/query'),('peak_process_rss_mib','Peak embedding-process RAM','MiB')]):
        left=30+panel*490;svg.append(f'<text x="{left}" y="105" font-size="17" font-weight="bold">{title}</text>')
        maximum=max(r[key] for r in rows)
        for i,row in enumerate(rows):
            y=145+i*75;width=row[key]/maximum*290
            svg.append(f'<text x="{left}" y="{y}" font-size="14">{html.escape(row["label"])}</text><rect x="{left}" y="{y+10}" width="{width:.1f}" height="24" rx="5" fill="{colors[i]}"/><text x="{left+width+8:.1f}" y="{y+28}" font-size="14">{row[key]:.1f} {unit}</text>')
    svg.append('<text x="30" y="405" font-size="13">GPU batch 4: amortized time per query; improves throughput, not a promise of individual response latency.</text><text x="30" y="430" font-size="13">This chart measures embeddings, not the cloud LLM, speech models, vector database or complete application.</text><text x="30" y="452" font-size="13">GPU speedup does not imply the same speedup for end-to-end Coach requests.</text></g></svg>')
    (folder/'cpu-gpu-comparison.svg').write_text(''.join(svg)+'\n')
    lines=['# Latency, resources and measured optimizations','',
           'Measured on 23 October 2026. The main LLM uses Ollama Cloud. Local model workloads are embeddings and optional STT/TTS; the published CPU image disables speech. Streamlit, Qdrant and SQLite still use local resources. This keeps local model requirements lighter than hosting the main LLM, without assuming whole-application usage is negligible.','',
           '![CPU/GPU embedding comparison](performance/cpu-gpu-comparison.svg)','',
           f'Hardware: **{embed.get("hardware",{}).get("cpu","see machine-readable report")}**, **{embed.get("hardware",{}).get("gpu","NVIDIA GPU")}**; {hardware.get("logical_cpus","unknown")} logical CPUs visible. GPU capacity {hardware.get("gpu_memory_mib",0):,.0f} MiB, driver {hardware.get("driver","unknown")}; Linux/WSL memory limit about {hardware.get("linux_memory_limit_mib",0)/1024:.2f} GiB. CPU embedding runs use two OpenMP threads. These figures are specific to this hardware and workload.','',
           '## Embedding comparison','',
           'The same 20 development questions were encoded three times per configuration (60 encodings each), using the same frozen BGE weights, CLS pooling, normalization and FP32. CPU uses two OpenMP threads. First batches are excluded from warm statistics.','',
           '| Configuration | Warm median | Warm p95 | Standard deviation | Peak process RAM | Peak CUDA allocation | Warm throughput |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        vram=f'{r["peak_cuda_allocated_mib"]:.1f} MiB' if r['peak_cuda_allocated_mib'] is not None else 'Not used'
        lines.append(f'| {r["label"]} | {r["warm_median_ms"]:.2f} ms | {r["warm_p95_ms"]:.2f} ms | {r["warm_population_std_ms"]:.2f} ms | {r["peak_process_rss_mib"]:.1f} MiB | {vram} | {r["warm_queries_per_second"]:.2f}/s |')
    speedup=rows[0]['warm_median_ms']/rows[1]['warm_median_ms'];batch_gain=rows[2]['warm_queries_per_second']/rows[1]['warm_queries_per_second']
    lines+=['',f'GPU single-query median encoding was **{speedup:.2f}× faster** than CPU in this run. GPU batching increased measured warm throughput by **{batch_gain:.2f}×** over GPU batch 1. Batch-4 values are amortized batch times, with 14 warm batches; single-query configurations have 59 warm samples. Queue waiting is not included, so batching is not automatically better for interactive single-user latency.',
            '',f'CPU/GPU minimum vector cosine agreement was {embed["vector_agreement"]["cpu_vs_gpu_min_cosine"]:.12f}; GPU single/batch agreement was {embed["vector_agreement"]["gpu_single_vs_batch_min_cosine"]:.12f}. This checks numerical agreement, not complete application answer quality.',
            '', f'Peak GPU allocation was {max(r["peak_cuda_allocated_mib"] or 0 for r in rows)/1024:.2f} GiB. Whole-device NVIDIA monitoring peaked at {rows[1]["device_gpu_observations"]["peak_device_gpu_utilization_percent"]}% utilization for batch 1 and {rows[2]["device_gpu_observations"]["peak_device_gpu_utilization_percent"]}% for batch 4; those observations include startup and other device users, so they are not per-request or per-process utilization. Process CPU averaged '+', '.join(f'{r["mean_cpu_percent_one_core"]:.2f}%' for r in rows)+f' of one core respectively; 100% means one occupied core, not all {hardware.get("logical_cpus","available")} visible logical CPUs.',
            '', '## Actual published CPU-image requests','',
            f'Five read-only synthetic requests used the actual compiled Coach graph, existing indexed corpus, bundled CPU embeddings and Gemma 4 31B through Ollama Cloud. A disposable account/database was used; no real user state was opened. Requests completed in **{min(times):.2f}–{max(times):.2f} seconds**, with median **{statistics.median(times):.2f} seconds** and mean **{statistics.mean(times):.2f} seconds**. Embeddings were prewarmed and the compiled graph was reused.',
            '', '| Sample | Backend completion | LLM calls | Embedding time | Qdrant time |','|---|---:|---:|---:|---:|']
    for r in local['per_request']:lines.append(f'| {r["id"]} | {r["seconds"]:.2f} s | {r["llm_calls"]} | {r["embedding_seconds"]:.3f} s | {r["qdrant_seconds"]:.3f} s |')
    lines+=['',f'Peak sampled Coach-process RAM was **{local["peak_process_rss_mib"]:.1f} MiB ({local["peak_process_rss_mib"]/1024:.2f} GiB)**. Per-request CPU averaged **{local["mean_cpu_percent_one_core_range"][0]:.2f}–{local["mean_cpu_percent_one_core_range"][1]:.2f}% of one logical core**; cloud/network wait is included in elapsed time. This CPU image uses no CUDA. External Qdrant, OS/browser resources and provider-side inference resources are excluded from these process numbers.',
            '', '**Output-quality observation:** '+local['quality_observation']+' These five operational requests do not replace the separately scoped 100-case direct-RAG quality evaluation.',
            '', '## Optimization findings','',
            f'- **Model residency:** the first CPU embedding call, including imports/model loading/inference, took {local["first_embedding_call_seconds"]:.2f} s; five subsequent calls had median {1000*local["warm_embedding_median_seconds"]:.2f} ms. The existing application model cache avoids repeating cold initialization.',
            '- **GPU acceleration and batching:** the worker comparisons above verify lower embedding latency and higher batch throughput. The portable public image remains CPU-based; these GPU figures do not describe that image.',
            f'- **Main bottleneck:** recorded cloud LLM calls summed to about {100*local["llm_wall_fraction"]:.1f}% of the five backend request durations, including network/service wait. Speeding up embeddings alone will not produce a 14× whole-application speedup.',
            f'- **Visible latency:** a separate native model stream produced first content in {local["native_model_stream_probe"]["time_to_first_content_seconds"]:.3f} s and completed in {local["native_model_stream_probe"]["total_seconds"]:.3f} s. It has no agent/tool steps and uses think=false. The current UI buffers the background job, so this is **not** the app’s user-visible TTFT. Browser rendering/polling adds delay beyond measured backend availability.',
            '- **Next useful targets:** fewer unnecessary model/tool round trips and safely streamed user-facing text offer larger potential gains. They require separate implementation and behavioral validation; this report does not claim they are deployed.',
            '',f'Across these five requests, observed API usage was {local["observed_token_usage"]["input_tokens"]:,} input and {local["observed_token_usage"]["output_tokens"]:,} output tokens across {local["llm_call_count"]} calls. Billing/pricing was unavailable; no monetary cost is invented.',
            '', '## Reproduce','', 'Use the pinned project development environment for orchestration and a CUDA-enabled embedding interpreter/model for GPU measurements:','',
            '```bash','python -m scripts.performance.benchmark_embeddings \\','  --embedding-python /path/to/gpu-venv/bin/python \\','  --model /path/to/pinned-bge-model \\','  --output .release-local/performance/embeddings-repeated',
            'python -m scripts.performance.run_container_benchmark \\','  --cloud-env /path/to/private.env \\','  --qdrant-url http://host.docker.internal:6333','python -m scripts.performance.build_report','```','',
            'The container benchmark uses the verified public image digest and an isolated `/tmp` account. It makes real provider calls. On native Linux, set a container-reachable Qdrant URL; localhost inside a container is not the host. The embedding benchmark is also recorded by the trusted CI evaluation job, with aggregate performance artifacts. No hard latency gate is imposed on shared-hardware timings.',
            '', '[Machine-readable aggregates](performance/measurements.json) · [Quality evaluation](EVALUATION_PROCESS.md)']
    (ROOT/'docs/PERFORMANCE.md').write_text('\n'.join(lines)+'\n')
    print('Saved performance report, comparison SVG and safe aggregate JSON.')


if __name__=='__main__':main()

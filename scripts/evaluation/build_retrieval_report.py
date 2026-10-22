"""Build a public aggregate report without redistributing corpus text or private traces."""
from __future__ import annotations
import json
from pathlib import Path
import statistics
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[2]
LOCAL=ROOT/'.evaluation-local'


def summarize(assessment,review):
    rows=assessment['rows']
    judgments=review['judgments']
    docs=[d for j in judgments.values() for d in j.get('documents',[])]
    durations=[r['seconds'] for r in rows if r['status']=='parsed']
    return {'scenarios':len(rows),'parsed_outputs':sum(r['status']=='parsed' for r in rows),
            'median_agent_seconds':statistics.median(durations),
            'total_search_calls':sum(r.get('search_calls',0) for r in rows),
            'nonempty_evidence_cases':sum(bool(r.get('documents')) for r in rows),
            'cases_with_provenance_issues':sum(bool(r.get('issues')) for r in rows),
            'llm_scored_cases':sum(j.get('score') is not None for j in judgments.values()),
            'llm_relevant_documents':sum(d['relevant'] for d in docs),
            'llm_rated_documents':len(docs),
            'unscored_cases':{key:j['status'] for key,j in judgments.items() if j.get('score') is None},
            'judge_model':review['judge_model'],'experiment_url':review['url'],
            'per_case':[{'id':r['id'],'seconds':r.get('seconds'),'search_calls':r.get('search_calls'),
                         'returned_documents':r.get('returned_documents'),'provenance_issue_count':len(r.get('issues',[])),
                         'llm_relevance':judgments.get(r['id'],{}).get('score'),
                         'judge_status':judgments.get(r['id'],{}).get('status')} for r in rows]}


def main():
    def read(name):return json.loads((LOCAL/name).read_text())
    baseline=summarize(read('agentic-assessment.json'),read('agentic-langsmith-review-v2.json'))
    optimized=summarize(read('agentic-assessment-optimized.json'),read('agentic-langsmith-review-optimized.json'))
    direct=read('direct-development/results.json')
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'split':'development',
            'dataset_scenarios':100,'development_scenarios':30,'held_out_scenarios':70,
            'scope':'Retriever component pilot; no end-to-end Coach/Designer, memory or speech quality claim.',
            'corpus_counts':{key:value['count'] for key,value in direct['corpus_manifest']['collections'].items()},
            'embedding_model':direct.get('embedding_model'),'embedding_runtime':direct['embedding_runtime'],
            'baseline':baseline,'revised':optimized,
            'mistral_comparison':{'status':'not_run','reason':'Ollama Cloud returned HTTP 402: model not included in current free usage. No billing changes made.'},
            'limitations':['One generation per case on sixteen selected development retrieval scenarios. No independent holdout or statistical significance claim.',
                           'Different search counts and selected evidence counts; relevance means cannot be treated as equal-budget accuracy comparisons.',
                           'Empty evidence and judge parsing errors are unscored, not successes. Revised retriever falsely abstained on retrieval-20.',
                           'Both reviews use gpt-oss:120b and the same retrieval-v2-fields recipe; these are uncalibrated model ratings, not human ground truth.',
                           'Timing includes cloud calls and local GPU RPC overhead; provider/network variability remains. No repeated latency benchmark.',
                           'GPU embedding measurements are for a separate batched direct-query run, not per-agent-case VRAM peaks.',
                           'Original index embedding revision was not recorded; downloaded query encoder is pinned, but historical index revision is unknown.',
                           'Trace links require access to the private LangSmith workspace. No raw corpus text is included in this report.']}
    followup_path=LOCAL/'statistics-fix-assessment.json'
    followup=json.loads(followup_path.read_text()) if followup_path.exists() else None
    if followup:
        row=followup['rows'][0]
        report['statistics_followup']={key:row[key] for key in ['id','status','returned_documents','search_calls','seconds']}
        report['statistics_followup']['provenance_issue_count']=len(row['issues'])
        report['statistics_followup']['scope']='One targeted rerun after a further prompt change; not included in the 16-case revised timings.'
    output=ROOT/'evaluation/results/retrieval-development-pilot.json'
    output.write_text(json.dumps(report,indent=2)+'\n')
    summary=f'''# Retrieval development pilot

Recorded 22–23 October 2026. This evaluates the Retriever component on **16 development scenarios**, not the entire app or all 100 scenarios.

| Measurement | Original retriever | Revised retriever |
|---|---:|---:|
| Parsed JSON outputs | {baseline['parsed_outputs']}/16 | {optimized['parsed_outputs']}/16 |
| Median agent duration | {baseline['median_agent_seconds']:.2f} s | {optimized['median_agent_seconds']:.2f} s |
| Search calls across 16 cases | {baseline['total_search_calls']} | {optimized['total_search_calls']} |
| Cases returning evidence | {baseline['nonempty_evidence_cases']}/16 | {optimized['nonempty_evidence_cases']}/16 |
| Detected evidence provenance issues | {baseline['cases_with_provenance_issues']} | {optimized['cases_with_provenance_issues']} |
| Cases receiving a valid LLM rating | {baseline['llm_scored_cases']}/16 | {optimized['llm_scored_cases']}/16 |
| Documents the judge rated relevant | {baseline['llm_relevant_documents']}/{baseline['llm_rated_documents']} rated | {optimized['llm_relevant_documents']}/{optimized['llm_rated_documents']} rated |

**Do not interpret the last row as whole-project accuracy or a directly comparable improvement percentage.** The revised outputs contain fewer documents, three cases returned no evidence, and one additional case failed judge validation. Empty/error cases are not counted as perfect results.

![Measured retrieval execution comparison](results/retrieval-execution.svg)

## What changed

The original prompt contained placeholder allowed-value lists, instructed searches of both collections on every request, relaxed filters after empty results, and forced selection even when retrieved evidence was unrelated. The revised prompt supplies the actual categories, chooses collections by task, preserves explicit constraints and allows abstention. Qdrant point IDs now survive into agent evidence; exercise display names are also preserved.

## What needs attention

- `retrieval-20`: the first revised retriever discarded usable exercise-statistic evidence. A further general statistics-evidence instruction fixed this in a targeted rerun: one source returned, one search, 4.23 s, no detected provenance issues. The 16-case revised timings above predate this follow-up; replay the matrix before a final release.
- `retrieval-13`: judge output failed strict ID validation. Its documents remain unscored; malformed model ratings must never become a score silently.
- Judge interpretation of Beginner versus Novice and numerical metadata inconsistencies needs human calibration. A judge disagreement is not automatically an application failure.
- The unknown-title case and the advanced ten-minute case returned empty revised outputs; whether abstention is correct must be checked against the frozen corpus and user constraints, not inferred merely from an empty response.

## Execution and resources

Local Qdrant contained 2,594 program and 3,213 exercise records. The pinned query encoder was BAAI/bge-large-en-v1.5, revision `{direct.get('embedding_model',{}).get('revision','unknown')}`, using CUDA on the GTX 1660 Ti. The cloud retrieval model was Gemma 4 31B; the judge was gpt-oss:120b through Ollama Cloud.

The separate direct-query embedding run reported about {direct['embedding_runtime']['cuda_peak_allocated_mib']:.0f} MiB peak allocated CUDA memory and {direct['embedding_runtime']['max_rss_mib']:.0f} MiB process max RSS. Model loading and the first batch were cold; these are not per-agent-case resource measurements. Local batching times are not time to first user-visible answer.

LangSmith records datasets, traces and model judgments; Python runs the harness locally and Ollama Cloud runs the judge. Mistral Large 3 returned HTTP 402 because it is excluded from current free usage, so the requested two-judge comparison is unfinished. No credits were purchased and no price estimate was invented.

[Baseline review]({baseline['experiment_url']}) · [Revised review]({optimized['experiment_url']}) (workspace access required).

Raw corpus snapshots, full traces and judgments remain in ignored `.evaluation-local/`. [Aggregate machine-readable results](results/retrieval-development-pilot.json).

## Remaining evaluation work

Replay the full matrix after the targeted statistics fix, calibrate judge rubrics, review corpus-backed relevance references, implement isolated full-conversation fixtures, evaluate Coach/Designer and multi-turn memory on development cases, then freeze a candidate and run the 70 held-out scenarios without tuning on their outcomes. Full RAG correctness, groundedness of final answers, human-calibrated quality, complete resource profiling and a second-judge comparison are not complete.
'''
    (ROOT/'evaluation/RETRIEVAL_PILOT_RESULTS.md').write_text(summary)
    bars=[]
    for group,(label,left,right,max_value,unit) in enumerate([
        ('Median agent duration',baseline['median_agent_seconds'],optimized['median_agent_seconds'],9,' s'),
        ('Search calls across 16 cases',baseline['total_search_calls'],optimized['total_search_calls'],50,'')]):
        y=75+group*125
        bars.append(f'<text x="24" y="{y}" font-size="17" font-weight="600">{label}</text>')
        for offset,value,color,name in [(25,left,'#64748b','Original'),(58,right,'#2563eb','Revised')]:
            width=round(value/max_value*440)
            display=f'{value:.2f}' if unit else str(value)
            bars.append(f'<text x="24" y="{y+offset+17}" font-size="14">{name}</text><rect x="110" y="{y+offset}" width="{width}" height="24" rx="4" fill="{color}"/><text x="{120+width}" y="{y+offset+17}" font-size="14">{display}{unit}</text>')
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="700" height="350" viewBox="0 0 700 350" role="img"><title>Execution comparison on 16 development retrieval scenarios</title><rect width="700" height="350" fill="#f8fafc"/><g font-family="Arial,sans-serif" fill="#0f172a"><text x="24" y="32" font-size="21" font-weight="700">Retrieval execution: 16 development cases</text>'+''.join(bars)+'<text x="24" y="318" font-size="13">Single run per case; cloud/network variability remains.</text><text x="24" y="338" font-size="13">Speed is separate from relevance, coverage and final-answer correctness.</text></g></svg>'
    (ROOT/'evaluation/results/retrieval-execution.svg').write_text(svg+'\n')
    print('Wrote aggregate JSON, execution chart and documented limitations.')


if __name__=='__main__':main()

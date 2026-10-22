"""Create public aggregate results and a local full-evidence review page."""
from __future__ import annotations
import html
import json
from pathlib import Path
import statistics
from scripts.evaluation.build_corpus_golden import ROOT,LOCAL,PUBLIC,VERSION


def main():
    path=LOCAL/'golden/evaluation'
    summary=json.loads((path/'summary.json').read_text())
    rows={}
    for line in (path/'cases.jsonl').read_text().splitlines():
        row=json.loads(line);rows[row['id']]=row
    cases=[json.loads(line) for line in (LOCAL/f'golden/{VERSION}.jsonl').read_text().splitlines()]
    public={'dataset_version':VERSION,'cases':summary['cases'],'completed':summary['completed'],
            'normalized_ranking_score_100':summary['normalized_ranking_score_100'],
            'metrics':summary['metrics'],'experiment_url':summary['experiment_url'],
            'scope':summary['scope'],'limitations':summary['limitations'],
            'answer_model':summary['configuration']['answer_model'],'judge_model':summary['configuration']['judge_model'],
            'dataset_sha256':summary['configuration']['dataset_sha256'],
            'prompt_hashes':summary['configuration']['prompt_hashes'],
            'generation_median_seconds':statistics.median(r['generation']['wall_seconds'] for r in rows.values() if r.get('generation')),
            'provider_usage':{phase:{key:sum((r.get(phase,{}).get('usage',{}).get(key) or 0) for r in rows.values()) for key in ['prompt_eval_count','eval_count']} for phase in ['generation','correctness','faithfulness']},
            'per_case':[{'id':c['id'],'category':c['category'],'split':c['split'],
                         'status':rows.get(c['id'],{}).get('status','missing'),
                         'scores':rows.get(c['id'],{}).get('scores',{}),
                         'answer_generation_seconds':rows.get(c['id'],{}).get('generation',{}).get('wall_seconds')} for c in cases]}
    out=ROOT/'evaluation/results';out.mkdir(exist_ok=True)
    (out/'corpus-golden-baseline.json').write_text(json.dumps(public,indent=2)+'\n')
    labels={'ndcg_at_5':'Ranking nDCG@5','recall_at_5':'Retrieval recall@5','correctness_f1':'Required-fact correctness F1',
            'faithfulness':'Faithfulness to retrieved evidence','answer_relevance':'Answer relevance','completeness':'Reference-fact completeness'}
    bars=[]
    for i,(key,label) in enumerate(labels.items()):
        metric=summary['metrics'][key];value=metric['mean'];y=70+i*55
        width=(value or 0)*390
        text=f'{100*value:.1f}%' if value is not None else 'unscored'
        bars.append(f'<text x="22" y="{y}" font-size="14">{label}</text><rect x="22" y="{y+8}" width="390" height="18" rx="3" fill="#e2e8f0"/><rect x="22" y="{y+8}" width="{width:.1f}" height="18" rx="3" fill="#2563eb"/><text x="430" y="{y+23}" font-size="14">{text} ({metric["scored_cases"]}/100)</text>')
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="680" height="445" role="img"><title>Corpus-derived QA baseline: separate ranking and answer metrics</title><rect width="680" height="445" fill="#f8fafc"/><g font-family="Arial,sans-serif" fill="#0f172a"><text x="22" y="30" font-size="20" font-weight="bold">100 corpus-derived QA cases — direct RAG baseline</text>'+''.join(bars)+'<text x="22" y="421" font-size="12">Model-judged answer quality; source-relative facts, not expert fitness validation.</text><text x="22" y="439" font-size="12">Parentheses show valid score counts; missing judgments remain unscored.</text></g></svg>'
    (out/'corpus-golden-baseline.svg').write_text(svg+'\n')
    lines=['# Corpus-derived golden QA baseline','',
           'The corpus was inspected before sampling. A fixed seed selected 100 questions with 120 distinct authoritative source records: 50 program lookups, 30 exercise lookups, 10 program comparisons and 10 program/exercise joins. Every question has source chunks, graded qrels, structured reference facts and a reference answer before retrieval runs.',
           '', 'These are mechanically source-validated, synthetic reference questions. They assess recorded corpus facts; they are not independently human-adjudicated fitness truth or a whole-app quality certification.',
           '', '![Separate retrieval and answer metrics](results/corpus-golden-baseline.svg)',
           '', '| Metric | Mean | Valid scores |','|---|---:|---:|']
    for key,metric in summary['metrics'].items():
        value=f'{metric["mean"]:.4f}' if metric['mean'] is not None else 'unscored'
        lines.append(f'| {key} | {value} | {metric["scored_cases"]}/{metric["total_cases"]} |')
    lines+=['',f'Normalized ranking score: **{summary["normalized_ranking_score_100"]:.2f}/100**, calculated as 100 × mean nDCG@5 across all 100 questions.',
            '', 'Precision@5 has a ceiling of 0.2 for a question with one authoritative reference source and 0.4 for two sources. It should not be compared with open-ended semantic precision without that context.',
            '', 'nDCG compares discounted graded relevance with the ideal relevance order. Equally necessary sources have equal grades and either ordering is ideal. The qrels define authoritative-record identity for named factual questions; this is not exhaustive semantic relevance labeling of the whole corpus.',
            '', '## Answer scoring and framework',
            '', 'LangSmith hosts the frozen dataset and experiment. Python runs the harness locally, BGE embeddings use the local GPU, and Ollama Cloud runs Gemma answers and GPT-OSS judges. These are custom LangSmith evaluators; they are not scores produced by installing or running Ragas.',
            '', '- Correctness judge: question + reference answer/facts + generated answer. Required facts are marked correct, incorrect or missing; precision, recall/completeness and F1 are calculated in code.',
            '- Faithfulness judge: question + actual retrieved chunks + generated answer. It never receives the reference answer. Its score is supported factual claims divided by all factual claims; no-claim responses remain unscored.',
            '- Relevance: a separate 0–4 rubric normalized to 0–1. Completeness is reference facts correctly covered divided by all required facts.',
            '', 'Reference answers never enter generation prompts. Model-judged scores can be wrong and need calibration. No single overall answer score conceals the individual dimensions.',
            '', f'[LangSmith experiment]({summary["experiment_url"]}) (workspace access required). [Aggregate JSON](results/corpus-golden-baseline.json).',
            '', '## Scope and limitations','',
            'This is a **direct retrieval + LLM baseline**, not a run of the full Coach/Designer workflow, memory, approvals, speech or browser UI. Both Qdrant collections were searched for every question and cosine top-five results were merged without supplying gold routes or source IDs to retrieval. Each answer/judgment is one stochastic service observation despite temperature zero.',
            '', 'The 30/70 split uses disjoint source anchors. The full frozen 100-case set has now been evaluated once; do not tune on the 70 held-out outcomes and continue presenting them as untouched. No new retrieval/prompt tuning was done during this run.',
            '', 'Historical indexing revision is unknown. The corpus content hashes and query model revision are recorded. Source metadata may contain errors; the questions explicitly ask what the index records. API token usage is recorded; monetary cost is not invented.',
            '', 'Full contexts, actual answers, claim-level judge reasons and the review HTML remain in ignored `.evaluation-local/golden/`. Public files contain questions, generated reference answers/facts, source hashes/IDs and aggregate/per-case scores, without the raw corpus narratives.']
    (ROOT/'evaluation/GOLDEN_QA_RESULTS.md').write_text('\n'.join(lines)+'\n')
    cards=[]
    for c in cases:
        row=rows.get(c['id'],{})
        content={'question':c['question'],'reference_answer':c['reference_answer'],
                 'generated_answer':row.get('generation',{}).get('answer'),
                 'scores':row.get('scores'),
                 'reference_chunks':c['reference_chunks'],'reference_contexts':c['reference_contexts'],
                 'retrieved_contexts':row.get('retrieved_contexts'),
                 'correctness_judgment':row.get('correctness'),'faithfulness_judgment':row.get('faithfulness')}
        cards.append(f'<details><summary>{html.escape(c["id"]+" · "+c["category"]+" · "+str(row.get("status","missing")))}</summary><pre>{html.escape(json.dumps(content,indent=2,ensure_ascii=False))}</pre></details>')
    page='<!doctype html><html lang="en"><meta charset="utf-8"><title>Fitness golden QA evidence review</title><style>body{font:16px system-ui;max-width:1100px;margin:35px auto;padding:0 20px;background:#f8fafc;color:#0f172a}details{background:white;padding:16px;margin:12px 0;border:1px solid #cbd5e1;border-radius:8px}summary{cursor:pointer;font-weight:650}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}</style><h1>100 corpus-derived QA cases</h1><p>Reference evidence, actual retrieval, generated answers and independent judge dimensions. Source-relative synthetic benchmark; not independently human-adjudicated.</p>'+''.join(cards)+'</html>'
    (LOCAL/'golden/review.html').write_text(page)
    ragas=[{'user_input':c['question'],'reference':c['reference_answer'],
            'response':rows.get(c['id'],{}).get('generation',{}).get('answer',''),
            'retrieved_contexts':[json.dumps(d,ensure_ascii=False) for d in rows.get(c['id'],{}).get('retrieved_contexts',[])]} for c in cases]
    (LOCAL/'golden/ragas_samples.json').write_text(json.dumps(ragas,indent=2,ensure_ascii=False)+'\n')
    print('Saved public result report/chart, local evidence review HTML and Ragas-format samples.')


if __name__=='__main__':main()

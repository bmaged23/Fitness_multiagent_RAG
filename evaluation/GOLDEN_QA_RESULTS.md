# Corpus-derived golden QA baseline

The corpus was inspected before sampling. A fixed seed selected 100 questions with 120 distinct authoritative source records: 50 program lookups, 30 exercise lookups, 10 program comparisons and 10 program/exercise joins. Every question has source chunks, graded qrels, structured reference facts and a reference answer before retrieval runs.

These are mechanically source-validated, synthetic reference questions. They assess recorded corpus facts; they are not independently human-adjudicated fitness truth or a whole-app quality certification.

![Separate retrieval and answer metrics](results/corpus-golden-baseline.svg)

| Metric | Mean | Valid scores |
|---|---:|---:|
| ndcg_at_5 | 0.7179 | 100/100 |
| precision_at_5 | 0.1920 | 100/100 |
| recall_at_5 | 0.8200 | 100/100 |
| mrr_at_5 | 0.7095 | 100/100 |
| correctness_precision | 0.8433 | 100/100 |
| correctness_f1 | 0.8165 | 100/100 |
| completeness | 0.8020 | 100/100 |
| answer_relevance | 0.9075 | 100/100 |
| faithfulness | 0.9783 | 100/100 |
| unsupported_claim_rate | 0.0217 | 100/100 |

Normalized ranking score: **71.79/100**, calculated as 100 × mean nDCG@5 across all 100 questions.

Precision@5 has a ceiling of 0.2 for a question with one authoritative reference source and 0.4 for two sources. It should not be compared with open-ended semantic precision without that context.

nDCG compares discounted graded relevance with the ideal relevance order. Equally necessary sources have equal grades and either ordering is ideal. The qrels define authoritative-record identity for named factual questions; this is not exhaustive semantic relevance labeling of the whole corpus.

## Answer scoring and framework

LangSmith hosts the frozen dataset and experiment. Python runs the harness locally, BGE embeddings use the local GPU, and Ollama Cloud runs Gemma answers and GPT-OSS judges. These are custom LangSmith evaluators; they are not scores produced by installing or running Ragas.

- Correctness judge: question + reference answer/facts + generated answer. Required facts are marked correct, incorrect or missing; precision, recall/completeness and F1 are calculated in code.
- Faithfulness judge: question + actual retrieved chunks + generated answer. It never receives the reference answer. Its score is supported factual claims divided by all factual claims; no-claim responses remain unscored.
- Relevance: a separate 0–4 rubric normalized to 0–1. Completeness is reference facts correctly covered divided by all required facts.

Reference answers never enter generation prompts. Model-judged scores can be wrong and need calibration. No single overall answer score conceals the individual dimensions.

[LangSmith experiment](https://eu.smith.langchain.com/o/01cb8af4-5866-49ad-bca6-26844f87da18/projects/p/9164d45d-2506-483c-9272-ac2f1e73567a) (workspace access required). [Aggregate JSON](results/corpus-golden-baseline.json).

## Scope and limitations

This is a **direct retrieval + LLM baseline**, not a run of the full Coach/Designer workflow, memory, approvals, speech or browser UI. Both Qdrant collections were searched for every question and cosine top-five results were merged without supplying gold routes or source IDs to retrieval. Each answer/judgment is one stochastic service observation despite temperature zero.

The 30/70 split uses disjoint source anchors. The full frozen 100-case set has now been evaluated once; do not tune on the 70 held-out outcomes and continue presenting them as untouched. No new retrieval/prompt tuning was done during this run.

Historical indexing revision is unknown. The corpus content hashes and query model revision are recorded. Source metadata may contain errors; the questions explicitly ask what the index records. API token usage is recorded; monetary cost is not invented.

Full contexts, actual answers, claim-level judge reasons and the review HTML remain in ignored `.evaluation-local/golden/`. Public files contain questions, generated reference answers/facts, source hashes/IDs and aggregate/per-case scores, without the raw corpus narratives.

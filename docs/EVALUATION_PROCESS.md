# How we evaluated the RAG pipeline

We evaluated **100 corpus-derived questions** with fixed reference evidence and answers. This benchmark measures direct retrieval and answer generation. Offline tests separately check application behavior; the benchmark does not run the entire Coach/Designer, memory or speech workflow.

## 1. Inspect the corpus and freeze the reference dataset

We inspected the existing index containing **2,594 program records and 3,213 exercise records**, then used a fixed random seed to select 100 source-first questions:

| Question type | Cases |
|---|---:|
| Program facts | 50 |
| Exercise facts | 30 |
| Program comparisons | 10 |
| Program/exercise joins | 10 |

The questions use 120 distinct source records. Before running retrieval, every question received reference chunk IDs, source hashes, required facts and a reference answer derived from the recorded data. Similarity search did not define the ground truth. The source-relative facts were mechanically validated; there was no independent human adjudication or scientific fitness-truth certification.

Dataset and corpus hashes identify the frozen inputs. The original split was 30 development and 70 held-out questions with disjoint source anchors. All 100 have now been evaluated and reused for regression checking, so they are no longer an untouched final test set.

## 2. Retrieve evidence without showing the references

For each question, the pinned **BGE-large-en-v1.5** encoder creates a normalized embedding on the local GPU. The baseline searches both Qdrant collections, requests five candidates from each and merges them into a global cosine-ranked top five. It receives the question, without gold chunk IDs, reference answers or gold collection routes.

Actual retrieved payloads are checked against the frozen corpus. We compare the retrieved IDs/ranks with the reference chunks using:

- **Recall@5:** fraction of required source records retrieved.
- **nDCG@5:** graded relevance discounted by rank, normalized against the ideal ranking. Equally necessary sources have equal grades; either order is ideal.
- **MRR@5:** reciprocal rank of the first relevant result, or zero if none appears.
- **Precision@5:** relevant reference records divided by five. For these named-record questions, its ceiling is 0.2 for one required source and 0.4 for two; it is not an open-ended semantic relevance score.

The displayed ranking score out of 100 is `100 × mean nDCG@5`. Retrieval metrics are calculated in Python, without an LLM judge.

## 3. Generate a fresh answer

**Gemma 4 31B on Ollama Cloud** receives only the question and the actual retrieved contexts. It is asked to report recorded facts accurately, cite evidence and admit missing information. It never receives the reference answer or required reference facts.

## 4. Judge correctness and relevance

A separate **GPT-OSS 120B call on Ollama Cloud** receives the question, generated answer, reference answer and required reference facts. Every required fact is marked correct, incorrect or missing.

Python calculates:

- **Correctness precision:** correct facts / (correct + incorrect facts).
- **Completeness:** correct facts / all required facts.
- **Correctness F1:** harmonic mean of correctness precision and completeness.
- **Answer relevance:** a separate 0–4 judge rubric, normalized to 0–1.

These are custom required-fact scores. They are not native Ragas AnswerCorrectness scores and do not independently establish real-world scientific truth.

## 5. Judge faithfulness using the actual evidence

Another independent GPT-OSS 120B call receives the question, generated answer and **actual retrieved contexts**. It does not receive reference answers or gold facts.

The judge decomposes the answer into factual claims and checks whether the retrieved evidence supports each claim. Python validates cited source IDs and calculates:

- **Faithfulness:** supported claims / all evaluated factual claims.
- **Unsupported-claim rate:** `1 − faithfulness`.

An answer with no factual claims remains unscored, rather than receiving an automatic perfect score. A grounded answer can still be incomplete; a plausible answer can still lack support. That is why correctness, completeness and faithfulness remain separate.

## 6. Validate, save and compare

Python validates judge schemas and fact/source IDs. Invalid judgments or transient service failures allow up to three attempts, with available usage and attempts recorded. A valid low score is never retried to obtain a better result. Persistent failures remain unscored.

LangSmith stores the dataset, experiment traces, outputs and individual feedback scores. Python orchestrates the evaluation; Ollama Cloud runs the answer and judge models. These are custom LangSmith evaluators, not an installed/executed Ragas evaluation. Raw local contexts and detailed evidence remain outside Git; public CI artifacts contain aggregate summaries.

We average each metric separately and report its valid denominator. There is no combined score hiding the individual dimensions. LLM judgments can be wrong and still require human calibration.

## 7. Use the results as a CI/CD gate

Trusted application-code pushes repeat all 100 retrievals, generate 100 fresh answers and obtain 200 valid judge assessments. Publication requires 100 completed cases and 100 valid scores for each gated metric. A metric may regress by at most **0.03 absolute** against the original frozen baseline; unsupported-claim rate uses the opposite direction because lower is better. This is an operational tolerance, not a statistical significance test.

After passing, CI builds and tests the image, publishes it to Docker Hub, pulls it and repeats the container tests. Documentation-only pushes run offline CI without repeating the live benchmark. The laptop GPU runner, model and Qdrant must be online; the image publication job runs on GitHub-hosted infrastructure.

## Results

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

[Original report](../evaluation/GOLDEN_QA_RESULTS.md) · [CI results JSON](release-evaluation-summary.json) · [Successful release workflow](https://github.com/bmaged23/Fitness_multiagent_RAG/actions/runs/39876219203) · [CI/CD setup](CI_CD.md)


## Latest automatic release check

[Run 39881688307](https://github.com/bmaged23/Fitness_multiagent_RAG/actions/runs/39881688307) passed all 100 cases and the release gate: correctness F1 81.50%, completeness 80.20%, relevance 90.00%, faithfulness 99.00%, unsupported claims 1.00%; retrieval nDCG@5 0.7179 and recall@5 82.00%. This is a subsequent run, separate from the frozen baseline. [Aggregate evidence](https://github.com/bmaged23/Fitness_multiagent_RAG/blob/master/docs/performance/release-evaluation-7d09f5c.json). The quality evaluation runs from source on the local GPU; the built Docker image receives container smoke checks before publication and after pulling it back.

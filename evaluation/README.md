# Evaluation

## Completed primary benchmark: 100 corpus-derived questions

Use [GOLDEN_QA_RESULTS.md](GOLDEN_QA_RESULTS.md) for the completed 100-case retrieval and answer evaluation. Every case has reference source IDs, structured facts and a reference answer selected before retrieval. Public references are in `datasets/fitness-corpus-qa-v1.references.jsonl`; the manifest freezes dataset and corpus hashes. Full source contexts remain private under `.evaluation-local/`.

The release pipeline reruns all 100 questions, generates fresh answers and makes two independent judge calls per answer. It requires 100 valid scores for each gated metric. The [release policy](release-gate.json) allows at most 0.03 absolute regression from the recorded baseline. These are operational regression limits, not statistical significance tests or new blind benchmark claims. See [CI/CD setup](../docs/CI_CD.md).

The following older scenarios and pilot reports are separate development/regression work; their pending behavior checks do not mean the primary corpus QA run is incomplete.

---

# Fitness RAG evaluation

## Current status

100 distinct authored scenarios, containing 127 user messages and 20 multi-turn conversations. There are 30 development and 70 held-out scenarios. These are **draft evaluation inputs and rubrics, not 100 successful application runs or a validated benchmark**.

The existing local Qdrant corpus has now been snapshotted read-only: 2,594 program and 3,213 exercise records. The source CSVs are still absent from this checkout. 51 cases require corpus evidence review; 49 require behavior review. No human-reviewed relevance labels or final-answer correctness scores have been established. Dataset provenance is synthetic authoring informed by the repository schema; these are not real user conversations.

| Category | Scenarios |
|---|---:|
| Workout/program/exercise retrieval | 25 |
| Equipment, level, duration and schedule constraints | 20 |
| Multi-turn memory and corrections | 20 |
| Agent routing and tool use | 15 |
| Missing evidence, ambiguity and adversarial instructions | 10 |
| Plan validation, approval and export | 10 |

See [retrieval pilot results](RETRIEVAL_PILOT_RESULTS.md) for real development runs, measured timings, model-judge ratings and their limitations. Only the Retriever component has been exercised so far; the whole 100-case suite is not complete.

## Files and validation

- `datasets/fitness_scenarios.v1.jsonl`: one scenario per line, explicit user turns, starting state, expected behavior, checks and reference status.
- `datasets/manifest.json`: dataset version, split sizes, content hash and pending review status.
- `scripts/evaluation/validate_dataset.py`: schema/count/duplicate/split/hash validation.
- `scripts/evaluation/retrieval_metrics.py`: reference-based Precision@k, Recall@k and MRR@k.
- `scripts/evaluation/export_langsmith.py`: local export or explicitly requested LangSmith upload.

From the project root, with the development dependencies installed:

```bash
.venv/bin/python -m scripts.evaluation.validate_dataset
.venv/bin/python -m pytest -q
.venv/bin/python -m scripts.evaluation.export_langsmith \
  --split development --output /tmp/fitness-development-examples.json
```

The default export performs no cloud calls. All dataset examples are synthetic, but do not attach real personal database state or credentials to their exports.

## Reference review before scoring

1. Provision the actual licensed source corpus and embedding model; snapshot corpus/chunk hashes, model revision, collection configuration and application commit.
2. Inspect each development case's retrieved candidates, including candidates pooled from direct and agentic retrieval. A reviewer marks `(collection, chunk_id, relevant)` entries, records supporting source facts and any acceptable alternatives. Do not use embedding similarity as ground truth. Precision scores are conservative if the judged candidate pool is incomplete; recall is relative to the annotated positives, not all possible relevant corpus documents.
3. Check unsupported-name cases against the frozen corpus before asserting absence. For no-match cases, score correct abstention and fabrication separately rather than assigning perfect recall to an empty reference set.
4. Replace placeholder starting-state fixture names with implemented, reproducible synthetic profiles/plans/drafts. For every scenario, create isolated state; within a multi-turn scenario, retain the same session and interleave the app's actual assistant responses between user messages. Do not concatenate all user turns into a single prompt. Restart/multi-user isolation need additional explicit runner steps before claiming coverage.
5. Implement fault injection for Qdrant/save failures. Validate actual state changes, exported PDF and tool results, not just the assistant's claim that an action succeeded.
6. Add reviewer identity/date, set `reference_status` to `reviewed` only after review, version the dataset and update its manifest hash. Keep behavior references separate from answer text: multiple correct answers are allowed.

Use development cases for tuning. Do not tune on held-out cases or their scores. Current splits are scenario-level and include related themes across splits, so they do not establish independent task-family generalization. If tuning exposes held-out outcomes, build a new untouched final set. Repeat runs to characterize model variability and report per-category results and uncertainty, not just one aggregate score.

## Scoring plan

| Layer | Scoring method |
|---|---|
| Direct retrieval | Precision@3, Recall@3, MRR@3 against reviewed positive references; equipment/level constraint violations |
| Agentic retrieval | Same per-query-budget metrics plus evidence coverage across all unique documents; track rewrite/retry count and total retrieved tokens |
| Final answer | Human-calibrated judge rubrics for groundedness, relevance and correctness against reviewed source facts |
| Tools and state | Deterministic checks for routing outcomes, tool results, plan validity, explicit approval, saved state and PDF content |
| Memory | Latest fact/correction retained across turns; no fabricated personal facts |
| Operations | Retrieval time, time to first visible answer, total duration, failures, provider tokens and actual cost where available |

The current retriever caps each search at three results and can make multiple searches. Do not compare the agent's union of many searches to a direct top-3 result without reporting the different budgets. Record both equal-budget and actual-cost comparisons. For timing, distinguish tool activity from first user-visible answer text, and separate cold model loading from warm requests.

The scorer deduplicates credit while retaining duplicate rank positions. Missing references return `None`, not 0 or 1. It does not yet compute agent evidence coverage, grade final answers or run the application.

## Judge rubric

- **Correctness:** does the answer satisfy reviewed source facts and required user constraints? Identify unsupported or contradictory claims.
- **Groundedness:** are corpus-attributed claims supported by the actual retrieved text? Distinguish generated coaching suggestions from source statements.
- **Relevance:** does the answer address the current task without substituting nutrition/workout topics or unrelated personal facts?
- **Appropriate uncertainty:** does it acknowledge missing evidence and tool failures, ask necessary clarification, and avoid fabricated guarantees/citations?

Use per-rubric pass/fail with reasons and cited evidence; use `unscored` when evidence is insufficient. Calibrate the judge against human-reviewed examples, ideally use a different judge from the answering model, and manually inspect disagreements. These scores cannot certify exercise or medical safety.

## LangSmith

The installed core dependency graph includes LangSmith. The exporter uses its `Client.create_dataset` and `Client.create_examples` APIs. Configure `LANGSMITH_API_KEY` through your environment, never in dataset files. Optional tracing is separate from dataset upload and must be enabled deliberately; do not enable tracing of personal sessions globally for this exercise.

For draft annotation only, explicitly opt in:

```bash
.venv/bin/python -m scripts.evaluation.export_langsmith \
  --split development --output /tmp/fitness-development-examples.json \
  --upload --allow-draft --dataset-name fitness-scenarios-v1-development-draft
```

The command creates a fresh dataset; use a new name for a new version. It refuses unreviewed uploads without `--allow-draft`. Held-out export requires `--split held_out` and a dataset name containing `held_out`. Uploading is not executing or scoring an experiment. The 30 development cases have now been uploaded to the configured EU workspace. Live direct-search and recorded agent-evidence review experiments have run; see the results report. The 70 held-out cases have not been evaluated or uploaded. An upload by itself still does not constitute an evaluation.

Once references and fixtures are ready: run the direct-retrieval baseline, then the current agentic retriever, then end-to-end Coach/Designer scenarios. Compare experiments with identical cases and frozen references. Save detailed results locally as well as in LangSmith.

Official references: [RAG evaluation](https://docs.langchain.com/langsmith/evaluate-rag-tutorial), [evaluation methods](https://docs.langchain.com/langsmith/evaluation-types).

## Reproduce the retrieval pilot

Keep credentials in an ignored `.env`. EU workspaces require `LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com`; use the endpoint appropriate to your actual workspace. An existing Ollama credential file can be supplied with `--cloud-env` without copying its key.

The embedding worker needs a Python environment with PyTorch, Transformers and CUDA support. The measured run reused an existing local Python 3.12 GPU environment with torch 2.6.0+cu124 and transformers 4.57.6; it did not modify that environment. The light core environment alone cannot execute embeddings. Fresh GPU dependency installation for this project remains to be verified. The encoder uses normalized CLS embeddings with 512-token truncation, matching the configured BGE recipe; the historical index revision is unknown.

With your local Qdrant running and a locally downloaded pinned BGE model:

```bash
.venv/bin/python -m scripts.evaluation.snapshot_corpus
.venv/bin/python -m scripts.evaluation.run_direct_retrieval \
  --embedding-python /path/to/gpu-env/bin/python \
  --model /path/to/bge-large-en-v1.5
.venv/bin/python -m scripts.evaluation.audit_development_constraints
.venv/bin/python -m scripts.evaluation.run_agentic_retrieval \
  --cloud-env /path/to/ollama.env \
  --embedding-python /path/to/gpu-env/bin/python \
  --model /path/to/bge-large-en-v1.5 --limit 16 --trace \
  --output .evaluation-local/my-agentic-run
.venv/bin/python -m scripts.evaluation.assess_agentic_outputs \
  --input .evaluation-local/my-agentic-run/results.json \
  --output .evaluation-local/my-assessment.json
.venv/bin/python -m scripts.evaluation.review_agentic_in_langsmith \
  --cloud-env /path/to/ollama.env \
  --input .evaluation-local/my-assessment.json \
  --output .evaluation-local/my-judge-review.json
```

The review step judges saved actual evidence outputs. Its LangSmith target duration is replay overhead; use `recorded_agent_seconds` for the original generation duration. Judge calls run on Ollama Cloud, incur account usage, and may be unavailable on a given plan. Mistral Large 3 is currently blocked by HTTP 402 on the tested account; gpt-oss:120b is accessible. Nothing automatically purchases credits or changes a subscription.

Raw snapshots, vectors, complete messages, databases and credentials must stay out of Git. Only aggregate results are published.

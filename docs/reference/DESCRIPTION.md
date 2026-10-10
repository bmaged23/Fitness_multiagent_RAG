# Fitness Multiagent RAG — Project Description

## What it is

An AI fitness coaching system that combines three specialized agents to deliver personalized, grounded workout plans through a conversational interface.

A trainee talks to a **Coach** agent that remembers them across sessions. When a plan is needed, Coach delegates to a **Program Designer** agent, which retrieves relevant workout programs from a real dataset via a **Retriever** agent, then synthesizes a structured, validated plan tailored to the trainee's goal, fitness level, equipment, and any injuries or limitations.

---

## Why it was built

Most AI fitness tools either pull from generic exercise databases or hallucinate plans with no grounding. This system grounds every plan in a real 600K-row fitness dataset (Kaggle), enforces structural rules deterministically (equipment match, rest days, difficulty alignment), and runs an LLM self-critique pass when synthesizing across multiple source programs — catching coherence problems that rules alone can't.

It also solves the long-term memory problem: one rolling, salience-truncated summary per trainee in SQLite, so the coach remembers past conversations without growing unbounded.

---

## Architecture

```
Trainee ─► Coach agent (main)
               │
               ├──► Retriever agent (subagent)
               │         └──► Qdrant  (workout corpus: programs + exercises)
               │
               └──► Program Designer agent (subagent)
                         ├──► Retriever (for grounding)
                         └──► SQLite   (plans, revisions, trainee profiles, memory)
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Agent framework | deepagents + LangGraph |
| Vector store | Qdrant (two collections: programs + exercises) |
| Embeddings | BAAI/bge-large-en-v1.5 (dim=1024) via sentence-transformers |
| LLM backend | vLLM served locally at port 7834, accessed via LangChain ChatOpenAI |
| Database | SQLite — 5 tables (trainees, plans, plan_revisions, progress_logs, coach_memory) |
| Schema validation | Pydantic v2 |
| Frontend | Streamlit (not yet built) |
| Language | Python 3.12 |

---

## Implemented so far

### Program Designer agent (complete)
Interactive 3-stage plan generation flow:

1. **Stage 0 — Pre-flight**: validates trainee profile (goal, fitness level, equipment) against allowed value sets. If invalid, the model asks the trainee clarifying questions conversationally and persists their answers via `update_trainee_profile`.
2. **Stage 1 — Structure proposal**: proposes a compact training skeleton (split type, weekly schedule, duration, rep style) for user approval before any exercises are generated.
3. **Stage 2 — Week 1 generation**: fills exercise details for Week 1 only, guided by the approved structure.
4. **Stage 3 — Validate and save**: runs structural validation, optional LLM self-critique (diff-based, not full plan regeneration), expands Week 1 to full duration programmatically, and writes to SQLite.

9 tools including `collect_missing_info`, `update_trainee_profile`, `propose_plan_structure`, `synthesize_week_one`, `validate_and_critique`, `save_plan`, and `patch_existing_plan`.

### Retriever agent (complete)
Accumulate-and-expand loop — not a simple retry:
- Decomposes queries into sub-needs (slot-based + free-form LLM fallback)
- Adaptive top-k per query specificity
- Per-need validation and targeted query rewriting
- Overall coverage check with dynamic gap-filling
- Hard ceiling of 6 steps to prevent runaway loops

6 tools: `decompose_query`, `search_programs`, `search_exercises`, `rewrite_search_query`, `validate_chunk_relevance`, `check_retrieval_coverage`.

### Data pipeline (complete)
- Dataset downloaded from Kaggle (600K exercise rows + 2,598 program summaries)
- Chunking, embedding, and Qdrant indexing scripts
- SQLite schema and DB initialization scripts

### Test runner (`main.py`)
Multi-turn interactive CLI for testing the Designer directly:
- Shared `FilesystemBackend` across all stages so `write_file`/`read_file` persists between invocations
- Clean visual separation: dim internal tool calls vs. cyan-boxed model messages
- Automatic retry when profile questions need to be answered before proceeding

---

## Still to build

- **Coach agent** — conversation, identity resolution, routing, long-term memory pipeline
- **Orchestration** — wiring all three agents together with shared VFS and SQLite memory backend
- **Streamlit UI** — chat interface with plan rendering and progress charts

---

## Dataset

[600K Fitness Exercise and Workout Program Dataset](https://www.kaggle.com/datasets/adnanelouarii/600k-fitness-exercise-and-workout-program-dataset) by Adnane Louarii (Kaggle).
Chosen specifically because it contains program-level narrative text (goals, weekly structure, difficulty) alongside exercise-level data — giving the Designer meaningful grounding rather than a simple exercise lookup table.

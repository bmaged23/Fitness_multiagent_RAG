# Fitness_multiagent_RAG_project

## Watch the demo

[![Watch Alex: login, personalized workouts, and voice coaching](docs/media/fitness-coach-demo-poster.png)](docs/media/fitness-coach-demo.mp4)

**3:20 walkthrough:** login → chat → workout proposal → exercise details → approval → saved plans → PDF export → speech-to-text → spoken reply.

[Watch / download the MP4](docs/media/fitness-coach-demo.mp4) · [Recording notes](docs/demo-recording.md)

## Run the chat app

From the project directory with `.venv` activated:

```bash
python3 -m streamlit run app/streamlit_app.py
```

Open http://localhost:8501. Log in with your existing account or sign up before accessing chat. The app uses the same Coach, SQLite database, workout drafts, and nutrition plans as the terminal. Conversation history remains in the current browser session; approved plans and stored drafts persist in SQLite. Use **My plans** to select a workout week, review pending drafts, browse past workout/nutrition plans, and inspect revision snapshots. Workout days use exercise tables; nutrition meals show exact portions and alternatives. The default workout week is estimated from the save date and can be changed manually. Use the sidebar to view or download saved plans and log out.

A multi-agent, RAG-grounded fitness coaching system built on **deepagents**, backed by **Qdrant** (workout corpus) and **SQLite** (trainee data), with a **Streamlit** front end.

> The detailed architecture below preserves historical design notes. The Streamlit app and video above show the implemented workflow.

---

## Table of contents

1. [What this is](#1-what-this-is)
2. [System architecture](#2-system-architecture)
3. [Agent: Retriever](#3-agent-retriever-subagent)
4. [Agent: Program Designer](#4-agent-program-designer-subagent)
5. [Agent: Coach](#5-agent-coach-main-agent)
6. [Database](#6-database-sqlite-5-tables)
7. [Data source & embedding pipeline](#7-data-source--embedding-pipeline)
8. [deepagents wiring](#8-deepagents-wiring)
9. [Full project tree](#9-full-project-tree)
10. [Every file, what it contains](#10-every-file-what-it-contains)
11. [Conventions](#11-conventions)
12. [Open decisions](#12-open-decisions--do-not-guess-ask-the-user)
13. [Suggested build order](#13-suggested-build-order)

---

## 1. What this is

A trainee talks to a **Coach** agent (chat, via Streamlit). Coach can build or revise structured workout **plans** by delegating to a **Program Designer** agent, which in turn grounds itself in a real workout dataset via a **Retriever** agent querying Qdrant. Coach also remembers each trainee across sessions via a summarized, salience-truncated long-term memory backed by SQLite.

This is not a simple "one retrieval call → one answer" RAG app. All three agents are deepagents-native: they use the planning/todo tool, a shared virtual filesystem for passing state between agents in a session, subagent delegation, and dedicated skill files for their more complex procedures.

---

## 2. System architecture

```
                         ┌────────────────────┐
                         │     Coach agent     │   ← main deepagents agent
                         │  (trainee-facing)   │      owns: conversation,
                         └──────────┬──────────┘      identity, routing, memory
                                    │
                 ┌──────────────────┴──────────────────┐
                 │                                      │
       ┌─────────▼─────────┐                 ┌──────────▼──────────┐
       │  Retriever agent   │◄────────────────┤  Program Designer    │
       │     (subagent)      │   can call      │      (subagent)      │
       │  search only, no    │   Retriever      │  builds/revises      │
       │  fitness reasoning  │   directly       │  plan.json           │
       └─────────┬───────────┘                 └──────────┬───────────┘
                 │                                          │
       ┌─────────▼─────────┐                     ┌──────────▼──────────┐
       │       Qdrant        │                     │       SQLite         │
       │  workout corpus:     │                     │  trainee database:   │
       │  exercises +         │                     │  trainees, plans,    │
       │  program summaries   │                     │  plan_revisions,     │
       │  (payload-filtered)  │                     │  progress_logs,      │
       └─────────────────────┘                     │  coach_memory        │
                                                     └───────────────────────┘
```

Coach is the only agent the trainee talks to directly. Both Retriever and Designer can be called by Coach; Designer can also call Retriever directly when it needs fresh grounding for a revision. Only Designer writes to `plans`/`plan_revisions`; only Coach writes to `coach_memory`.

### Design principles established in conversation

- **Retriever doesn't reason about fitness.** Its only job is search quality — decomposition, adaptive chunk count, coverage validation, retry. It has no opinion on whether a plan is good.
- **Designer synthesizes, not just selects.** It combines multiple retrieved programs into one plan rather than picking the single closest match — more flexible, but this is *why* it needs a coherence guard (structural validation + conditional self-critique).
- **Coach routes by reasoning, not a hardcoded classifier.** Designer is exposed to Coach as an available tool; Coach's own judgment decides when a message needs it.
- **Persistent facts live in exactly one place.** Injuries, equipment, and goals live in `trainees` — never duplicated into a plan JSON or into the memory summary — so a fact only needs to be updated once to be correct everywhere.
- **Memory is rolling, not accumulating.** `coach_memory` holds one row per trainee, summarized and salience-truncated — not one row per session growing forever.
- **Every plan revision is audited.** `plan_revisions` stores a full before/after JSON snapshot of every patch plus what triggered it, so the system's own self-corrections are distinguishable from trainee-requested changes.

---

## 3. Agent: Retriever (subagent)

Callable by both Coach and Program Designer.

### Loop — accumulate-and-expand, not simple retry

This was deliberately designed to be more advanced than a single retry loop: it tracks coverage of the **overall information need** across multiple sub-queries, and keeps going even after some sub-queries already succeeded, if the original request still isn't fully answerable.

1. **Decompose the need.** Slot-based extraction first — `goal`, `equipment`, `difficulty`, `duration` — with a **free-form LLM coverage-judgment fallback** for queries that don't map to slots cleanly (e.g. "why am I sore for 3 days" isn't a plan-design query, it's a knowledge question).
2. **Pick the next unaddressed need, query Qdrant.** Chunk count is **adaptive to query specificity** — not a fixed top-k.
3. **Validate against that specific need.** Is the result relevant and sufficient, or noise?
4. **Sufficient** → save to the accumulated pool, mark that need satisfied.
5. **Insufficient** → rewrite the query, retry **that same need**. (Retry is per-need, not a single global counter — a need that keeps failing doesn't block progress on other needs.)
6. **Re-check overall coverage.** Given everything accumulated so far, is the original query now answerable? If not, formulate a new sub-query for the specific gap — this is the "expand" half of the loop.
7. **Stop condition.** The model can self-assess and surrender early once it believes coverage is sufficient (cheaper, usually a good judge) — but a **hard ceiling of 5–6 total retrieval steps** always applies underneath, so a confused model can't loop forever.

**Output:** accumulated chunks + a confidence flag, so Designer/Coach know not to over-trust a low-coverage result.

**Callers:** Coach (open-ended/knowledge questions) and Program Designer (structured plan-building and revision queries) — both are allowed to call it, which is exactly why the slot-based *and* free-form fallback both exist: Designer's queries are more structured, Coach's more conversational.

---

## 4. Agent: Program Designer (subagent)

Turns a goal + retrieved chunks into a **strict JSON plan**.

### New plan vs. revision

```
                    ┌───────────────────┐
                    │  Classify request   │
                    │ new plan or revision │
                    └──────────┬────────────┘
                 ┌──────────────┴──────────────┐
        ┌────────▼────────┐             ┌───────▼────────┐
        │    New plan       │             │    Revision      │
        │ retrieve, then     │             │ check plan.md    │
        │ synthesize across   │             │ first — only      │
        │ multiple programs   │             │ retrieve on gap    │
        └────────┬────────────┘             └────────┬─────────┘
                 └──────────────┬──────────────────────┘
                         ┌───────▼────────┐
                         │    Validate      │
                         │ rules (always)   │
                         │ + self-critique   │
                         │ (multi-source only)│
                         └───────┬────────────┘
                         ┌───────▼────────┐
                         │  Write plan.json │
                         └──────────────────┘
```

1. **Classify** the request: new plan, or revision to an existing one.
2. **New plan** → call Retriever, then **synthesize** a draft by combining chunks from multiple retrieved programs (not just selecting one).
3. **Revision** → check `plan.md`/context **first** for what's needed (e.g. is a knee-safe squat substitute already in what was previously retrieved?). Only call Retriever if that check comes up empty. This reuses the same coverage-check pattern as Retriever itself.
4. **Structural validation** — deterministic, rule-based, **always runs**: equipment matches the trainee's available equipment, rest days are present, difficulty progression makes sense. Cheap, catches concrete failure modes.
5. **Self-critique** — an LLM pass checking coherence, goal fit, and injury constraints. **Only triggered when synthesizing from multiple sources** (new plans, or revisions that pulled in fresh multi-source retrieval) — this is specifically where two retrieved programs can conflict in ways rules can't catch (e.g. mixing a beginner full-body split with advanced 6-day PPL volume).
6. **Write `plan.json`** + a short natural-language change summary back to Coach.

### Output schema (draft, validate against `schemas/plan_schema.py`)

```json
{
  "goal": "string",
  "difficulty": "string",
  "duration_weeks": 0,
  "equipment_available": ["string"],
  "weeks": [
    {
      "week": 1,
      "days": [
        {
          "day": 1,
          "focus": "string",
          "rest_day": false,
          "exercises": [
            {
              "name": "string",
              "sets": 0,
              "reps": 0,
              "rest_seconds": 0,
              "equipment": "string",
              "muscle_group": "string",
              "notes": "string"
            }
          ]
        }
      ]
    }
  ]
}
```

Injury/limitation constraints are **read from the `trainees` table** at validation time, not duplicated into the plan JSON — so a trainee only has to report an injury once and it stays enforced across every future revision.

---

## 5. Agent: Coach (main agent)

Owns the conversation, trainee identity, routing, and long-term memory.

### Session start — identity resolution

```
   Session starts
         │
   Check identity  (name + secondary ID: phone / email / trainee_id)
         │
   ┌─────┴─────┐
   │           │
 Match      No match
   │           │
Returning    New trainee
trainee      → run intake flow (name, contact, goals,
→ load        equipment, injuries) → write trainees row
profile +
memory +
active plan
   │           │
   └─────┬─────┘
   Check progress_logs for missed-session pattern
         │
   Begin conversation (proactively, if a pattern was flagged)
```

1. **Check identity**: name **+ a secondary ID**. Name alone is not sufficient — a name match with a secondary-ID mismatch triggers a confirmation prompt, never a silent load. This matters because the data involved (injuries, health goals) is sensitive.
2. **Match → returning trainee**: load the `trainees` profile row, the latest `coach_memory` summary, and the active `plans` row.
3. **No match → new trainee**: run the intake flow — collect name, contact/secondary ID, goals, equipment, injuries/limitations — then write the first `trainees` row. This feeds directly into Designer building their first plan.
4. **Check `progress_logs`** for a missed-session pattern. If flagged, Coach opens the conversation proactively (e.g. "noticed you've missed leg day a few times, everything okay?") instead of waiting to be asked — this is the proactive half of "keep the trainee engaged."

### Per-message loop

1. **Load context**: profile, memory, active plan.
2. **Reason: handle directly, or route to Designer.** Direct covers general coaching and knowledge questions (Coach may call Retriever itself for grounding). Routed covers anything that touches the actual plan — building or revising it.
3. **Interim acknowledgment before delegating.** Since Retriever's loop plus Designer's synthesize/validate chain has real latency (potentially 15–20s), Coach sends a short acknowledgment ("let me check on knee-safe alternatives...") before going into that chain, rather than leaving the trainee staring at silence. This is the second half of "keep the trainee engaged."
4. **Respond.** Relay Designer's structured JSON output in trainee-facing natural language, or answer directly.
5. **Update memory** (full pipeline below). Also writes to `progress_logs` if the message contained loggable info (completed a workout, reported weight, mentioned pain).

### Long-term memory pipeline

Rolling and summarized — **one row per trainee**, not one row per session, and specifically salience-based so it stays useful rather than growing indefinitely.

```
Summarize session → Merge with rolling summary → Check trigger
                                                        │
                                    (length threshold OR N sessions
                                     since last truncation — either fires it)
                                                        │
                                                  Salience pass
                                          (LLM judges what's still
                                           relevant, drops the rest)
                                                        │
                                                  Write back
                                          (overwrite the single
                                           coach_memory row)
```

Persistent facts (injuries, goals, equipment) live in `trainees`, **not** in this rolling summary — `coach_memory` is conversational/relational context only (rapport, past complaints, what motivated the trainee last time). That separation is what makes aggressive truncation of old conversational detail safe: nothing safety-critical lives only in the summary.

---

## 6. Database (SQLite, 5 tables)

```sql
trainees
  id                   PK
  name                 text
  secondary_id         text        -- phone / email / external trainee_id
  age                  int
  gender               text
  fitness_level        text
  equipment_available  text/json
  injuries_limitations text        -- persistent, source of truth
  goal                 text
  created_at           datetime

plans
  id              PK
  trainee_id      FK → trainees
  difficulty      text
  duration_weeks  int
  plan_json       json             -- Designer's structured output
  status          text             -- active / completed / archived
  created_at      datetime
  updated_at      datetime

plan_revisions
  id                   PK
  plan_id              FK → plans
  revision_number      int
  change_description   text
  previous_plan_json   json        -- full snapshot before the patch
  new_plan_json        json        -- full snapshot after the patch
  triggered_by         text        -- user_request / self_critique / validation_fix
  created_at           datetime

progress_logs
  id                  PK
  trainee_id          FK → trainees
  plan_id             FK → plans
  log_date            date
  weight_kg           float
  completed_workouts  json
  notes               text

coach_memory
  id                              PK
  trainee_id                      FK → trainees, unique (one row per trainee)
  summary_text                    text   -- rolling, salience-truncated
  session_count_since_truncation  int
  last_updated                    datetime
```

**Relationships:** one `trainees` row → many `plans` → many `plan_revisions` per plan. `progress_logs` and `coach_memory` both key off `trainee_id` directly (not `plan_id`) — memory and progress persist across plans, not scoped to just one.

---

## 7. Data source & embedding pipeline

**Dataset:** [600K Fitness Exercise & Workout Program Dataset](https://www.kaggle.com/datasets/adnanelouardi/600k-fitness-exercise-and-workout-program-dataset) (Kaggle). Chosen deliberately over smaller exercise-lookup-only datasets because it has **program-level narrative text** (goals, nutrition guidelines, difficulty, weekly structure) — that's what gives Designer something to actually reason and coach over, not just spit back a single exercise definition.

- `fitness_exercises.csv` — ~605,033 rows, exercise-level.
- `program_summary.csv` — 2,598 rows, program-level.

The dataset is **not** pre-chunked or pre-embedded — chunking, embedding, and Qdrant indexing are all pipeline steps this project owns.

### Pipeline (five sequential scripts)

| Step | Script | What it does |
|---|---|---|
| 1. Download | `scripts/download_dataset.py` | Wraps `kaggle datasets download`, unzips into `data/raw/`, verifies both CSVs are present with a sane row count. |
| 2. Inspect | `scripts/inspect_schema.py` | Loads both CSVs, prints columns/dtypes/null counts/sample rows, writes findings to `data/schema/data_dictionary.md`. **Run this before finalizing chunking** — do not assume column names. |
| 3. Chunk | `scripts/chunk_data.py` | Two strategies: row-level chunks for `fitness_exercises.csv` (one exercise per chunk); field-grouped narrative chunks for `program_summary.csv` (goal + nutrition + difficulty text combined per program). Outputs JSONL to `data/processed/`. |
| 4. Embed & index | `scripts/embed_and_index.py` | Reads processed JSONL, computes embeddings, upserts into Qdrant with metadata as payload, using the collection config from `vectorstore/schema.py`. |
| 5. Init trainee DB | `scripts/init_db.py` | Runs `db/schema.sql` against a fresh SQLite file, creating all five tables above. |

### Qdrant payload schema (metadata, attached as payload — not embedded into the vector)

| Payload field | Source | Used by |
|---|---|---|
| `source_table` | exercises vs. program_summary | Retriever routes queries to the right sub-corpus |
| `goal` | program_summary text, extracted | Slot filter — fat loss, hypertrophy, strength, etc. |
| `difficulty` | program_summary column | Slot filter + Designer's structural validation |
| `equipment` | exercise-level column | Slot filter + Designer's equipment-match check |
| `muscle_group` | exercise-level column | Slot filter for exercise substitutions |
| `duration_weeks` | program_summary column | Slot filter for program length |
| `chunk_id` / `text` | generated at chunk time | the retrieved content itself |

**`OPEN`:** exact field names are the *intended* mapping, not yet verified — confirm against the real output of `inspect_schema.py` before finalizing `vectorstore/schema.py`.

---

## 8. deepagents wiring

Beyond plain tool-calling, this project uses four deepagents primitives deliberately:

| Primitive | How it's used here |
|---|---|
| **Planning / todo tool** | Coach tracks multi-step turns explicitly (check identity → load profile → call Retriever → call Designer → validate → respond → update memory). This is also what powers the interim status updates sent to the trainee. |
| **Virtual filesystem** | Session-scoped state passing between agents: Retriever writes chunks to a file → Designer reads it and writes `plan.md`/`plan.json` → Coach reads `plan.md` to reply. This is **short-term** memory — resets each session. |
| **Subagents** | Retriever and Program Designer are callable subagent tools from Coach (the main agent). Retriever is also directly callable from Designer. |
| **Custom long-term memory store** | SQLite-backed, replacing deepagents' default in-memory store — implements `get`/`set`/`merge` against `coach_memory` and `trainees`, called at session start and end. |

### Skills — one per owning agent, not a flat top-level folder

This mirrors how deepagents subagents actually declare their own skill sets — each agent's `skills/` folder lives inside its own subtree:

- `agents/coach/skills/trainee-intake.md` — the formalized onboarding procedure.
- `agents/retriever/skills/retrieval-coverage-loop.md` — the full accumulate-and-expand procedure.
- `agents/designer/skills/plan-structural-validation.md` — the deterministic rule checks.
- `agents/designer/skills/plan-revision.md` — check-first, patch-vs-rebuild logic.

Each agent also has its own `prompts/` folder of `.md` files (not inline Python f-strings) — no shared prompt file across agents, since Coach's persona, Designer's synthesis prompting, and Retriever's query decomposition prompting all iterate independently and shouldn't be tangled together in one file.

---

## 9. Full project tree

```
Fitness_multiagent_RAG_project/
├── README.md                       # this file
├── pyproject.toml
├── .env.example
├── .gitignore
├── Makefile
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── .github/workflows/
│   └── tests.yml
│
├── config/
│   └── settings.py
│
├── data/
│   ├── raw/                        # gitignored — downloaded CSVs
│   ├── processed/                  # gitignored — chunked JSONL
│   └── schema/
│       └── data_dictionary.md      # generated by inspect_schema.py
│
├── scripts/
│   ├── download_dataset.py
│   ├── inspect_schema.py
│   ├── chunk_data.py
│   ├── embed_and_index.py
│   └── init_db.py
│
├── src/fitness_multiagent_rag/
│   ├── __init__.py
│   │
│   ├── agents/
│   │   ├── coach/
│   │   │   ├── agent.py
│   │   │   ├── identity.py
│   │   │   ├── memory.py
│   │   │   ├── routing.py
│   │   │   ├── prompts/
│   │   │   │   ├── system_prompt.md
│   │   │   │   ├── intake_prompts.md
│   │   │   │   └── routing_prompts.md
│   │   │   └── skills/
│   │   │       └── trainee-intake.md
│   │   │
│   │   ├── retriever/
│   │   │   ├── agent.py
│   │   │   ├── coverage.py
│   │   │   ├── query_rewrite.py
│   │   │   ├── prompts/
│   │   │   │   ├── system_prompt.md
│   │   │   │   ├── query_decomposition.md
│   │   │   │   └── coverage_check.md
│   │   │   └── skills/
│   │   │       └── retrieval-coverage-loop.md
│   │   │
│   │   └── designer/
│   │       ├── agent.py
│   │       ├── synthesis.py
│   │       ├── validation.py
│   │       ├── self_critique.py
│   │       ├── prompts/
│   │       │   ├── system_prompt.md
│   │       │   ├── synthesis_prompts.md
│   │       │   ├── self_critique_prompts.md
│   │       │   └── revision_prompts.md
│   │       └── skills/
│   │           ├── plan-structural-validation.md
│   │           └── plan-revision.md
│   │
│   ├── orchestration/
│   │   └── deepagent_setup.py
│   │
│   ├── schemas/
│   │   ├── plan_schema.py
│   │   └── trainee_schema.py
│   │
│   ├── db/
│   │   ├── models.py
│   │   ├── schema.sql
│   │   ├── crud.py
│   │   └── connection.py
│   │
│   ├── vectorstore/
│   │   ├── qdrant_client.py
│   │   ├── schema.py
│   │   └── embeddings.py
│   │
│   ├── memory/
│   │   └── sqlite_memory_backend.py
│   │
│   ├── llm/
│   │   └── client.py
│   │
│   └── utils/
│       ├── logging.py
│       └── prompt_loader.py
│
├── app/
│   ├── streamlit_app.py
│   └── components/
│       └── chat_ui.py
│
├── notebooks/
│   ├── 01_dataset_exploration.ipynb
│   ├── 02_chunking_experiments.ipynb
│   └── 03_retrieval_eval.ipynb
│
├── tests/
│   ├── test_retriever.py
│   ├── test_designer.py
│   ├── test_coach.py
│   └── test_memory_pipeline.py
│
└── docs/
    └── Fitness_multiagent_RAG_project_reference.html
```

---

## 10. Every file, what it contains

### `agents/coach/` — main agent

| File | Contains |
|---|---|
| `agent.py` | Instantiates the Coach deepagents agent: loads its system prompt, registers Retriever and Designer as subagent tools, registers DB read/write tools, wires the planning/todo tool. |
| `identity.py` | Name + secondary ID lookup against `trainees`, mismatch handling (confirmation prompt, not silent load), triggers the intake flow for new trainees. |
| `memory.py` | The full summarize → merge → trigger-check → salience-truncate → write-back pipeline described in §5, run at the end of each session. |
| `routing.py` | Tool descriptions and reasoning scaffolding that let Coach's own judgment decide handle-directly vs. route-to-Designer — no hardcoded classifier lives here. |
| `prompts/system_prompt.md` | Core persona, tone, behavioral rules: proactive check-ins on missed sessions, interim acknowledgments before delegating, the injury/medical escalation boundary. |
| `prompts/intake_prompts.md` | The onboarding conversation script — what to ask a new trainee, in what order. |
| `prompts/routing_prompts.md` | Guidance embedded in Designer's tool description so Coach's reasoning routes plan-related questions correctly. |
| `skills/trainee-intake.md` | Formalized deepagents skill version of the intake procedure, loaded on demand. |

### `agents/retriever/` — subagent

| File | Contains |
|---|---|
| `agent.py` | Defines the Retriever subagent, registers the Qdrant search tool, wires the coverage-check loop with its 5-6 step ceiling. |
| `coverage.py` | Slot-based decomposition with free-form LLM fallback; tracks which needs are satisfied vs. still open across the loop. |
| `query_rewrite.py` | Sub-query rewriting on per-need validation failure, and new sub-query formulation when the overall coverage check finds a gap. |
| `prompts/system_prompt.md` | Retriever's role definition — search quality only, no fitness reasoning. |
| `prompts/query_decomposition.md` | Prompting for splitting a request into slots or sub-queries. |
| `prompts/coverage_check.md` | Prompting for the free-form "can I answer this yet, what's missing" fallback judgment. |
| `skills/retrieval-coverage-loop.md` | Formalized skill for the full accumulate-and-expand procedure. |

### `agents/designer/` — subagent

| File | Contains |
|---|---|
| `agent.py` | Defines the Designer subagent, registers Retriever as a callable tool, registers DB read/write for `plans` and `plan_revisions`. |
| `synthesis.py` | Combines chunks from multiple retrieved programs into a single draft plan matching the strict JSON schema. |
| `validation.py` | Deterministic structural rule checks — equipment, rest days, difficulty progression. Always runs, cheap. |
| `self_critique.py` | LLM self-critique pass, conditional on multi-source synthesis. |
| `prompts/system_prompt.md` | Role, output schema contract, coherence-guard instructions. |
| `prompts/synthesis_prompts.md` | Prompting for combining multiple retrieved programs into one coherent plan. |
| `prompts/self_critique_prompts.md` | Prompting for the conditional self-critique pass. |
| `prompts/revision_prompts.md` | Prompting for check-first, patch-vs-rebuild revision logic. |
| `skills/plan-structural-validation.md` | Formalized skill for the deterministic rule checks. |
| `skills/plan-revision.md` | Formalized skill for revision handling — when to patch vs. re-retrieve. |

### `orchestration/`, `schemas/`, `llm/`

| File | Contains |
|---|---|
| `orchestration/deepagent_setup.py` | The composition root — instantiates Coach as the main deepagents agent, registers Retriever and Designer as subagents with their own prompts/skills, wires the SQLite long-term memory backend and Qdrant client, exposes a single `build_agent()` entrypoint used by the Streamlit app. |
| `schemas/plan_schema.py` | Pydantic models mirroring `plan.json` (`WeekPlan`, `DayPlan`, `Exercise`) — Designer validates its own output against this before writing to the DB; Coach uses it to render trainee-facing text. |
| `schemas/trainee_schema.py` | Pydantic model for trainee profile fields, used at intake and at every DB read/write boundary. |
| `llm/client.py` | Abstraction over the LLM backend (vLLM-served open model vs. Claude API — `OPEN`) so all three agents call through one interface and switching backends later doesn't touch agent logic. |

### `db/`, `memory/`

| File | Contains |
|---|---|
| `db/models.py` | Model classes mirroring the five tables in §6. |
| `db/schema.sql` | Raw `CREATE TABLE` statements, run by `scripts/init_db.py`. |
| `db/crud.py` | Read/write functions used directly by agents: `get_trainee`, `save_plan`, `log_revision`, `update_memory`, `log_progress`. |
| `db/connection.py` | SQLite connection/session management, DB path sourced from `config/settings.py`. |
| `memory/sqlite_memory_backend.py` | Implements deepagents' long-term memory store interface, backed by `coach_memory` — `get`/`set`/`merge` called at session start/end. |

### `vectorstore/`

| File | Contains |
|---|---|
| `qdrant_client.py` | Thin wrapper — connect, search with payload filters, upsert. Used by both the indexing script and Retriever at query time. |
| `schema.py` | Collection config: vector size/distance metric, and the payload schema from §7. |
| `embeddings.py` | Embedding model wrapper, shared by the offline indexing script and the online Retriever query path so both embed identically. |

### `app/` — Streamlit

| File | Contains |
|---|---|
| `streamlit_app.py` | Entrypoint — session state management, calls `orchestration.deepagent_setup.build_agent()`, renders chat history, streams responses, and handles the identity/intake flow as the very first interaction of a session. |
| `components/chat_ui.py` | Reusable components: message bubbles, `plan.json` rendered as a formatted weekly table, progress charts pulled from `progress_logs`. |

### `config/`, `utils/`

| File | Contains |
|---|---|
| `config/settings.py` | Hardcoded config variables (per project owner's preference — no argparse): paths via `Path(__file__).parent`, Qdrant collection name, chunk size defaults, Retriever's step ceiling (5-6), memory truncation thresholds, LLM model name. |
| `utils/logging.py` | Shared logging config across the project. |
| `utils/prompt_loader.py` | Loads `.md` prompt files from each agent's `prompts/` folder, handles templating/variable substitution. |

### `tests/`

| File | Contains |
|---|---|
| `test_retriever.py` | Unit tests for the coverage-check loop against mocked Qdrant responses. |
| `test_designer.py` | Tests for structural validation rules and synthesis logic against fixture chunks. |
| `test_coach.py` | Tests for identity resolution and routing decisions. |
| `test_memory_pipeline.py` | Tests the summarize → merge → truncate logic in isolation from the agents. |

### Root & infra

| File | Contains |
|---|---|
| `pyproject.toml` | Dependencies: deepagents, qdrant-client, streamlit, an embeddings library, pandas, pydantic, sqlite3/SQLAlchemy. |
| `.env.example` | `QDRANT_URL`, `QDRANT_API_KEY`, LLM backend config (vLLM endpoint or API key), `SQLITE_DB_PATH`. |
| `Makefile` | Shortcuts: `make download-data`, `make chunk`, `make embed`, `make init-db`, `make run-app`, `make test`. |
| `docker/docker-compose.yml` | App service + Qdrant service. |
| `.github/workflows/tests.yml` | CI — runs pytest on push. |
| `data/schema/data_dictionary.md` | Generated documentation of the dataset's real columns — output of `inspect_schema.py`, not hand-written; treat as generated, regenerate if the dataset changes. |

---

## 11. Conventions

Apply these throughout, they come directly from the project owner's existing engineering habits:

- **Hardcoded config variables over argparse** — everything configurable lives in `config/settings.py`, not CLI flags.
- **`Path(__file__).parent`** for path resolution — never hardcoded absolute paths or reliance on `os.getcwd()`.
- **Complete file delivery, not partial diffs** — when generating or editing a file, produce the whole file, not a fragment.
- Familiar stack elsewhere in this project owner's work (useful context, not all necessarily used here): Python, FastAPI, Docker, PyTorch, Hugging Face, Neo4j, Qdrant, FAISS, ChromaDB, PostgreSQL/MySQL, vLLM, NeMo, LangGraph/LangChain, Linux server administration.

---

## 12. Open decisions — do not guess, ask the user

- **Embedding model** for `vectorstore/embeddings.py`.
- **LLM backend** for the three agents — vLLM-served open model (matches the project owner's other pipelines) vs. Claude API.
- **Real Qdrant payload field names**, pending the actual output of `inspect_schema.py`.
- **Injury/medical escalation boundary** — when Coach should say "see a doctor" instead of letting Designer quietly work around a symptom, and whether `injuries_limitations` is trainee-editable mid-conversation or requires an explicit confirmation step.
- **Low-confidence Retriever behavior** — does Designer build a best-effort plan flagged low-confidence, or does Coach ask a clarifying question instead of guessing?
- **Eval strategy** before trusting the loop with real trainees.

---

## 13. Suggested build order

1. `scripts/download_dataset.py` → `scripts/inspect_schema.py` → fill in `data/schema/data_dictionary.md` for real. **Do this before writing any chunking or Qdrant schema code.**
2. Finalize `scripts/chunk_data.py` against the real schema, then `scripts/embed_and_index.py`.
3. `scripts/init_db.py` to stand up the SQLite tables.
4. Build **Retriever first** (it's a dependency of Designer), then **Designer**, then **Coach**.
5. `orchestration/deepagent_setup.py` to wire all three together.
6. `app/streamlit_app.py` last, only once the agent chain works end-to-end via a script or notebook test.

## Optional English voice chat

Voice controls appear after login. Click the microphone inside **Message Alex…**. Wait until **Starting microphone…**
changes to **Recording — speak now**, then speak and submit the recording.
The app transcribes it in English and sends the transcript directly to Alex.
The transcript follows the same Coach workflow as a typed message. Click
**Listen to this reply** beneath an assistant reply to generate audio, then use
its player. Submitting a recording sends its transcript; audio replies never autoplay.

The local models are faster-whisper **base.en** (CUDA int8/float16) and
**Kokoro-82M**, with American English voices `am_michael` (man) and `af_heart` (woman).
Choose **Reply voice** in the sidebar before clicking **Listen to this reply**.
Both voices share one GPU model; switching voices does not load a second model. Models load only
when requested and remain cached for later requests. CUDA is required for voice;
text chat remains available when voice setup fails. Recordings are limited to
2 minutes. Voice recordings and generated audio are not written to the database.

For a fresh setup, retain a PyTorch build compatible with your NVIDIA driver,
install `requirements-speech.txt` into the project virtual environment, then run:

```bash
python scripts/download_speech_models.py
```

Start the app as usual with `python -m streamlit run app/streamlit_app.py`.
Allow microphone access in your browser (localhost or HTTPS).

## PDF plan downloads

The sidebar exports your active nutrition plan and workout program as PDF files.
Workout exports include every saved week, daily exercise tables, rest days, and
progression. Nutrition exports include daily targets, meals, portions,
alternatives, and dietary notes. Download buttons are disabled until an active
plan exists. Install `requirements-pdf.txt` when setting up a new environment.

Reply audio generates in the background while you browse My plans. Click Listen
on a reply, then press Play in the audio player directly beneath that reply.
Generated audio remains available when you return to Chat.

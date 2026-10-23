# Run the Fitness application with Docker

Public image: `bmaged23/fitness-multiagent-rag:cpu` (Linux amd64). Publication, CI post-publication pull/smoke checks and anonymous registry access are verified:

https://hub.docker.com/r/bmaged23/fitness-multiagent-rag

The image contains the Streamlit application, three agents, SQLite schema, PDF export, corpus preparation scripts and **BGE-large-en-v1.5** at revision `d4aa6901d3a41ba39fb536a557fa166f842b0e09`. It uses CPU inference so NVIDIA hardware is not required. Optional Whisper/Kokoro GPU speech is available through the source route and is disabled in this image.

The LLM runs through your configured provider; its weights are not bundled. The workout corpus is downloaded separately using your Kaggle account and indexed into the persistent Qdrant volume. The image does not contain personal accounts, saved plans, API keys, evaluation traces or redistributed workout data. BGE's model card declares MIT licensing; its upstream README is bundled with the weights.

## Local resource requirements

The main LLM is hosted on Ollama Cloud in the default cloud configuration; its model weights and inference do not use local RAM/VRAM. This image runs the embedding model locally, alongside Streamlit, Qdrant and SQLite. Local STT/TTS are optional through the GPU source route and are disabled in this CPU image. Local model requirements are therefore lighter than hosting the main LLM, while actual application latency and resource usage still need direct measurement.

## Requirements

Docker Engine/Desktop with Compose v2, Linux amd64 container support, internet for the initial corpus download and LLM calls, and your own Kaggle/provider credentials. Allow at least 8 GB available RAM and 8 GB free disk as an initial provisioning budget; full-stack peak resource usage is not yet measured. macOS/Windows require Docker Desktop; ARM native execution is not validated.

Commands below use a Bash shell (Linux/WSL2).

## Pull and configure

```bash
git clone https://github.com/bmaged23/Fitness_multiagent_RAG.git
cd Fitness_multiagent_RAG
cp .env.example .env
# Edit .env: provider URL/model/key and Kaggle credentials.
docker pull bmaged23/fitness-multiagent-rag:cpu
docker compose -f docker/compose.app.yml up -d qdrant
```

For Ollama Cloud, set `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL=https://ollama.com`, an account-accessible `OLLAMA_MODEL`, and `OLLAMA_API_KEY`. Container localhost refers to the container itself: if using a host Ollama service, supply a URL reachable from the container. Compose sets the internal Qdrant URL automatically.

## Provision the corpus once

Run in order; the embedding model is already included in the image:

```bash
docker compose -f docker/compose.app.yml run --rm app python scripts/download_dataset.py
docker compose -f docker/compose.app.yml run --rm app python scripts/chunk_data.py
docker compose -f docker/compose.app.yml run --rm app python scripts/embed_and_index.py --no-reseting
docker compose -f docker/compose.app.yml run --rm app python scripts/inspect_collections.py
docker compose -f docker/compose.app.yml run --rm app python scripts/init_db.py
```

The source is Kaggle's `adnanelouardi/600k-fitness-exercise-and-workout-program-dataset`. Review its source terms before use. These commands require provider-independent Kaggle access; a model image cannot supply account credentials. CPU indexing can take time. Do not run chunking/indexing concurrently or repeat chunking on an existing index without planning a versioned replacement: chunk generation assigns UUIDs.

## Launch

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

## Verification

The image smoke test performs real 1024-dimensional BGE inference, SQLite signup/login, PDF generation, HTTP health, actual Streamlit login UI rendering, synthetic CSV preparation, first-run indexing against a disposable Qdrant, retrieval, and persistent accounts across separate containers:

```bash
python3 scripts/smoke_container.py --image bmaged23/fitness-multiagent-rag:cpu
```

It creates and deletes its own temporary container and leaves your application volumes alone. Corpus retrieval and cloud answer quality are evaluated separately by the [100-case release gate](CI_CD.md). The [release verification record](RELEASE_VERIFICATION.md) identifies the tested source and CI evidence. Published CPU image digest:

```text
sha256:607ea87c7098638bd0f1227b848d0574bb413842cabf7cf69f4703e50662fc8b
```

For the exact release rather than the moving `cpu` tag:

```bash
docker pull bmaged23/fitness-multiagent-rag@sha256:607ea87c7098638bd0f1227b848d0574bb413842cabf7cf69f4703e50662fc8b
```

You can set this digest as `app.image` in Compose for a fixed deployment. On memory-constrained machines, add `EMBEDDING_BATCH_SIZE=8` to `.env` before corpus indexing.

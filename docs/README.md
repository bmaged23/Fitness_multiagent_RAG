# Documentation guide

| Topic | Start here |
|---|---|
| Install and use the application | [Main README](../README.md) |
| Pull and run the public image | [Docker setup](DOCKER.md) |
| Golden dataset, retrieval metrics and LLM judges | [Evaluation process](EVALUATION_PROCESS.md) |
| CPU/GPU latency, RAM/VRAM and reproduction | [Performance](PERFORMANCE.md) |
| Automated tests, evaluation gate and publishing | [CI/CD](CI_CD.md) |
| Successful releases and exact image digest | [Release verification](RELEASE_VERIFICATION.md) |
| Public Docker Hub description | [Canonical Hub README](DOCKERHUB_README.md) |
| Nutrition features | [Nutrition plans](nutrition_plans.md) |
| Architecture animation and demo | [Architecture](architecture.html), [demo page](demo.html), `media/` |

`performance/` contains publishable measurement summaries and charts. `reference/` holds historical design documents, the old demonstration environment snapshot and earlier release-progress notes; it is not the current setup guide. Recording/publishing notes are in `demo-recording.md` and `video-publishing.md`.

Private corpora, full evaluation traces, secrets, model caches and personal databases stay in ignored local storage rather than this documentation folder.

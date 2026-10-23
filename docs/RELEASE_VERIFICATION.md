# Verified application release — 23 October 2026

- Source commit: `bbbdfdd83a1c45b50d8269d8062db8a1706d755b`.
- [Successful GitHub Actions run](https://github.com/bmaged23/Fitness_multiagent_RAG/actions/runs/39876219203): offline → live 100-case evaluation → quality gate → image build → complete image smoke checks → public publication → pull and repeat checks.
- [Public Docker Hub repository](https://hub.docker.com/r/bmaged23/fitness-multiagent-rag); tags `cpu`, `latest`, `sha-bbbdfdd83a1c45b50d8269d8062db8a1706d755b`.
- Published CPU image digest: `sha256:607ea87c7098638bd0f1227b848d0574bb413842cabf7cf69f4703e50662fc8b`.
- Docker Hub metadata reports `is_private=false`; an anonymous registry manifest request returned HTTP 200.
- Linux amd64 image, Python 3.12.15, pinned CPU runtime, bundled BGE revision `d4aa6901d3a41ba39fb536a557fa166f842b0e09`. No NVIDIA GPU is required for this image. The CI retrieval evaluation uses the laptop GPU.

## Checks that passed

132 offline Python tests, dependency consistency, JavaScript microphone regression; 100 fresh query retrievals, 100 fresh Gemma answers and 200 valid GPT-OSS judge results, with all required metrics scored on 100/100 cases. The unchanged baseline and a 0.03 maximum absolute per-metric regression policy gated publication.

| Live CI metric | Result |
|---|---:|
| nDCG@5 | 0.7179 |
| Recall@5 | 82.00% |
| Correctness F1 | 81.01% |
| Completeness | 79.80% |
| Relevance | 91.00% |
| Faithfulness | 99.25% |
| Unsupported claims | 0.75% |

[Machine-readable CI evidence](release-evaluation-summary.json). The original baseline remains frozen separately under `evaluation/results/`. These are separate metric means, not percentages of questions passed or a full Coach/Designer quality certification.

The image checks perform real BGE inference, SQLite signup/login, PDF generation, HTTP health and real login UI rendering. A disposable Qdrant instance verifies synthetic CSV chunking, first-run indexing, retrieval and persistent account/files across separate containers. Test resources are removed; existing user data is not touched. These are provisioning checks, not synthetic model-accuracy claims. The same suite passed before publication and after pulling the published image in CI.

An additional local real Coach request using the existing fitness corpus and Ollama Cloud succeeded in 38.99 seconds. This is one observation, not average latency or time to first token.

## Independent public-image check

After the CI release, the published digest was pulled separately onto the laptop and the full smoke suite passed again, including fresh indexing and persistent-volume checks (35.23 seconds for that phase). All **133 pinned runtime distributions** exactly matched `requirements/requirements-runtime.txt`; the only additional Python distribution was the pip installer. The local development environment's 104 distributions also passed dependency compatibility checks.

`.gitignore` exclusions were checked for credentials, databases, raw/processed data, model folders, alternate environments and generated reports. The Docker build context uses a separate allowlist to keep private runtime files out of the image.

## Supported route and remaining limits

The published image supports CPU text chat, retrieval, agents, saved plans and PDF exports. Users need their own LLM credentials and corpus provisioning as described in [DOCKER.md](DOCKER.md). The workout corpus and personal data are not bundled. Initial resources are a budget estimate, not a full-stack peak measurement. Full Coach/Designer/memory quality, native Windows/macOS/ARM installations and a fresh GPU speech installation are outside this verification.

The GPU evaluation runner is a user process on the laptop; it must be online with Qdrant and the model available. It does not automatically start after reboot/WSL shutdown. The image publication job runs on GitHub-hosted infrastructure. This is tested image delivery, not a hosted application deployment.


## Performance release verification — 23 October 2026

Source `7d09f5cd6ad156ad7f136fe37b97a1cf9b625fc7` passed [automatic CI/CD run 39881688307](https://github.com/bmaged23/Fitness_multiagent_RAG/actions/runs/39881688307): 132 offline tests, all 100 fresh source-based RAG evaluations, CPU/GPU embedding benchmark, quality gate, image build, container smoke tests, publication and published-image pull/retest.

All metrics have 100 valid scores: nDCG@5 0.7179, recall@5 82%, correctness F1 81.50%, completeness 80.20%, relevance 90%, faithfulness 99%, unsupported claims 1%. [Full aggregate evidence](performance/release-evaluation-7d09f5c.json). The frozen baseline is unchanged.

The `cpu`, `latest` and `sha-7d09f5cd6ad156ad7f136fe37b97a1cf9b625fc7` tags all published digest `sha256:607ea87c7098638bd0f1227b848d0574bb413842cabf7cf69f4703e50662fc8b`. The digest is unchanged because application image inputs were unchanged; performance tooling, workflow checks and documentation were added. This is a successful automatic publication, not a missed update.

[Performance measurements](PERFORMANCE.md) compare CPU/GPU embeddings and five real containerized Coach requests. Embedding median was 260.25 ms CPU versus 18.27 ms GPU; the separate five-request CPU Coach benchmark had 3.30 s median backend completion and about 1.71 GiB peak process RAM. These are different measurement scopes. Speech was disabled; one known-record lookup miss is documented, so timing completion is not an accuracy pass. The 100-case quality evaluation runs outside Docker; container smoke checks run inside the built image.

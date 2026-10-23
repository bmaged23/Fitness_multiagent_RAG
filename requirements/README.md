# Dependency files

For normal installation, run `python -m pip install -r requirements.txt` from the repository root. It includes the exact CPU runtime lock below.

| Files | Purpose |
|---|---|
| `requirements-runtime.in` / `.txt` | Direct runtime dependencies / exact resolved CPU application dependencies used by Docker and the default install. |
| `requirements-dev.in` / `.txt` | Direct development dependencies / exact smaller offline-test environment used by CI. Install with `python -m pip install -r requirements/requirements-dev.txt`. |
| `requirements-core.in` / `.txt` | Direct shared text/PDF dependencies / resolved subset used to maintain the dependency sets. Not a complete embedding installation. |
| `requirements-speech.txt` | Optional speech dependencies; requires the source GPU setup described in the main README. |
| `requirements-data.txt` | Pinned dataset-download dependencies included when maintaining the runtime input. |
| `requirements-pdf.txt` | Supplemental PDF export/testing dependencies for minimal environments; included in normal runtime/development sets. |

The `.in` files are maintainer inputs; `.txt` files provide pinned installs. Users do not need to install every file. Paths inside dependency files resolve relative to their containing file. The historical GPU demo snapshot under `docs/reference/` is not the default installation.

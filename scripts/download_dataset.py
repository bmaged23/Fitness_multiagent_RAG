"""
Download the 600K Fitness Exercise & Workout Program Dataset from Kaggle.

Usage:
    python scripts/download_dataset.py

Requires:
    - kaggle Python package installed  (pip install kaggle)
    - ~/.kaggle/kaggle.json with valid credentials, OR
      KAGGLE_USERNAME and KAGGLE_KEY environment variables set

Outputs:
    data/raw/fitness_exercises.csv   (~605 K rows)
    data/raw/program_summary.csv     (~2 598 rows)
"""

import sys
import zipfile
import logging
from pathlib import Path

# Allow running as a top-level script without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import (
    DATA_RAW_DIR,
    KAGGLE_DATASET_SLUG,
    EXERCISES_CSV,
    PROGRAMS_CSV,
    EXERCISES_MIN_ROWS,
    PROGRAMS_MIN_ROWS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

EXPECTED_FILES = {
    EXERCISES_CSV.name: EXERCISES_MIN_ROWS,
    PROGRAMS_CSV.name: PROGRAMS_MIN_ROWS,
}


def _check_kaggle_credentials() -> None:
    """Fail fast with a clear message if credentials are missing."""
    import os

    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    has_json = kaggle_json.exists()
    has_env = os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY")

    if not has_json and not has_env:
        raise EnvironmentError(
            "Kaggle credentials not found.\n"
            "Either place your API token at ~/.kaggle/kaggle.json  (chmod 600),\n"
            "or export KAGGLE_USERNAME and KAGGLE_KEY environment variables.\n"
            "Get a token at: https://www.kaggle.com/settings → API → Create New Token"
        )

    if has_json:
        log.info("Kaggle credentials: ~/.kaggle/kaggle.json found")
    else:
        log.info("Kaggle credentials: KAGGLE_USERNAME / KAGGLE_KEY env vars found")


def _download(dest_dir: Path) -> Path:
    """Call the Kaggle API to download and return the path of the zip file."""
    try:
        import kaggle
    except ImportError:
        raise ImportError(
            "kaggle package not installed. Run: pip install kaggle"
        )

    kaggle.api.authenticate()

    log.info("Downloading dataset '%s' …", KAGGLE_DATASET_SLUG)
    kaggle.api.dataset_download_files(
        KAGGLE_DATASET_SLUG,
        path=str(dest_dir),
        unzip=False,   # we handle unzip ourselves so we can log progress
        quiet=False,
    )

    # kaggle saves as <dataset-name>.zip
    dataset_name = KAGGLE_DATASET_SLUG.split("/")[-1]
    zip_path = dest_dir / f"{dataset_name}.zip"
    if not zip_path.exists():
        # Some versions drop a differently-named zip; find the first one
        zips = list(dest_dir.glob("*.zip"))
        if not zips:
            raise FileNotFoundError(
                f"Download appeared to succeed but no .zip found in {dest_dir}"
            )
        zip_path = zips[0]

    log.info("Downloaded to: %s  (%.1f MB)", zip_path, zip_path.stat().st_size / 1e6)
    return zip_path


def _unzip(zip_path: Path, dest_dir: Path) -> None:
    log.info("Extracting %s …", zip_path.name)
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.namelist()
        log.info("Archive contents: %s", members)
        zf.extractall(dest_dir)
    log.info("Extraction complete → %s", dest_dir)


def _verify(dest_dir: Path) -> bool:
    """
    Check that every expected CSV is present and has at least the minimum
    expected row count (counting newlines is fast; no need to load into pandas).
    """
    all_ok = True

    for filename, min_rows in EXPECTED_FILES.items():
        csv_path = dest_dir / filename
        if not csv_path.exists():
            log.error("MISSING: %s", csv_path)
            all_ok = False
            continue

        # Count lines (header + data rows) without loading the whole file
        with open(csv_path, "rb") as f:
            line_count = sum(1 for _ in f)

        data_rows = line_count - 1  # subtract header
        size_mb = csv_path.stat().st_size / 1e6

        if data_rows < min_rows:
            log.error(
                "ROW COUNT TOO LOW: %s has %d rows (expected ≥ %d)",
                filename, data_rows, min_rows,
            )
            all_ok = False
        else:
            log.info(
                "OK  %-35s  %9d rows  %.1f MB",
                filename, data_rows, size_mb,
            )

    return all_ok


def main() -> None:
    DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Skip download if both files already exist and pass verification
    if EXERCISES_CSV.exists() and PROGRAMS_CSV.exists():
        log.info("Both CSVs already present — running verification only.")
        ok = _verify(DATA_RAW_DIR)
        if ok:
            log.info("Dataset is ready. Nothing to do.")
            return
        log.warning("Verification failed on existing files — re-downloading.")

    _check_kaggle_credentials()
    zip_path = _download(DATA_RAW_DIR)
    _unzip(zip_path, DATA_RAW_DIR)

    # Clean up the zip to save space
    zip_path.unlink()
    log.info("Removed zip file to save space.")

    ok = _verify(DATA_RAW_DIR)
    if not ok:
        log.error("Dataset verification failed. Check the errors above.")
        sys.exit(1)

    log.info("Dataset downloaded and verified successfully.")
    log.info("Next step: python scripts/inspect_schema.py")


if __name__ == "__main__":
    main()


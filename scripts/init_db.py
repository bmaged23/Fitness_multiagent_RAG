import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import SQLITE_DB_PATH

SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"

EXPECTED_TABLES = {
    "trainees",
    "trainee_auth",
    "plans",
    "plan_revisions",
    "progress_logs",
    "coach_memory",
    "nutrition_plans",
    "nutrition_plan_revisions",
}


_TRAINEE_NEW_COLS = [
    ("email",        "TEXT"),
    ("phone",        "TEXT"),
    ("height_cm",    "REAL"),
    ("weight_kg",    "REAL"),
    ("body_fat_pct", "REAL"),
    ("muscle_pct",   "REAL"),
    ("images_dir",   "TEXT"),
]

_TRAINEE_DROP_COLS = {"username", "password_hash"}  # moved to trainee_auth


def _migrate(conn: sqlite3.Connection) -> None:
    """Migrate trainees table: add new profile columns, create trainee_auth if missing."""
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(trainees)").fetchall()
    }
    for col_name, col_def in _TRAINEE_NEW_COLS:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE trainees ADD COLUMN {col_name} {col_def}")
            print(f"  migrated: added column trainees.{col_name}")
    # Note: SQLite does not support DROP COLUMN in older versions.
    # username/password_hash columns left in place if they exist from a prior schema
    # version — they are ignored by all code (trainee_auth is authoritative).


def init_db() -> None:
    SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    sql = SCHEMA_PATH.read_text() + "\n" + SCHEMA_PATH.with_name("nutrition_schema.sql").read_text()

    with sqlite3.connect(SQLITE_DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(sql)
        _migrate(conn)

    print(f"Database initialised: {SQLITE_DB_PATH}")

    with sqlite3.connect(SQLITE_DB_PATH) as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cur.fetchall()}

    missing = EXPECTED_TABLES - tables
    if missing:
        raise RuntimeError(f"Schema incomplete — missing tables: {missing}")

    print(f"Tables: {', '.join(sorted(tables))}")


if __name__ == "__main__":
    init_db()

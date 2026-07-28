import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import SQLITE_DB_PATH

SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"

EXPECTED_TABLES = {
    "trainees",
    "plans",
    "plan_revisions",
    "progress_logs",
    "coach_memory",
}


def init_db() -> None:
    SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    sql = SCHEMA_PATH.read_text()

    with sqlite3.connect(SQLITE_DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(sql)

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

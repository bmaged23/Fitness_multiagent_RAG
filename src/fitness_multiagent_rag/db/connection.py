from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from config.settings import SQLITE_DB_PATH


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Yield a connection with an active transaction. Commits on clean exit, rolls back on exception."""
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_db_ro() -> Generator[sqlite3.Connection, None, None]:
    """Yield a read-only connection (no commit, no rollback)."""
    conn = _get_conn()
    try:
        yield conn
    finally:
        conn.close()

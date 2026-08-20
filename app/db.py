"""SQLite persistence layer. stdlib sqlite3 — no ORM needed at this scale."""
import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "shortener.db"

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
    code        TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT
);
"""


def get_conn() -> sqlite3.Connection:
    # ponytail: one connection per thread; connection pool if this ever fronts real traffic
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


def init_db() -> None:
    get_conn().executescript(SCHEMA)


def insert_link(code: str, url: str, expires_at: str | None) -> bool:
    """Returns False on code collision."""
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO links (code, url, expires_at) VALUES (?, ?, ?)",
                (code, url, expires_at),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def get_link(code: str) -> sqlite3.Row | None:
    return get_conn().execute(
        "SELECT * FROM links WHERE code = ?", (code,)
    ).fetchone()


def delete_link(code: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM links WHERE code = ?", (code,))
    return cur.rowcount > 0

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

CREATE TABLE IF NOT EXISTS clicks (
    id        INTEGER PRIMARY KEY,
    code      TEXT NOT NULL REFERENCES links(code) ON DELETE CASCADE,
    ts        TEXT NOT NULL DEFAULT (datetime('now')),
    referrer  TEXT
);
CREATE INDEX IF NOT EXISTS idx_clicks_code_ts ON clicks(code, ts);
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


def record_click(code: str, referrer: str | None) -> None:
    # ponytail: synchronous insert on redirect path; queue/batch if redirect latency matters
    with get_conn() as conn:
        conn.execute("INSERT INTO clicks (code, referrer) VALUES (?, ?)", (code, referrer))


def link_stats(code: str) -> dict:
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(*) FROM clicks WHERE code = ?", (code,)
    ).fetchone()[0]
    by_day = conn.execute(
        """SELECT date(ts) AS day, COUNT(*) AS clicks FROM clicks
           WHERE code = ? AND ts >= datetime('now', '-7 days')
           GROUP BY day ORDER BY day""",
        (code,),
    ).fetchall()
    referrers = conn.execute(
        """SELECT COALESCE(referrer, '(direct)') AS referrer, COUNT(*) AS clicks
           FROM clicks WHERE code = ? GROUP BY referrer ORDER BY clicks DESC LIMIT 10""",
        (code,),
    ).fetchall()
    return {
        "total_clicks": total,
        "last_7_days": [dict(r) for r in by_day],
        "top_referrers": [dict(r) for r in referrers],
    }


def delete_link(code: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM links WHERE code = ?", (code,))
    return cur.rowcount > 0

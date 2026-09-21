"""
Server-side history storage for Anchor Elite AI.

Replaces the old localStorage-only history (which lived entirely in the
browser, didn't survive a cleared cache/different device, truncated code to
120 chars even for the "restore" action, and for Analyze was saved BEFORE
the result existed so it never recorded a score) with a small SQLite
database on the server.

This is a single-user local tool with no login system, so history is global
per server instance — that's a deliberate scope choice, not an oversight;
adding per-user history would require an auth layer this project doesn't have.
"""
import sqlite3
import logging
import threading
from pathlib import Path
from contextlib import contextmanager

log = logging.getLogger("anchor_elite.history_db")

DB_PATH = Path(__file__).parent / "history.db"
_lock = threading.Lock()  # sqlite3 connections aren't thread-safe to share

MAX_ENTRIES_PER_KIND = 200  # hard cap so the db can't grow unbounded


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _lock, _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analyze_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                lang TEXT NOT NULL,
                score INTEGER,
                corrected_code TEXT,
                verified INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assistant_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt TEXT NOT NULL,
                code TEXT,
                result TEXT,
                model TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
    log.info(f"History DB ready at {DB_PATH}")


def save_analyze(code: str, lang: str, score: int, corrected_code: str, verified: bool):
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO analyze_history (code, lang, score, corrected_code, verified) VALUES (?,?,?,?,?)",
            (code, lang, score, corrected_code, int(bool(verified)))
        )
        _trim(conn, "analyze_history")


def save_assistant(prompt: str, code: str, result: str, model: str):
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO assistant_history (prompt, code, result, model) VALUES (?,?,?,?)",
            (prompt, code, result, model)
        )
        _trim(conn, "assistant_history")


def _trim(conn, table):
    """Keep only the most recent MAX_ENTRIES_PER_KIND rows."""
    conn.execute(f"""
        DELETE FROM {table} WHERE id NOT IN (
            SELECT id FROM {table} ORDER BY id DESC LIMIT ?
        )
    """, (MAX_ENTRIES_PER_KIND,))


def get_analyze_history(limit: int = 20) -> list:
    with _lock, _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM analyze_history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_assistant_history(limit: int = 20) -> list:
    with _lock, _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM assistant_history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def delete_entry(kind: str, entry_id: int):
    table = "analyze_history" if kind == "analyze" else "assistant_history"
    with _lock, _conn() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (entry_id,))


def clear_history(kind: str):
    table = "analyze_history" if kind == "analyze" else "assistant_history"
    with _lock, _conn() as conn:
        conn.execute(f"DELETE FROM {table}")
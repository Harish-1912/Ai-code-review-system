"""
learning.py — Anchor Elite's "learn from my corrections" memory.

How it works (no model retraining needed):
  1. You paste the ORIGINAL buggy code + a CORRECT version you got elsewhere.
  2. The pair is validated (the corrected code must parse and actually run),
     then stored in learned.db.
  3. Next time similar code is analysed:
       - SAME code seen before  -> your stored fix is used directly (and re-run to check it).
       - SIMILAR code           -> your past fixes are shown to the AI as worked examples.
Similarity ignores variable names, so `def add(x, g=[])` matches `def push(item, buf=[])`.
"""
import re, os, hmac, sqlite3, threading, logging, hashlib, keyword
from pathlib import Path
from contextlib import contextmanager

log = logging.getLogger("anchor_elite.learning")

DB_PATH = Path(__file__).parent / "learned.db"
MAX_ENTRIES = 500
_lock = threading.Lock()
_ready = False

_KEYWORDS = set(keyword.kwlist) | {
    "function", "const", "let", "var", "public", "private", "static", "void", "int",
    "new", "null", "this", "String", "await", "async", "try", "catch", "throws",
    "self", "print", "len", "range", "open", "return",
}
_TOK = re.compile(
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_]\w*|\d+(?:\.\d+)?'
    r'|==|!=|<=|>=|\*\*|//|\+=|-=|->|[^\s\w]'
)


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init():
    global _ready
    if _ready:
        return
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lang TEXT NOT NULL,
                buggy_hash TEXT NOT NULL,
                buggy_code TEXT NOT NULL,
                fixed_code TEXT NOT NULL,
                uses INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lang_hash ON corrections(lang, buggy_hash)")
        c.execute("CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    _ready = True


def _norm(code: str) -> str:
    return re.sub(r"\s+", " ", code.strip())


def _hash(code: str) -> str:
    return hashlib.sha1(_norm(code).encode("utf-8")).hexdigest()


def _tokens(code: str):
    return _TOK.findall(code)


def _shape(tokens):
    """Replace names/numbers/strings with placeholders so renamed variables still match."""
    out = []
    for t in tokens:
        if t[0] in "\"'":
            out.append("STR")
        elif t[0].isdigit():
            out.append("NUM")
        elif (t[0].isalpha() or t[0] == "_"):
            out.append(t if t in _KEYWORDS else "ID")
        else:
            out.append(t)
    return out


def _jaccard(a, b) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a and b else 0.0


def _bigrams(seq):
    return [(seq[i], seq[i + 1]) for i in range(len(seq) - 1)]


def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    full = _jaccard(ta, tb)
    shape = _jaccard(_bigrams(_shape(ta)), _bigrams(_shape(tb)))
    return round(0.5 * full + 0.5 * shape, 3)


def save(lang: str, buggy: str, fixed: str) -> int:
    """Store (or update) a correction. Returns total number of stored corrections."""
    _init()
    h = _hash(buggy)
    with _lock, _conn() as c:
        row = c.execute("SELECT id FROM corrections WHERE lang=? AND buggy_hash=?", (lang, h)).fetchone()
        if row:
            c.execute("UPDATE corrections SET fixed_code=?, buggy_code=? WHERE id=?",
                      (fixed.strip(), buggy.strip(), row["id"]))
        else:
            c.execute("INSERT INTO corrections (lang, buggy_hash, buggy_code, fixed_code) VALUES (?,?,?,?)",
                      (lang, h, buggy.strip(), fixed.strip()))
        c.execute("DELETE FROM corrections WHERE id NOT IN "
                  "(SELECT id FROM corrections ORDER BY id DESC LIMIT ?)", (MAX_ENTRIES,))
        return c.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]


def find_similar(code: str, lang: str, limit: int = 2, min_score: float = 0.45) -> list:
    """Best matches first. 'exact' is True when it is the same code (ignoring whitespace)."""
    _init()
    h = _hash(code)
    with _lock, _conn() as c:
        rows = c.execute("SELECT id, buggy_hash, buggy_code, fixed_code FROM corrections WHERE lang=?",
                         (lang,)).fetchall()
    scored = []
    for r in rows:
        exact = r["buggy_hash"] == h
        score = 1.0 if exact else similarity(code, r["buggy_code"])
        if exact or score >= min_score:
            scored.append({"id": r["id"], "score": score, "exact": exact,
                           "buggy": r["buggy_code"], "fixed": r["fixed_code"]})
    scored.sort(key=lambda d: d["score"], reverse=True)
    return scored[:limit]


def mark_used(entry_id: int):
    _init()
    with _lock, _conn() as c:
        c.execute("UPDATE corrections SET uses = uses + 1 WHERE id=?", (entry_id,))


def count() -> int:
    _init()
    with _lock, _conn() as c:
        return c.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]


def list_all(limit: int = 50) -> list:
    _init()
    with _lock, _conn() as c:
        rows = c.execute("SELECT id, lang, buggy_code, fixed_code, uses, created_at "
                         "FROM corrections ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def delete(entry_id: int):
    _init()
    with _lock, _conn() as c:
        c.execute("DELETE FROM corrections WHERE id=?", (entry_id,))


# ── Admin key chosen on the web page (first key entered becomes THE key) ─────
# Only a salted hash is stored, never the key itself.
def _hash_key(key: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, 200_000).hex()


def admin_key_is_set() -> bool:
    _init()
    with _lock, _conn() as c:
        return c.execute("SELECT 1 FROM settings WHERE k='admin_key'").fetchone() is not None


def set_admin_key(key: str) -> bool:
    """Saves the key ONLY if none exists yet. Returns False if one is already set."""
    _init()
    salt = os.urandom(16)
    value = salt.hex() + "$" + _hash_key(key, salt)
    with _lock, _conn() as c:
        cur = c.execute("INSERT OR IGNORE INTO settings (k, v) VALUES ('admin_key', ?)", (value,))
        return cur.rowcount == 1


def check_admin_key(key: str) -> bool:
    if not key:
        return False
    _init()
    with _lock, _conn() as c:
        row = c.execute("SELECT v FROM settings WHERE k='admin_key'").fetchone()
    if not row:
        return False
    salt_hex, stored = row["v"].split("$", 1)
    return hmac.compare_digest(_hash_key(key, bytes.fromhex(salt_hex)), stored)
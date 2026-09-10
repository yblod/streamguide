"""SQLite-Zugriff (eine Datei, WAL-Modus) und Schema-Migration."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

# Datenordner: im Home-Assistant-Add-on /data (persistent), sonst ./data neben der App.
DATA_DIR = Path(os.environ.get("STREAMGUIDE_DATA_DIR") or Path(__file__).resolve().parent.parent / "data").resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "streamguide.db"

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS providers (
    id               INTEGER PRIMARY KEY,
    name             TEXT NOT NULL,
    logo_path        TEXT,
    display_priority INTEGER DEFAULT 999,
    active           INTEGER DEFAULT 0,
    media_types      TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS genres (
    id         INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    name       TEXT NOT NULL,
    PRIMARY KEY (media_type, id)
);

CREATE TABLE IF NOT EXISTS titles (
    media_type        TEXT NOT NULL,
    tmdb_id           INTEGER NOT NULL,
    imdb_id           TEXT,
    title             TEXT,
    original_title    TEXT,
    year              INTEGER,
    overview          TEXT,
    poster_path       TEXT,
    backdrop_path     TEXT,
    genre_ids         TEXT DEFAULT '[]',
    runtime           INTEGER,
    origin_countries  TEXT DEFAULT '[]',
    certification     TEXT,
    tmdb_rating       REAL,
    tmdb_votes        INTEGER,
    popularity        REAL,
    status            TEXT,
    number_of_seasons INTEGER,
    seasons           TEXT,
    next_episode_air  TEXT,
    last_air_date     TEXT,
    providers         TEXT,
    providers_fetched_at TEXT,
    details_fetched_at   TEXT,
    updated_at        TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (media_type, tmdb_id)
);
CREATE INDEX IF NOT EXISTS idx_titles_imdb ON titles(imdb_id);

CREATE TABLE IF NOT EXISTS imdb_ratings (
    tconst TEXT PRIMARY KEY,
    rating REAL,
    votes  INTEGER
);

CREATE TABLE IF NOT EXISTS user_titles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    media_type      TEXT NOT NULL,
    tmdb_id         INTEGER NOT NULL,
    status          TEXT NOT NULL,          -- watchlist | watching | watched | disliked | dropped
    rating          INTEGER,                -- eigene Bewertung 1-10
    rated_at        TEXT,
    added_at        TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    source          TEXT,                   -- manual | imdb | tmdb | list
    watched_seasons TEXT DEFAULT '[]',
    new_season_flag INTEGER DEFAULT 0,
    notes           TEXT,
    UNIQUE (media_type, tmdb_id)
);

CREATE TABLE IF NOT EXISTS import_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT,
    source     TEXT,
    ref        TEXT,
    title      TEXT,
    result     TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS people (
    id                   INTEGER PRIMARY KEY,
    imdb_id              TEXT,
    name                 TEXT,
    profile_path         TEXT,
    known_for_department TEXT,
    birthday             TEXT,
    deathday             TEXT,
    place_of_birth       TEXT,
    biography            TEXT,
    popularity           REAL,
    gender               INTEGER,
    credits              TEXT,
    details_fetched_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_people_imdb ON people(imdb_id);

CREATE TABLE IF NOT EXISTS user_people (
    person_id INTEGER PRIMARY KEY,
    added_at  TEXT DEFAULT (datetime('now')),
    source    TEXT,
    notes     TEXT
);

CREATE TABLE IF NOT EXISTS blocked_people (
    person_id INTEGER PRIMARY KEY,
    added_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    kind        TEXT,
    status      TEXT,
    progress    INTEGER DEFAULT 0,
    total       INTEGER DEFAULT 0,
    message     TEXT,
    result      TEXT,
    started_at  TEXT DEFAULT (datetime('now')),
    finished_at TEXT
);
"""


def open_db(path: Path) -> sqlite3.Connection:
    """Öffnet eine StreamGuide-Datenbank, legt Schema an und migriert (auch für Kopien/Importe)."""
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def connect() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = open_db(DB_PATH)
        return _conn


def close() -> None:
    """Verbindung schließen (z. B. vor dem Austausch der Datenbankdatei)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            _conn.close()
            _conn = None


MIGRATIONS = (
    ("user_titles", "watched_episodes", "TEXT DEFAULT '{}'"),
    ("user_titles", "avail_mine", "INTEGER"),
    ("user_titles", "newly_available", "INTEGER DEFAULT 0"),
    ("user_titles", "new_kind", "TEXT"),
    ("titles", "last_ep_season", "INTEGER"),
    ("titles", "last_ep_number", "INTEGER"),
    ("titles", "original_language", "TEXT"),
    ("titles", "de_release", "INTEGER"),
    ("titles", "jw_offers", "TEXT"),
    ("titles", "jw_fetched_at", "TEXT"),
    ("titles", "cast", "TEXT"),
)


def _migrate(conn: sqlite3.Connection) -> None:
    for table, col, decl in MIGRATIONS:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    """Serialisierte Transaktion (ein Prozess, ein Nutzer)."""
    conn = connect()
    with _lock:
        conn.execute("BEGIN")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def query(sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    conn = connect()
    with _lock:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def query_one(sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple | list = ()) -> None:
    conn = connect()
    with _lock:
        conn.execute(sql, params)


def executemany(sql: str, rows: list[tuple]) -> None:
    conn = connect()
    with _lock:
        conn.execute("BEGIN")
        try:
            conn.executemany(sql, rows)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


# ---------- Settings (Key/Value) ----------

def get_setting(key: str, default: Any = None) -> Any:
    row = query_one("SELECT value FROM settings WHERE key=?", (key,))
    if row is None or row["value"] is None:
        return default
    try:
        return json.loads(row["value"])
    except (TypeError, ValueError):
        return row["value"]


def set_setting(key: str, value: Any) -> None:
    execute(
        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )


def all_settings() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for r in query("SELECT key, value FROM settings"):
        try:
            out[r["key"]] = json.loads(r["value"])
        except (TypeError, ValueError):
            out[r["key"]] = r["value"]
    return out


def loads(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default

"""SQLite-Zugriff (eine Datei, WAL-Modus) und Schema-Migration."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator

# Datenordner: im Home-Assistant-Add-on /data (persistent), sonst ./data neben der App.
DATA_DIR = Path(os.environ.get("STREAMGUIDE_DATA_DIR") or Path(__file__).resolve().parent.parent / "data").resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "streamguide.db"

_lock = threading.RLock()
_conns: dict[str, sqlite3.Connection] = {}

# ---------- Profile ----------
# Das Hauptprofil („main“) nutzt streamguide.db. Jedes weitere Profil hat eine eigene Datei unter profiles/<id>.db
# mit nur den Nutzertabellen; die Haupt-Datenbank ist dort als „cache“ angehängt, so dass Titel-Cache, IMDb-Datensatz,
# Anbieter, Personen und Jobs für alle Profile gemeinsam gelten (unqualifizierte Tabellennamen lösen SQLite zuerst im
# Profil, dann im angehängten Cache auf). Das aktive Profil steht je Anfrage in der Kontextvariable PROFILE.
PROFILE: ContextVar[str] = ContextVar("sg_profile", default="main")
PROFILES_DIR = DATA_DIR / "profiles"
PROFILE_TABLES = ("settings", "user_titles", "import_log", "user_people", "blocked_people")
# Einstellungen, die für alle Profile gelten (liegen immer in der Haupt-Datenbank)
SHARED_KEYS = frozenset({"tmdb_api_key", "extra_regions", "count_all_free", "imdb_dataset_updated", "profiles",
                         "main_name", "main_pin"})
_profile_ids_cache: set[str] | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS providers (
    id               INTEGER NOT NULL,
    region           TEXT NOT NULL DEFAULT 'DE',   -- Land des Angebots (DE oder ein VPN-Zusatzland wie GB)
    name             TEXT NOT NULL,
    logo_path        TEXT,
    display_priority INTEGER DEFAULT 999,
    active           INTEGER DEFAULT 0,
    media_types      TEXT DEFAULT '[]',
    PRIMARY KEY (id, region)
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


def _schema_for(tables: tuple[str, ...]) -> str:
    out = []
    for stmt in SCHEMA.split(";"):
        st = stmt.strip()
        if not st:
            continue
        m = re.search(r"TABLE IF NOT EXISTS (\w+)", st) or re.search(r"INDEX IF NOT EXISTS \w+ ON (\w+)", st)
        if m and m.group(1) in tables:
            out.append(st + ";")
    return "\n".join(out)


PROFILE_SCHEMA = _schema_for(PROFILE_TABLES)


def open_profile_db(path: Path) -> sqlite3.Connection:
    """Profil-Datenbank (nur Nutzertabellen) öffnen und die Haupt-Datenbank als Cache anhängen."""
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(PROFILE_SCHEMA)
    _migrate(conn)
    conn.execute("ATTACH DATABASE ? AS cache", (str(DB_PATH),))
    return conn


def _main_conn() -> sqlite3.Connection:
    with _lock:
        c = _conns.get("main")
        if c is None:
            c = _conns["main"] = open_db(DB_PATH)
        return c


def _main_setting(key: str, default: Any = None) -> Any:
    conn = _main_conn()
    with _lock:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None or row[0] is None:
        return default
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return row[0]


def profiles() -> list[dict[str, Any]]:
    """Alle Profile; das Hauptprofil steht immer vorn. max_age = Altersgrenze (None = keine)."""
    out: list[dict[str, Any]] = [{"id": "main", "name": _main_setting("main_name") or "Ich", "max_age": None}]
    for raw in _main_setting("profiles", []) or []:
        pid = str((raw or {}).get("id") or "").strip().lower()
        if pid and pid != "main" and re.fullmatch(r"[a-z0-9_-]{1,32}", pid):
            age = raw.get("max_age")
            out.append({"id": pid, "name": raw.get("name") or pid, "max_age": int(age) if age not in (None, "") else None})
    return out


def profile_ids() -> set[str]:
    global _profile_ids_cache
    if _profile_ids_cache is None:
        _profile_ids_cache = {p["id"] for p in profiles()}
    return _profile_ids_cache


def profile_id() -> str:
    pid = PROFILE.get() or "main"
    return pid if pid in profile_ids() else "main"


def current_profile() -> dict[str, Any]:
    pid = profile_id()
    for p in profiles():
        if p["id"] == pid:
            return p
    return profiles()[0]


def max_age() -> int | None:
    """Altersgrenze des aktiven Profils (None = unbeschränkt)."""
    return current_profile().get("max_age")


def connect() -> sqlite3.Connection:
    """Verbindung des aktiven Profils (Hauptprofil: Haupt-Datenbank)."""
    pid = profile_id()
    if pid == "main":
        return _main_conn()
    with _lock:
        c = _conns.get(pid)
        if c is None:
            _main_conn()
            PROFILES_DIR.mkdir(parents=True, exist_ok=True)
            c = _conns[pid] = open_profile_db(PROFILES_DIR / f"{pid}.db")
        return c


def close() -> None:
    """Alle Verbindungen schließen (z. B. vor dem Austausch der Datenbankdateien); Profile zuerst (sie hängen am Cache)."""
    with _lock:
        for pid in sorted(_conns, key=lambda k: k == "main"):
            c = _conns.pop(pid)
            try:
                c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                pass
            c.close()


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
        if cols and col not in cols:  # Tabelle fehlt in Profil-Datenbanken → nichts zu tun
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    _migrate_providers_region(conn)


def _migrate_providers_region(conn: sqlite3.Connection) -> None:
    """providers: Primärschlüssel (id) -> (id, region), bestehende Zeilen gelten als DE."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(providers)").fetchall()}
    if not cols or "region" in cols:
        return
    conn.executescript("""
        CREATE TABLE providers_new (
            id INTEGER NOT NULL, region TEXT NOT NULL DEFAULT 'DE', name TEXT NOT NULL, logo_path TEXT,
            display_priority INTEGER DEFAULT 999, active INTEGER DEFAULT 0, media_types TEXT DEFAULT '[]',
            PRIMARY KEY (id, region)
        );
        INSERT INTO providers_new(id, region, name, logo_path, display_priority, active, media_types)
            SELECT id, 'DE', name, logo_path, display_priority, active, media_types FROM providers;
        DROP TABLE providers;
        ALTER TABLE providers_new RENAME TO providers;
    """)


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

def _settings_conn(key: str) -> sqlite3.Connection:
    """Gemeinsame Einstellungen liegen in der Haupt-Datenbank, alle anderen im Profil."""
    return _main_conn() if key in SHARED_KEYS else connect()


def get_setting(key: str, default: Any = None) -> Any:
    conn = _settings_conn(key)
    with _lock:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None or row[0] is None:
        return default
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return row[0]


def set_setting(key: str, value: Any) -> None:
    global _profile_ids_cache
    conn = _settings_conn(key)
    with _lock:
        conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (key, json.dumps(value)))
    if key == "profiles":
        _profile_ids_cache = None


def all_settings() -> dict[str, Any]:
    """Einstellungen des aktiven Profils, ergänzt um die gemeinsamen aus der Haupt-Datenbank."""
    out: dict[str, Any] = {}
    for conn, only_shared in ((_main_conn(), profile_id() != "main"), (connect(), False)):
        with _lock:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        for r in rows:
            if only_shared and r[0] not in SHARED_KEYS:
                continue
            try:
                out[r[0]] = json.loads(r[1])
            except (TypeError, ValueError):
                out[r[0]] = r[1]
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

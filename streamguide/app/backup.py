"""Sicherung und Wiederherstellung: ZIP mit der SQLite-Datenbank (ohne den großen IMDb-Datensatz)."""
from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from . import db

DB_NAME = "streamguide.db"
MANIFEST = "manifest.json"
# Tabellen, die nicht in die Sicherung gehören (werden neu aufgebaut bzw. sind Laufzeitdaten).
SKIP_TABLES = ("imdb_ratings", "jobs")


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in ("user_titles", "titles", "people", "user_people", "blocked_people", "providers", "settings"):
        try:
            out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.Error:
            out[t] = 0
    return out


def export_from_connection(src: sqlite3.Connection, dest_zip: Path, version: str = "dev") -> dict[str, Any]:
    """Kopiert die Datenbank über die Backup-API, entfernt große/flüchtige Tabellen und packt sie als ZIP."""
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sg-export-") as tmp:
        copy = Path(tmp) / DB_NAME
        dst = sqlite3.connect(copy, isolation_level=None)  # Autocommit, sonst scheitert VACUUM
        try:
            src.backup(dst)
            dst.execute("PRAGMA journal_mode=DELETE")
            for t in SKIP_TABLES:
                dst.execute(f"DELETE FROM {t}")
            dst.execute("VACUUM")
            counts = _counts(dst)
        finally:
            dst.close()
        manifest = {"app": "streamguide", "format": 1, "version": version,
                    "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "counts": counts}
        with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.write(copy, DB_NAME)
            z.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
    manifest["size"] = dest_zip.stat().st_size
    return manifest


def export_live(dest_zip: Path, version: str = "dev") -> dict[str, Any]:
    """Sicherung der laufenden App-Datenbank."""
    conn = db.connect()
    with db._lock:
        return export_from_connection(conn, dest_zip, version)


def export_file(db_path: Path, dest_zip: Path, version: str = "dev") -> dict[str, Any]:
    """Sicherung aus einer beliebigen Datenbankdatei (z. B. der PC-Version).

    Die Quelle wird vorher samt WAL/SHM in ein Temp-Verzeichnis kopiert und nur die Kopie geöffnet,
    damit an der Originaldatei nichts verändert wird.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    with tempfile.TemporaryDirectory(prefix="sg-src-") as tmp:
        work = Path(tmp) / DB_NAME
        shutil.copy2(db_path, work)
        for suffix in ("-wal", "-shm"):
            side = db_path.with_name(db_path.name + suffix)
            if side.exists():
                shutil.copy2(side, work.with_name(work.name + suffix))
        conn = sqlite3.connect(work, isolation_level=None)
        try:
            return export_from_connection(conn, dest_zip, version)
        finally:
            conn.close()


def inspect_zip(zip_path: Path) -> dict[str, Any]:
    """Prüft eine Sicherung und liefert das Manifest (wirft ValueError bei ungültigen Dateien)."""
    if not zipfile.is_zipfile(zip_path):
        raise ValueError("Keine ZIP-Datei.")
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
        if DB_NAME not in names:
            raise ValueError(f"In der ZIP fehlt {DB_NAME}.")
        manifest = json.loads(z.read(MANIFEST)) if MANIFEST in names else {}
    if manifest and manifest.get("app") != "streamguide":
        raise ValueError("Das ist keine StreamGuide-Sicherung.")
    return manifest


def restore(zip_path: Path) -> dict[str, Any]:
    """Ersetzt die laufende Datenbank durch die aus der ZIP.

    Der IMDb-Datensatz (imdb_ratings) wird aus der bisherigen Datenbank übernommen, damit er nicht neu
    geladen werden muss. Die bisherige Datenbank bleibt als .bak-Datei erhalten.
    """
    manifest = inspect_zip(zip_path)
    with tempfile.TemporaryDirectory(prefix="sg-restore-") as tmp:
        new_db = Path(tmp) / DB_NAME
        with zipfile.ZipFile(zip_path) as z:
            with z.open(DB_NAME) as src, open(new_db, "wb") as dst:
                shutil.copyfileobj(src, dst)
        # Integrität und Schema der neuen Datei prüfen (legt fehlende Tabellen/Spalten an).
        check = db.open_db(new_db)
        try:
            ok = check.execute("PRAGMA integrity_check").fetchone()[0]
            if ok != "ok":
                raise ValueError(f"Datenbank beschädigt: {ok}")
            counts = _counts(check)
        finally:
            check.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            check.close()

        with db._lock:
            db.close()
            stamp = time.strftime("%Y%m%d-%H%M%S")
            backup_path = db.DB_PATH.with_name(f"{DB_NAME}.bak-{stamp}")
            had_old = db.DB_PATH.exists()
            if had_old:
                shutil.move(db.DB_PATH, backup_path)
            for suffix in ("-wal", "-shm"):
                side = db.DB_PATH.with_name(db.DB_PATH.name + suffix)
                if side.exists():
                    side.unlink()
            shutil.copy2(new_db, db.DB_PATH)
            conn = db.connect()
            ratings = 0
            if had_old:
                conn.execute("ATTACH DATABASE ? AS old", (str(backup_path),))
                try:
                    conn.execute("INSERT OR REPLACE INTO imdb_ratings SELECT * FROM old.imdb_ratings")
                    ratings = conn.execute("SELECT COUNT(*) FROM imdb_ratings").fetchone()[0]
                    row = conn.execute("SELECT value FROM old.settings WHERE key='imdb_dataset_updated'").fetchone()
                    if row and row[0]:
                        conn.execute("INSERT INTO settings(key,value) VALUES('imdb_dataset_updated',?) "
                                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (row[0],))
                finally:
                    conn.execute("DETACH DATABASE old")
            _prune_backups(db.DB_PATH.parent, keep=3)
    return {"manifest": manifest, "counts": counts, "imdb_ratings_kept": ratings}


def _prune_backups(folder: Path, keep: int) -> None:
    baks = sorted(folder.glob(f"{DB_NAME}.bak-*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in baks[keep:]:
        try:
            p.unlink()
        except OSError:
            pass

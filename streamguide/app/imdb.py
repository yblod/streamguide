"""IMDb: offizieller Bewertungs-Datensatz (title.ratings.tsv.gz) und CSV-Exporte des Nutzers."""
from __future__ import annotations

import csv
import gzip
import io
from datetime import datetime
from typing import Any

import httpx

from . import db

RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"

TYPE_MAP = {
    "movie": "movie", "tvmovie": "movie", "video": "movie", "short": "movie", "tvshort": "movie",
    "tvspecial": "movie", "tv movie": "movie", "tv special": "movie", "tv short": "movie",
    "tvseries": "tv", "tvminiseries": "tv", "tv series": "tv", "tv mini series": "tv", "tv mini-series": "tv",
    "podcastseries": None, "tvepisode": None, "tv episode": None, "videogame": None, "video game": None,
}


def _norm_key(k: str) -> str:
    return k.strip().lstrip("﻿").lower()


def map_title_type(t: str | None) -> str | None:
    if not t:
        return "movie"
    key = t.strip().lower()
    if key in TYPE_MAP:
        return TYPE_MAP[key]
    if "episode" in key or "game" in key or "podcast" in key:
        return None
    if "series" in key:
        return "tv"
    return "movie"


def parse_export(content: bytes) -> list[dict[str, Any]]:
    """IMDb-CSV (Ratings- oder Watchlist-Export) in Zeilen mit einheitlichen Feldern umwandeln."""
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    for raw in reader:
        r = {_norm_key(k): (v or "").strip() for k, v in raw.items() if k is not None}
        const = r.get("const") or r.get("tconst") or ""
        if not const.startswith("tt"):
            continue
        rating_s = r.get("your rating") or ""
        year_s = r.get("year") or ""
        rows.append({
            "imdb_id": const,
            "title": r.get("title") or r.get("original title") or const,
            "title_type": r.get("title type") or "",
            "media_type": map_title_type(r.get("title type")),
            "rating": int(float(rating_s)) if rating_s.replace(".", "", 1).isdigit() else None,
            "rated_at": _date(r.get("date rated") or ""),
            "created_at": _date(r.get("created") or ""),
            "year": int(year_s[:4]) if year_s[:4].isdigit() else None,
        })
    return rows


def parse_people_export(content: bytes) -> list[dict[str, Any]]:
    """IMDb-Listen-Export mit Personen (Const = nm…)."""
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    for raw in reader:
        r = {_norm_key(k): (v or "").strip() for k, v in raw.items() if k is not None}
        const = r.get("const") or ""
        if not const.startswith("nm"):
            continue
        rows.append({"imdb_id": const, "name": r.get("name") or const, "known_for": r.get("known for") or ""})
    return rows


def _date(s: str) -> str | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return s[:10]


def download_ratings_dataset(progress=None) -> int:
    """Lädt title.ratings.tsv.gz und ersetzt die lokale Tabelle. Gibt Zeilenanzahl zurück (blockierend)."""
    with httpx.Client(timeout=120.0, follow_redirects=True) as c:
        with c.stream("GET", RATINGS_URL) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or 0)
            buf = io.BytesIO()
            got = 0
            for chunk in r.iter_bytes(1 << 16):
                buf.write(chunk)
                got += len(chunk)
                if progress and total:
                    progress(got, total, "IMDb-Datensatz wird geladen …")
    buf.seek(0)
    conn = db.connect()
    rows: list[tuple[str, float, int]] = []
    count = 0
    with db._lock:
        conn.execute("BEGIN")
        try:
            conn.execute("DELETE FROM imdb_ratings")
            with gzip.open(buf, mode="rt", encoding="utf-8") as fh:
                header = fh.readline()  # tconst averageRating numVotes
                assert header.startswith("tconst")
                for line in fh:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 3:
                        continue
                    try:
                        rows.append((parts[0], float(parts[1]), int(parts[2])))
                    except ValueError:
                        continue
                    if len(rows) >= 20000:
                        conn.executemany("INSERT INTO imdb_ratings(tconst,rating,votes) VALUES(?,?,?)", rows)
                        count += len(rows)
                        rows.clear()
                        if progress:
                            progress(count, 0, f"IMDb-Bewertungen werden importiert … {count:,}")
            if rows:
                conn.executemany("INSERT INTO imdb_ratings(tconst,rating,votes) VALUES(?,?,?)", rows)
                count += len(rows)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    db.set_setting("imdb_dataset_updated", datetime.utcnow().replace(microsecond=0).isoformat())
    return count

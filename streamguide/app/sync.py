"""Synchronisation und Importe: Anbieter/Genres, IMDb-CSV, TMDB-Konto, Titellisten, Serien-Check."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import timedelta
from typing import Any

from . import db, imdb, justwatch, library, people, titles, tmdb
from .jobs import Job

DEFAULT_ACTIVE_NAMES = ("netflix", "amazon prime video", "ard", "zdf", "arte", "3sat")
DEFAULT_ACTIVE_IDS = {350}  # Apple TV+ (Abo, nicht der Kauf-/Leih-Store "Apple TV")
DEFAULT_EXCLUDE = ("channel", "plus", "kids", "herzkino")  # kostenpflichtige Zusatzkanäle nicht vorbelegen


# ---------- Stammdaten ----------

async def seed_providers(force: bool = False) -> int:
    existing = {r["id"]: r for r in db.query("SELECT * FROM providers")}
    if existing and not force:
        return len(existing)
    movie = await tmdb.watch_providers("movie")
    tv = await tmdb.watch_providers("tv")
    merged: dict[int, dict[str, Any]] = {}
    for kind, lst in (("movie", movie), ("tv", tv)):
        for p in lst:
            pid = p["provider_id"]
            m = merged.setdefault(pid, {
                "id": pid, "name": p["provider_name"], "logo_path": p.get("logo_path"),
                "display_priority": (p.get("display_priorities") or {}).get("DE", p.get("display_priority", 999)),
                "media_types": set(),
            })
            m["media_types"].add(kind)
    rows = []
    for pid, m in merged.items():
        if pid in existing:
            active = existing[pid]["active"]
        else:
            name = m["name"].lower()
            active = 1 if (pid in DEFAULT_ACTIVE_IDS or (any(name.startswith(n) for n in DEFAULT_ACTIVE_NAMES)
                                                       and not any(x in name for x in DEFAULT_EXCLUDE))) else 0
        rows.append((pid, m["name"], m["logo_path"], m["display_priority"], active, json.dumps(sorted(m["media_types"]))))
    db.executemany(
        "INSERT INTO providers(id,name,logo_path,display_priority,active,media_types) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, logo_path=excluded.logo_path, "
        "display_priority=excluded.display_priority, media_types=excluded.media_types", rows)
    return len(rows)


async def seed_genres(force: bool = False) -> None:
    if not force and db.query_one("SELECT 1 FROM genres LIMIT 1"):
        return
    rows = []
    for mt in ("movie", "tv"):
        for g in await tmdb.genres(mt):
            rows.append((g["id"], mt, g["name"]))
    if rows:
        db.executemany("INSERT OR REPLACE INTO genres(id,media_type,name) VALUES(?,?,?)", rows)


async def bootstrap() -> dict[str, Any]:
    """Nach Eingabe des API-Schlüssels: Stammdaten laden."""
    n = await seed_providers()
    await seed_genres()
    return {"providers": n}


# ---------- IMDb-CSV-Import ----------

async def resolve_imdb(imdb_id: str, hint_type: str | None) -> tuple[str, int] | None:
    cached = db.query_one("SELECT media_type, tmdb_id FROM titles WHERE imdb_id=?", (imdb_id,))
    if cached:
        return cached["media_type"], cached["tmdb_id"]
    data = await tmdb.find_by_imdb(imdb_id)
    if not data:
        return None
    movies = data.get("movie_results") or []
    tvs = data.get("tv_results") or []
    pick: tuple[str, dict[str, Any]] | None = None
    if hint_type == "tv" and tvs:
        pick = ("tv", tvs[0])
    elif hint_type == "movie" and movies:
        pick = ("movie", movies[0])
    elif movies:
        pick = ("movie", movies[0])
    elif tvs:
        pick = ("tv", tvs[0])
    if not pick:
        return None
    mt, r = pick
    row = titles.lite_from_result(mt, r)
    row["imdb_id"] = imdb_id
    existing = titles.get_title(mt, row["tmdb_id"])
    if existing and existing.get("details_fetched_at"):
        if not existing.get("imdb_id"):
            db.execute("UPDATE titles SET imdb_id=? WHERE media_type=? AND tmdb_id=?", (imdb_id, mt, row["tmdb_id"]))
    else:
        titles.upsert_title(row)
    return mt, row["tmdb_id"]


async def import_imdb_csv(job: Job, content: bytes, mode: str) -> None:
    """mode: ratings | watchlist"""
    rows = imdb.parse_export(content)
    job.update(0, len(rows), "IMDb-Export wird verarbeitet …")
    threshold = int(db.get_setting("dislike_threshold", 1))
    stats = {"imported": 0, "skipped": 0, "unmatched": 0, "updated": 0}
    sem = asyncio.Semaphore(12)
    done = 0

    async def one(r: dict[str, Any]) -> None:
        nonlocal done
        async with sem:
            if r["media_type"] is None:
                stats["skipped"] += 1
                db.execute("INSERT INTO import_log(job_id,source,ref,title,result) VALUES(?,?,?,?,?)",
                           (job.id, "imdb", r["imdb_id"], r["title"], f"übersprungen ({r['title_type']})"))
            else:
                try:
                    key = await resolve_imdb(r["imdb_id"], r["media_type"])
                except tmdb.TMDBError as e:
                    key = None
                    db.execute("INSERT INTO import_log(job_id,source,ref,title,result) VALUES(?,?,?,?,?)",
                               (job.id, "imdb", r["imdb_id"], r["title"], f"Fehler: {e}"))
                if key is None:
                    stats["unmatched"] += 1
                    db.execute("INSERT INTO import_log(job_id,source,ref,title,result) VALUES(?,?,?,?,?)",
                               (job.id, "imdb", r["imdb_id"], r["title"], "nicht bei TMDB gefunden"))
                else:
                    mt, tid = key
                    existing = library.get_entry(mt, tid)
                    if mode == "ratings":
                        rating = r["rating"]
                        status = "disliked" if (rating is not None and rating <= threshold) else "watched"
                        if existing and existing["status"] == "watching" and status == "watched":
                            status = "watching"  # laufende Serie nicht überschreiben
                        library.set_status(mt, tid, status, rating=rating, rated_at=r["rated_at"], source="imdb")
                    else:  # watchlist
                        if existing and existing["status"] in ("watched", "disliked", "watching"):
                            stats["skipped"] += 1
                            done += 1
                            return
                        library.set_status(mt, tid, "watchlist", source="imdb")
                    stats["updated" if existing else "imported"] += 1
            done += 1
            if done % 10 == 0 or done == len(rows):
                job.update(done, len(rows), f"{done}/{len(rows)} verarbeitet")

    await asyncio.gather(*(one(r) for r in rows))
    job.result = stats
    job.update(len(rows), len(rows), f"Fertig: {stats['imported']} neu, {stats['updated']} aktualisiert, "
                                     f"{stats['unmatched']} nicht gefunden, {stats['skipped']} übersprungen")


# ---------- Titelliste (z. B. aus JustWatch kopiert) ----------

LINE_RE = re.compile(r"^(?P<title>.+?)(?:\s*[\(\[]?(?P<year>(19|20)\d{2})[\)\]]?)?\s*$")


async def import_title_list(job: Job, text: str, status: str, media_hint: str | None) -> None:
    lines = [ln.strip(" \t-•*") for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    job.update(0, len(lines), "Titelliste wird aufgelöst …")
    stats = {"imported": 0, "unmatched": 0, "skipped": 0}
    sem = asyncio.Semaphore(8)
    done = 0

    async def one(line: str) -> None:
        nonlocal done
        async with sem:
            m = LINE_RE.match(line)
            title, year = (m.group("title"), m.group("year")) if m else (line, None)
            year_i = int(year) if year else None
            candidates: list[tuple[str, dict[str, Any]]] = []
            try:
                for mt in ([media_hint] if media_hint in ("movie", "tv") else ["movie", "tv"]):
                    for r in (await tmdb.search_single(mt, title, year_i))[:3]:
                        candidates.append((mt, r))
            except tmdb.TMDBError as e:
                db.execute("INSERT INTO import_log(job_id,source,ref,title,result) VALUES(?,?,?,?,?)",
                           (job.id, "list", line, title, f"Fehler: {e}"))
            if not candidates:
                stats["unmatched"] += 1
                db.execute("INSERT INTO import_log(job_id,source,ref,title,result) VALUES(?,?,?,?,?)",
                           (job.id, "list", line, title, "nicht gefunden"))
            else:
                def score(c: tuple[str, dict[str, Any]]) -> float:
                    mt, r = c
                    name = (r.get("title") or r.get("name") or "").lower()
                    s = float(r.get("popularity") or 0)
                    if name == title.lower():
                        s += 1000
                    ry = titles._year(r.get("release_date") or r.get("first_air_date"))
                    if year_i and ry == year_i:
                        s += 500
                    return s
                mt, r = max(candidates, key=score)
                titles.upsert_lite(mt, r)
                if library.get_entry(mt, r["id"]):
                    stats["skipped"] += 1
                else:
                    library.set_status(mt, r["id"], status, source="list")
                    stats["imported"] += 1
            done += 1
            job.update(done, len(lines), f"{done}/{len(lines)} verarbeitet")

    await asyncio.gather(*(one(ln) for ln in lines))
    job.result = stats
    job.update(len(lines), len(lines), f"Fertig: {stats['imported']} neu, {stats['skipped']} bereits vorhanden, "
                                       f"{stats['unmatched']} nicht gefunden")


# ---------- TMDB-Konto ----------

def tmdb_session() -> tuple[str, int] | None:
    sid = db.get_setting("tmdb_session_id")
    aid = db.get_setting("tmdb_account_id")
    if sid and aid:
        return sid, int(aid)
    return None


async def sync_tmdb_account(job: Job) -> None:
    sess = tmdb_session()
    if not sess:
        raise RuntimeError("Kein TMDB-Konto verbunden.")
    sid, aid = sess
    job.update(0, 4, "TMDB-Watchlist wird geladen …")
    stats = {"watchlist": 0, "rated": 0, "skipped": 0}
    threshold = int(db.get_setting("dislike_threshold", 1))
    step = 0
    for kind in ("watchlist", "rated"):
        for mt_api, mt in (("movies", "movie"), ("tv", "tv")):
            items = await tmdb.account_list(aid, kind, mt_api, sid)
            for r in items:
                titles.upsert_lite(mt, r)
                existing = library.get_entry(mt, r["id"])
                if kind == "watchlist":
                    if existing and existing["status"] != "watchlist":
                        stats["skipped"] += 1
                        continue
                    if not existing:
                        library.set_status(mt, r["id"], "watchlist", source="tmdb")
                        stats["watchlist"] += 1
                else:
                    rating = int(round(float(r.get("rating") or 0))) or None
                    if existing and existing["rating"] == rating and existing["status"] != "watchlist":
                        stats["skipped"] += 1  # unverändert
                        continue
                    status = "disliked" if (rating is not None and rating <= threshold) else "watched"
                    if existing and existing["status"] in ("watching", "dropped") and status == "watched":
                        status = existing["status"]  # laufende/abgebrochene Serie nicht umstellen
                    library.set_status(mt, r["id"], status, rating=rating, source="tmdb")
                    stats["rated"] += 1
            step += 1
            job.update(step, 4, f"{kind}/{mt_api}: {len(items)} Einträge")
    job.result = stats
    job.update(4, 4, f"Fertig: {stats['watchlist']} Watchlist-Einträge, {stats['rated']} Bewertungen, {stats['skipped']} übersprungen")


async def push_watchlist(media_type: str, tmdb_id: int, on: bool) -> None:
    """Best-effort: Watchlist-Änderung an TMDB spiegeln (wenn aktiviert, Standard: an)."""
    if not db.get_setting("tmdb_mirror_watchlist", True):
        return
    sess = tmdb_session()
    if not sess:
        return
    try:
        await tmdb.account_set_watchlist(sess[1], sess[0], media_type, tmdb_id, on)
    except tmdb.TMDBError as e:
        print("TMDB-Watchlist-Sync fehlgeschlagen:", e)


async def push_rating(media_type: str, tmdb_id: int, rating: int | None) -> None:
    """Best-effort: Bewertung an TMDB spiegeln (TMDB = Single Source of Truth)."""
    if not db.get_setting("tmdb_mirror_ratings", True):
        return
    sess = tmdb_session()
    if not sess:
        return
    try:
        if rating is None:
            await tmdb.delete_rating(media_type, tmdb_id, sess[0])
        else:
            await tmdb.rate(media_type, tmdb_id, sess[0], float(rating))
    except tmdb.TMDBError as e:
        print("TMDB-Bewertungs-Sync fehlgeschlagen:", e)


# ---------- Bibliothek auffrischen / Serien prüfen ----------

async def refresh_library(job: Job, only_series: bool = False, everything: bool = False) -> None:
    """Details+Anbieter für Watchlist/Serien aktualisieren und neue Staffeln erkennen.
    everything=True: zusätzlich alle gesehenen/abgelehnten Titel ohne vollständige Details nachladen."""
    if everything:
        rows = db.query("SELECT u.media_type, u.tmdb_id FROM user_titles u LEFT JOIN titles t "
                        "ON t.media_type=u.media_type AND t.tmdb_id=u.tmdb_id "
                        "WHERE u.status IN ('watchlist','watching') OR t.details_fetched_at IS NULL")
    elif only_series:
        rows = db.query("SELECT media_type, tmdb_id FROM user_titles WHERE media_type='tv' AND status IN ('watching','watchlist')")
    else:
        rows = db.query("SELECT media_type, tmdb_id FROM user_titles WHERE status IN ('watchlist','watching')")
    keys = [(r["media_type"], r["tmdb_id"]) for r in rows]
    job.update(0, len(keys), "Titel werden aktualisiert …")
    sem = asyncio.Semaphore(12)
    done = 0

    async def one(k: tuple[str, int]) -> None:
        nonlocal done
        async with sem:
            try:
                await titles.ensure_title(k[0], k[1], force=(k[0] == "tv"), providers_ttl=timedelta(hours=6))
            except tmdb.TMDBError:
                pass
            done += 1
            if done % 5 == 0 or done == len(keys):
                job.update(done, len(keys), f"{done}/{len(keys)} aktualisiert")

    await asyncio.gather(*(one(k) for k in keys))
    job.update(len(keys), len(keys), "Wiedergabesprachen (JustWatch) werden geladen …")
    try:
        await justwatch.ensure_many([k for k in keys if k[0] in ("movie", "tv")])
    except Exception:  # noqa: BLE001
        pass
    fav_ids = sorted(people.favorite_ids())
    if fav_ids:
        job.update(len(keys), len(keys), f"Filmografien von {len(fav_ids)} Schauspielern werden aktualisiert …")
        stale = [r["id"] for r in db.query(f"SELECT id, details_fetched_at FROM people WHERE id IN ({','.join('?' * len(fav_ids))})", fav_ids)
                 if people._stale(r.get("details_fetched_at"))]
        await people.ensure_many(stale)
    newly = check_availability()
    flagged = check_new_seasons()
    job.result = {"refreshed": len(keys), "new_seasons": flagged, "newly_available": newly}
    job.update(len(keys), len(keys), f"Fertig: {len(keys)} Titel aktualisiert, {flagged} Serien mit neuen Folgen, "
                                     f"{newly} neu verfügbar")


def check_availability() -> int:
    """Merkt sich je Watchlist-/Serien-Titel, ob er bei meinen Anbietern läuft, und markiert Wechsel auf 'verfügbar'."""
    items = library.list_titles(status=["watchlist", "watching"])
    newly = 0
    for t in items:
        if t.get("availability") is None:
            continue
        mine = 1 if t["availability"].get("mine") else 0
        prev = db.query_one("SELECT avail_mine FROM user_titles WHERE media_type=? AND tmdb_id=?",
                            (t["media_type"], t["tmdb_id"]))
        prev_val = prev["avail_mine"] if prev else None
        if prev_val == 0 and mine == 1:
            newly += 1
            db.execute("UPDATE user_titles SET avail_mine=1, newly_available=1 WHERE media_type=? AND tmdb_id=?",
                       (t["media_type"], t["tmdb_id"]))
        else:
            db.execute("UPDATE user_titles SET avail_mine=?, newly_available=CASE WHEN ?=0 THEN 0 ELSE newly_available END "
                       "WHERE media_type=? AND tmdb_id=?", (mine, mine, t["media_type"], t["tmdb_id"]))
    return newly


def check_new_seasons() -> int:
    """Setzt new_season_flag/new_kind für verfolgte, begonnene Serien mit ausstehenden Folgen bei eigenen Anbietern."""
    series = library.list_titles(status=["watching"], media_type="tv")
    flagged = 0
    for t in series:
        prog = library.series_progress(t)
        avail = t.get("availability") or {}
        new = prog["started"] and prog["pending"] > 0 and bool(avail.get("mine"))
        kind = ("season" if prog["new_season"] else "episodes") if new else None
        db.execute("UPDATE user_titles SET new_season_flag=?, new_kind=? WHERE media_type='tv' AND tmdb_id=?",
                   (1 if new else 0, kind, t["tmdb_id"]))
        flagged += 1 if new else 0
    return flagged

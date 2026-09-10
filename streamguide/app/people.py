"""Personen (Schauspieler): TMDB-Details, Hauptrollen, Favoriten, Neuerscheinungen von Favoriten."""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from typing import Any

from . import db, titles, tmdb

DETAILS_TTL = timedelta(days=7)
MAIN_ROLE_MAX_ORDER = 4   # Top-5-Billing gilt als Hauptrolle
EXCLUDED_TV_GENRES = {10767, 10763, 10764}  # Talk, News, Reality


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _stale(ts: str | None, ttl: timedelta = DETAILS_TTL) -> bool:
    if not ts:
        return True
    try:
        return datetime.fromisoformat(ts) < datetime.utcnow() - ttl
    except ValueError:
        return True


# ---------- Persistenz ----------

def get(person_id: int) -> dict[str, Any] | None:
    return db.query_one("SELECT * FROM people WHERE id=?", (person_id,))


def upsert_lite(p: dict[str, Any]) -> None:
    """Aus Such-/Trend-/Cast-Ergebnis eine schlanke Personenzeile anlegen (vorhandene Details nicht überschreiben)."""
    row = get(p["id"])
    if row and row.get("details_fetched_at"):
        return
    db.execute(
        "INSERT INTO people(id,name,profile_path,known_for_department,popularity,gender) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, profile_path=COALESCE(excluded.profile_path, people.profile_path), "
        "known_for_department=COALESCE(excluded.known_for_department, people.known_for_department), popularity=excluded.popularity",
        (p["id"], p.get("name"), p.get("profile_path"), p.get("known_for_department"), p.get("popularity"), p.get("gender")),
    )


def _credit_row(c: dict[str, Any]) -> dict[str, Any]:
    mt = c.get("media_type") or ("movie" if c.get("title") else "tv")
    return {
        "media_type": mt,
        "tmdb_id": c["id"],
        "title": c.get("title") if mt == "movie" else c.get("name"),
        "original_title": c.get("original_title") if mt == "movie" else c.get("original_name"),
        "date": c.get("release_date") if mt == "movie" else c.get("first_air_date"),
        "character": c.get("character"),
        "order": c.get("order"),
        "episode_count": c.get("episode_count"),
        "poster_path": c.get("poster_path"),
        "vote_average": c.get("vote_average"),
        "vote_count": c.get("vote_count"),
        "genre_ids": c.get("genre_ids") or [],
        "popularity": c.get("popularity"),
    }


async def ensure(person_id: int, force: bool = False) -> dict[str, Any] | None:
    """Details + Filmografie (combined_credits) sicherstellen."""
    row = get(person_id)
    if row and not force and not _stale(row.get("details_fetched_at")):
        return row
    d = await tmdb.get(f"/person/{person_id}", language=tmdb.LANG, append_to_response="combined_credits,external_ids")
    if not d:
        return row
    bio = d.get("biography") or ""
    if not bio:
        try:
            d_en = await tmdb.get(f"/person/{person_id}", language="en-US")
            bio = (d_en or {}).get("biography") or ""
        except tmdb.TMDBError:
            pass
    cast = [_credit_row(c) for c in (d.get("combined_credits") or {}).get("cast", []) if c.get("id")]
    # Doppelte (z. B. mehrere Rollen in einer Serie) zusammenfassen: beste Billing-Position behalten
    merged: dict[tuple[str, int], dict[str, Any]] = {}
    for c in cast:
        key = (c["media_type"], c["tmdb_id"])
        cur = merged.get(key)
        if cur is None or (c.get("order") is not None and (cur.get("order") is None or c["order"] < cur["order"])):
            if cur and cur.get("character") and c.get("character") and cur["character"] != c["character"]:
                c["character"] = f"{c['character']} / {cur['character']}"
            merged[key] = c
        elif cur and c.get("character") and c["character"] not in (cur.get("character") or ""):
            cur["character"] = f"{cur['character']} / {c['character']}" if cur.get("character") else c["character"]
    credits = sorted(merged.values(), key=lambda c: c.get("date") or "0000", reverse=True)
    ext = d.get("external_ids") or {}
    db.execute(
        "INSERT INTO people(id,imdb_id,name,profile_path,known_for_department,birthday,deathday,place_of_birth,biography,popularity,gender,credits,details_fetched_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET imdb_id=excluded.imdb_id, name=excluded.name, profile_path=excluded.profile_path, "
        "known_for_department=excluded.known_for_department, birthday=excluded.birthday, deathday=excluded.deathday, place_of_birth=excluded.place_of_birth, "
        "biography=excluded.biography, popularity=excluded.popularity, gender=excluded.gender, credits=excluded.credits, details_fetched_at=excluded.details_fetched_at",
        (person_id, ext.get("imdb_id") or d.get("imdb_id"), d.get("name"), d.get("profile_path"), d.get("known_for_department"),
         d.get("birthday"), d.get("deathday"), d.get("place_of_birth"), bio, d.get("popularity"), d.get("gender"),
         json.dumps(credits), now_iso()),
    )
    return get(person_id)


async def ensure_many(ids: list[int], force: bool = False) -> None:
    ids = list(dict.fromkeys(ids))
    sem = asyncio.Semaphore(8)

    async def one(pid: int) -> None:
        async with sem:
            try:
                await ensure(pid, force)
            except tmdb.TMDBError:
                pass

    await asyncio.gather(*(one(i) for i in ids))


# ---------- Favoriten ----------

def favorite_ids() -> set[int]:
    return {r["person_id"] for r in db.query("SELECT person_id FROM user_people")}


def set_favorite(person_id: int, on: bool, source: str = "manual") -> None:
    if on:
        db.execute("INSERT OR IGNORE INTO user_people(person_id, source) VALUES(?,?)", (person_id, source))
    else:
        db.execute("DELETE FROM user_people WHERE person_id=?", (person_id,))


# ---------- Nicht mein Fall (Sperrliste) ----------

def blocked_ids() -> set[int]:
    return {r["person_id"] for r in db.query("SELECT person_id FROM blocked_people")}


def set_blocked(person_id: int, on: bool) -> None:
    if on:
        db.execute("INSERT OR IGNORE INTO blocked_people(person_id) VALUES(?)", (person_id,))
    else:
        db.execute("DELETE FROM blocked_people WHERE person_id=?", (person_id,))


def blocked() -> list[dict[str, Any]]:
    rows = db.query("SELECT p.*, b.added_at FROM blocked_people b JOIN people p ON p.id=b.person_id ORDER BY p.name COLLATE NOCASE")
    favs = favorite_ids()
    return [{**person_lite(r, favs), "blocked": True, "gender": r.get("gender")} for r in rows]


# ---------- Ausgabe ----------

def is_main_role(c: dict[str, Any]) -> bool:
    if c.get("order") is None or c["order"] > MAIN_ROLE_MAX_ORDER:
        return False
    ch = (c.get("character") or "").strip().lower()
    if ch.startswith(("self", "himself", "herself", "themselves")) or 99 in (c.get("genre_ids") or []):
        return False  # Dokus / Auftritte als sie selbst sind keine Rollen
    if c["media_type"] == "tv":
        if set(c.get("genre_ids") or []) & EXCLUDED_TV_GENRES:
            return False
        if (c.get("episode_count") or 0) < 2 and (c.get("vote_count") or 0) < 20:
            return False  # Gastauftritte
    return True


def decorate_person(row: dict[str, Any], with_credits: bool = True, favs: set[int] | None = None) -> dict[str, Any]:
    favs = favorite_ids() if favs is None else favs
    out = {
        "id": row["id"], "imdb_id": row.get("imdb_id"), "name": row.get("name"), "profile_path": row.get("profile_path"),
        "known_for_department": row.get("known_for_department"), "birthday": row.get("birthday"), "deathday": row.get("deathday"),
        "place_of_birth": row.get("place_of_birth"), "biography": row.get("biography"), "popularity": row.get("popularity"),
        "gender": row.get("gender"), "favorite": row["id"] in favs, "blocked": row["id"] in blocked_ids(),
        "details_fetched": bool(row.get("details_fetched_at")),
    }
    if row.get("birthday"):
        try:
            b = date.fromisoformat(row["birthday"])
            end = date.fromisoformat(row["deathday"]) if row.get("deathday") else date.today()
            out["age"] = end.year - b.year - ((end.month, end.day) < (b.month, b.day))
        except ValueError:
            pass
    if with_credits:
        credits = db.loads(row.get("credits"), []) or []
        keys = [(c["media_type"], c["tmdb_id"]) for c in credits]
        user_map = titles.user_status_map(keys)
        # zwischengespeicherte Titel (IMDb-Rating, Verfügbarkeit) anreichern, ohne API-Aufrufe
        cached: dict[tuple[str, int], dict[str, Any]] = {}
        ids = list({k[1] for k in keys})
        for chunk in range(0, len(ids), 400):
            part = ids[chunk:chunk + 400]
            rows = db.query(f"SELECT * FROM titles WHERE tmdb_id IN ({','.join('?' * len(part))})", part)
            for t in titles.decorate(rows, user_map):
                cached[(t["media_type"], t["tmdb_id"])] = t
        out_credits = []
        for c in credits:
            key = (c["media_type"], c["tmdb_id"])
            t = cached.get(key)
            out_credits.append({
                **c,
                "year": int(c["date"][:4]) if c.get("date") and c["date"][:4].isdigit() else None,
                "main": is_main_role(c),
                "imdb_rating": t["imdb_rating"] if t else None,
                "availability": t["availability"] if t else None,
                "user": user_map.get(key),
                "poster_path": c.get("poster_path") or (t["poster_path"] if t else None),
            })
        out["credits"] = out_credits
        out["main_roles"] = sum(1 for c in out_credits if c["main"])
    return out


def person_lite(p: dict[str, Any], favs: set[int]) -> dict[str, Any]:
    return {
        "id": p["id"], "name": p.get("name"), "profile_path": p.get("profile_path"),
        "known_for_department": p.get("known_for_department"), "popularity": p.get("popularity"),
        "known_for": [(k.get("title") or k.get("name")) for k in (p.get("known_for") or [])[:3]],
        "favorite": p["id"] in favs,
    }


async def search(q: str) -> list[dict[str, Any]]:
    data = await tmdb.get("/search/person", query=q, language=tmdb.LANG, include_adult="false")
    favs = favorite_ids()
    out = []
    for p in (data or {}).get("results", []):
        upsert_lite(p)
        out.append(person_lite(p, favs))
    return out


async def trending() -> list[dict[str, Any]]:
    data = await tmdb.get("/trending/person/week", language=tmdb.LANG)
    favs = favorite_ids()
    out = []
    for p in (data or {}).get("results", []):
        if p.get("known_for_department") not in (None, "Acting"):
            continue
        upsert_lite(p)
        out.append(person_lite(p, favs))
    return out[:20]


def favorites() -> list[dict[str, Any]]:
    rows = db.query("SELECT p.*, u.added_at FROM user_people u JOIN people p ON p.id=u.person_id ORDER BY p.name COLLATE NOCASE")
    favs = {r["id"] for r in rows}
    out = []
    for r in rows:
        d = decorate_person(r, with_credits=False, favs=favs)
        out.append({**person_lite(r, favs), "added_at": r["added_at"], "details_fetched": bool(r.get("details_fetched_at")),
                    "gender": r.get("gender"), "birthday": r.get("birthday"), "deathday": r.get("deathday"), "age": d.get("age")})
    return out


async def resolve_imdb(imdb_id: str) -> int | None:
    row = db.query_one("SELECT id FROM people WHERE imdb_id=?", (imdb_id,))
    if row:
        return row["id"]
    data = await tmdb.find_by_imdb(imdb_id)
    res = (data or {}).get("person_results") or []
    if not res:
        return None
    upsert_lite(res[0])
    db.execute("UPDATE people SET imdb_id=? WHERE id=?", (imdb_id, res[0]["id"]))
    return res[0]["id"]


def new_from_favorites(days_back: int = 240, days_ahead: int = 120, limit: int = 40) -> list[dict[str, Any]]:
    """Hauptrollen der Favoriten mit Veröffentlichung im Zeitfenster (aus zwischengespeicherten Filmografien)."""
    today = date.today()
    lo = (today - timedelta(days=days_back)).isoformat()
    hi = (today + timedelta(days=days_ahead)).isoformat()
    rows = db.query("SELECT p.id, p.name, p.profile_path, p.credits FROM user_people u JOIN people p ON p.id=u.person_id")
    found: dict[tuple[str, int], dict[str, Any]] = {}
    for r in rows:
        for c in db.loads(r.get("credits"), []) or []:
            d = c.get("date")
            if not d or not (lo <= d <= hi) or not is_main_role(c):
                continue
            key = (c["media_type"], c["tmdb_id"])
            entry = found.setdefault(key, {**c, "people": []})
            entry["people"].append({"id": r["id"], "name": r["name"], "profile_path": r["profile_path"], "character": c.get("character")})
    t = today.isoformat()
    released = sorted((c for c in found.values() if (c.get("date") or "") <= t), key=lambda c: c.get("date") or "", reverse=True)
    upcoming = sorted((c for c in found.values() if (c.get("date") or "") > t), key=lambda c: c.get("date") or "")
    return (released + upcoming)[:limit]  # erst frisch erschienen (neueste zuerst), dann kommende (nächste zuerst)

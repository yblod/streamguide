"""Titel-Cache: TMDB-Details, Streaming-Angebote (DE), IMDb-Bewertung, Zugangsmodell."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, date
from typing import Any, Iterable

from . import db, tmdb

DETAILS_TTL = timedelta(days=7)
PROVIDERS_TTL = timedelta(days=1)
OFFER_TYPES = ("flatrate", "free", "ads", "rent", "buy")

FSK_ORDER = {"0": 0, "6": 6, "12": 12, "16": 16, "18": 18}


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _year(s: str | None) -> int | None:
    if s and len(s) >= 4 and s[:4].isdigit():
        return int(s[:4])
    return None


# ---------- Normalisierung von TMDB-Objekten ----------

def lite_from_result(media_type: str, r: dict[str, Any]) -> dict[str, Any]:
    """Aus Such-/Discover-Ergebnis eine schlanke Titelzeile bauen."""
    is_movie = media_type == "movie"
    return {
        "media_type": media_type,
        "tmdb_id": r["id"],
        "title": r.get("title") if is_movie else r.get("name"),
        "original_title": r.get("original_title") if is_movie else r.get("original_name"),
        "year": _year(r.get("release_date") if is_movie else r.get("first_air_date")),
        "overview": r.get("overview") or "",
        "poster_path": r.get("poster_path"),
        "backdrop_path": r.get("backdrop_path"),
        "genre_ids": json.dumps(r.get("genre_ids") or [g["id"] for g in r.get("genres", [])]),
        "origin_countries": json.dumps(r.get("origin_country") or []),
        "original_language": r.get("original_language"),
        "tmdb_rating": r.get("vote_average"),
        "tmdb_votes": r.get("vote_count"),
        "popularity": r.get("popularity"),
    }


def _certification(media_type: str, d: dict[str, Any]) -> str | None:
    if media_type == "movie":
        for entry in (d.get("release_dates") or {}).get("results", []):
            if entry.get("iso_3166_1") == "DE":
                for rd in entry.get("release_dates", []):
                    c = (rd.get("certification") or "").strip()
                    if c:
                        return c
    else:
        for entry in (d.get("content_ratings") or {}).get("results", []):
            if entry.get("iso_3166_1") == "DE" and entry.get("rating"):
                return str(entry["rating"]).strip()
    return None


def _de_release(media_type: str, d: dict[str, Any]) -> int:
    """1, wenn TMDB eine deutsche Veröffentlichung (Film) bzw. deutsche Altersfreigabe (Serie) kennt."""
    if media_type == "movie":
        for entry in (d.get("release_dates") or {}).get("results", []):
            if entry.get("iso_3166_1") == "DE" and entry.get("release_dates"):
                return 1
    else:
        for entry in (d.get("content_ratings") or {}).get("results", []):
            if entry.get("iso_3166_1") == "DE":
                return 1
    return 0


def _seasons(d: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for s in d.get("seasons") or []:
        if s.get("season_number", 0) <= 0:
            continue
        out.append({
            "season_number": s["season_number"],
            "name": s.get("name"),
            "episode_count": s.get("episode_count"),
            "air_date": s.get("air_date"),
            "poster_path": s.get("poster_path"),
        })
    return out


def full_from_details(media_type: str, d: dict[str, Any]) -> dict[str, Any]:
    row = lite_from_result(media_type, d)
    ext = d.get("external_ids") or {}
    imdb_id = ext.get("imdb_id") or d.get("imdb_id")
    if media_type == "movie":
        runtime = d.get("runtime")
    else:
        rt = d.get("episode_run_time") or []
        runtime = rt[0] if rt else ((d.get("last_episode_to_air") or {}).get("runtime"))
    prov = ((d.get("watch/providers") or {}).get("results") or {}).get(tmdb.REGION) or {}
    origin = d.get("origin_country") or [c.get("iso_3166_1") for c in d.get("production_countries", [])]
    nxt = d.get("next_episode_to_air") or {}
    last_ep = d.get("last_episode_to_air") or {}
    cast_src = (d.get("credits") or d.get("aggregate_credits") or {}).get("cast") or []
    cast = []
    for c in cast_src[:12]:
        roles = c.get("roles") or []
        character = c.get("character") or " / ".join(x.get("character") for x in roles if x.get("character"))
        cast.append({"id": c["id"], "name": c.get("name"), "character": character, "profile_path": c.get("profile_path"),
                     "order": c.get("order"), "episodes": c.get("total_episode_count")})
    row.update({
        "cast": json.dumps(cast),
        "last_ep_season": last_ep.get("season_number"),
        "last_ep_number": last_ep.get("episode_number"),
        "imdb_id": imdb_id,
        "runtime": runtime,
        "origin_countries": json.dumps(origin),
        "certification": _certification(media_type, d),
        "de_release": _de_release(media_type, d),
        "status": d.get("status"),
        "number_of_seasons": d.get("number_of_seasons"),
        "seasons": json.dumps(_seasons(d)) if media_type == "tv" else None,
        "next_episode_air": nxt.get("air_date"),
        "last_air_date": d.get("last_air_date"),
        "providers": json.dumps(clean_providers(prov)),
        "providers_fetched_at": now_iso(),
        "details_fetched_at": now_iso(),
    })
    return row


def clean_providers(prov: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"link": prov.get("link")}
    for t in OFFER_TYPES:
        out[t] = [
            {"id": p["provider_id"], "name": p.get("provider_name"), "logo": p.get("logo_path")}
            for p in prov.get(t, [])
        ]
    return out


# ---------- Persistenz ----------

def upsert_title(row: dict[str, Any]) -> None:
    cols = [c for c in row.keys()]
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("media_type", "tmdb_id"))
    db.execute(
        f"INSERT INTO titles({','.join(cols)}) VALUES({placeholders}) "
        f"ON CONFLICT(media_type,tmdb_id) DO UPDATE SET {updates}, updated_at=datetime('now')",
        tuple(row[c] for c in cols),
    )


def upsert_lite(media_type: str, r: dict[str, Any]) -> None:
    """Schlanke Daten nur einfügen, wenn kein vollständiger Datensatz existiert."""
    row = lite_from_result(media_type, r)
    existing = db.query_one("SELECT details_fetched_at, original_language FROM titles WHERE media_type=? AND tmdb_id=?",
                            (media_type, row["tmdb_id"]))
    if existing and existing["details_fetched_at"]:
        if not existing["original_language"] and row.get("original_language"):
            db.execute("UPDATE titles SET original_language=? WHERE media_type=? AND tmdb_id=?",
                       (row["original_language"], media_type, row["tmdb_id"]))
        return
    upsert_title(row)


def get_title(media_type: str, tmdb_id: int) -> dict[str, Any] | None:
    return db.query_one("SELECT * FROM titles WHERE media_type=? AND tmdb_id=?", (media_type, tmdb_id))


def _stale(ts: str | None, ttl: timedelta) -> bool:
    if not ts:
        return True
    try:
        return datetime.fromisoformat(ts) < datetime.utcnow() - ttl
    except ValueError:
        return True


async def ensure_title(media_type: str, tmdb_id: int, force: bool = False,
                       providers_ttl: timedelta = PROVIDERS_TTL) -> dict[str, Any] | None:
    """Sorgt für vollständige, frische Daten eines Titels (holt bei Bedarf von TMDB)."""
    row = get_title(media_type, tmdb_id)
    need_details = force or row is None or _stale(row.get("details_fetched_at"), DETAILS_TTL)
    if not need_details and media_type == "tv" and row.get("last_ep_season") is None and db.loads(row.get("seasons"), []):
        need_details = True  # vor der Folgen-Erweiterung gecacht: last_episode_to_air nachladen
    if not need_details and row.get("cast") is None:
        need_details = True  # vor der Besetzungs-Erweiterung gecacht
    need_providers = need_details or _stale(row.get("providers_fetched_at"), providers_ttl)
    if need_details:
        d = await tmdb.details(media_type, tmdb_id)
        if d is None:
            return row
        upsert_title(full_from_details(media_type, d))
    elif need_providers:
        prov = await tmdb.providers_only(media_type, tmdb_id)
        if prov is not None:
            db.execute("UPDATE titles SET providers=?, providers_fetched_at=? WHERE media_type=? AND tmdb_id=?",
                       (json.dumps(clean_providers(prov)), now_iso(), media_type, tmdb_id))
    return get_title(media_type, tmdb_id)


async def ensure_many(keys: Iterable[tuple[str, int]], force: bool = False,
                      providers_ttl: timedelta = PROVIDERS_TTL) -> None:
    keys = list(dict.fromkeys(keys))
    if not keys:
        return

    async def one(k: tuple[str, int]) -> None:
        try:
            await ensure_title(k[0], k[1], force=force, providers_ttl=providers_ttl)
        except tmdb.TMDBError:
            pass

    await asyncio.gather(*(one(k) for k in keys))


# ---------- Anreicherung für die API-Ausgabe ----------

def active_provider_ids() -> set[int]:
    return {r["id"] for r in db.query("SELECT id FROM providers WHERE active=1")}


def genre_map() -> dict[str, dict[int, str]]:
    m: dict[str, dict[int, str]] = {"movie": {}, "tv": {}}
    for r in db.query("SELECT id, media_type, name FROM genres"):
        m[r["media_type"]][r["id"]] = r["name"]
    return m


_FAMILY_SUFFIXES = (" free with ads", " standard with ads", " basic with ads", " with ads", " kids", " plus", "+")


def _family(name: str | None) -> str:
    n = (name or "").lower().strip()
    for suf in _FAMILY_SUFFIXES:
        if n.endswith(suf):
            n = n[: -len(suf)].strip()
    return n


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Varianten desselben Anbieters (Netflix / Netflix mit Werbung) nur einmal anzeigen."""
    seen: set[str] = set()
    out = []
    for p in items:
        fam = _family(p.get("name"))
        if fam in seen:
            continue
        seen.add(fam)
        out.append(p)
    return out


def _attach_audio(items: list[dict[str, Any]], jw: dict[str, Any] | None, kinds: tuple[str, ...]) -> list[dict[str, Any]]:
    """Jedem TMDB-Angebot die JustWatch-Sprachen des passenden Anbieters (gleiche Familie, gleiche Art) zuordnen."""
    if not jw or not jw.get("offers"):
        return items
    out = []
    for p in items:
        fam = _family(p.get("name"))
        audio: set[str] = set()
        subs: set[str] = set()
        matched = False
        for o in jw["offers"]:
            if o.get("kind") not in kinds:
                continue
            ofam = _family(o.get("name"))
            if ofam == fam or ofam.startswith(fam) or fam.startswith(ofam):
                matched = True
                audio.update(o.get("audio") or [])
                subs.update(o.get("subs") or [])
        q = dict(p)
        if matched:
            q["audio"] = sorted(audio)
            q["subs"] = sorted(subs)
        out.append(q)
    return out


def availability(providers: dict[str, Any] | None, active: set[int], count_all_free: bool,
                 jw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Zugangsmodell aus Sicht des Nutzers berechnen (inkl. Wiedergabesprachen aus JustWatch, falls vorhanden)."""
    prov = providers or {}
    sub = _dedupe([p for p in prov.get("flatrate", []) if p["id"] in active])
    free_all = prov.get("free", []) + prov.get("ads", [])
    free = _dedupe([p for p in free_all if count_all_free or p["id"] in active])
    rent = _dedupe(prov.get("rent", []))
    buy = _dedupe(prov.get("buy", []))
    other_sub = _dedupe([p for p in prov.get("flatrate", []) if p["id"] not in active])
    other_free = _dedupe([p for p in free_all if not (count_all_free or p["id"] in active)])
    if sub:
        mode = "sub"
    elif free:
        mode = "free"
    elif other_sub or other_free:
        mode = "other_sub"
    elif rent or buy:
        mode = "rent"
    else:
        mode = "none"
    sub = _attach_audio(sub, jw, ("flatrate",))
    free = _attach_audio(free, jw, ("free", "ads"))
    other_sub = _attach_audio(other_sub, jw, ("flatrate",))
    other_free = _attach_audio(other_free, jw, ("free", "ads"))
    rent = _attach_audio(rent, jw, ("rent",))
    buy = _attach_audio(buy, jw, ("buy",))
    return {
        "mode": mode,                    # sub | free | other_sub | rent | none
        "mine": bool(sub or free),
        "sub": sub, "free": free, "other_sub": other_sub, "other_free": other_free,
        "rent": rent, "buy": buy, "link": prov.get("link"),
        "jw": bool(jw and jw.get("found")), "jw_path": (jw or {}).get("path"),
    }


def offer_languages(av: dict[str, Any], scope: str) -> list[str] | None:
    """Vereinigte Wiedergabesprachen der Angebote im Geltungsbereich; None = keine Sprachdaten vorhanden."""
    groups = {
        "mine": ("sub", "free"), "stream": ("sub", "free", "other_sub", "other_free"),
        "free": ("free", "other_free"), "rent": ("rent", "buy"),
        "any": ("sub", "free", "other_sub", "other_free", "rent", "buy"),
    }.get(scope, ("sub", "free"))
    langs: set[str] = set()
    has = False
    for g in groups:
        for p in av.get(g, []):
            if p.get("audio"):
                has = True
                langs.update(p["audio"])
    return sorted(langs) if has else None


def decorate(rows: list[dict[str, Any]], user_map: dict[tuple[str, int], dict[str, Any]] | None = None
             ) -> list[dict[str, Any]]:
    """Titelzeilen aus der DB in API-Objekte verwandeln (IMDb-Rating, Genres, Verfügbarkeit, Nutzerstatus)."""
    if not rows:
        return []
    active = active_provider_ids()
    count_all_free = bool(db.get_setting("count_all_free", False))
    gmap = genre_map()
    imdb_ids = [r["imdb_id"] for r in rows if r.get("imdb_id")]
    ratings: dict[str, tuple[float, int]] = {}
    for chunk in range(0, len(imdb_ids), 500):
        part = imdb_ids[chunk:chunk + 500]
        for r in db.query(f"SELECT tconst, rating, votes FROM imdb_ratings WHERE tconst IN ({','.join('?' * len(part))})", part):
            ratings[r["tconst"]] = (r["rating"], r["votes"])
    if user_map is None:
        keys = [(r["media_type"], r["tmdb_id"]) for r in rows]
        user_map = user_status_map(keys)
    blocked = {r["person_id"] for r in db.query("SELECT person_id FROM blocked_people")}
    out = []
    for r in rows:
        providers = db.loads(r.get("providers"), None)
        jw = db.loads(r.get("jw_offers"), None)
        imdb = ratings.get(r.get("imdb_id") or "")
        gids = db.loads(r.get("genre_ids"), [])
        u = user_map.get((r["media_type"], r["tmdb_id"]))
        out.append({
            "media_type": r["media_type"],
            "tmdb_id": r["tmdb_id"],
            "imdb_id": r.get("imdb_id"),
            "title": r.get("title"),
            "original_title": r.get("original_title"),
            "year": r.get("year"),
            "overview": r.get("overview"),
            "poster_path": r.get("poster_path"),
            "backdrop_path": r.get("backdrop_path"),
            "genres": [gmap[r["media_type"]].get(g, str(g)) for g in gids],
            "genre_ids": gids,
            "runtime": r.get("runtime"),
            "origin_countries": db.loads(r.get("origin_countries"), []),
            "original_language": r.get("original_language"),
            "certification": r.get("certification"),
            "tmdb_rating": r.get("tmdb_rating"),
            "tmdb_votes": r.get("tmdb_votes"),
            "imdb_rating": imdb[0] if imdb else None,
            "imdb_votes": imdb[1] if imdb else None,
            "status": r.get("status"),
            "number_of_seasons": r.get("number_of_seasons"),
            "seasons": db.loads(r.get("seasons"), []),
            "next_episode_air": r.get("next_episode_air"),
            "last_air_date": r.get("last_air_date"),
            "last_ep_season": r.get("last_ep_season"),
            "last_ep_number": r.get("last_ep_number"),
            "availability": availability(providers, active, count_all_free, jw) if providers is not None else None,
            "cast": [{**c, "blocked": c.get("id") in blocked} for c in db.loads(r.get("cast"), [])],
            "blocked_by": [c.get("name") for c in db.loads(r.get("cast"), []) if c.get("id") in blocked and (c.get("order") or 0) <= 4],
            "details_fetched": bool(r.get("details_fetched_at")),
            "user": u,
        })
    return out


def user_status_map(keys: list[tuple[str, int]]) -> dict[tuple[str, int], dict[str, Any]]:
    if not keys:
        return {}
    out: dict[tuple[str, int], dict[str, Any]] = {}
    ids = list({k[1] for k in keys})
    for chunk in range(0, len(ids), 500):
        part = ids[chunk:chunk + 500]
        rows = db.query(f"SELECT * FROM user_titles WHERE tmdb_id IN ({','.join('?' * len(part))})", part)
        for r in rows:
            out[(r["media_type"], r["tmdb_id"])] = user_entry(r)
    return out


def user_entry(r: dict[str, Any]) -> dict[str, Any]:
    """user_titles-Zeile in das API-Objekt 'user' umwandeln."""
    return {
        "status": r["status"], "rating": r["rating"], "rated_at": r["rated_at"],
        "added_at": r["added_at"], "watched_seasons": db.loads(r.get("watched_seasons"), []),
        "watched_episodes": {int(k): v for k, v in db.loads(r.get("watched_episodes"), {}).items()},
        "new_season_flag": bool(r.get("new_season_flag")), "new_kind": r.get("new_kind"),
        "newly_available": bool(r.get("newly_available")), "notes": r.get("notes"),
    }


def aired_seasons(t: dict[str, Any]) -> list[int]:
    today = date.today().isoformat()
    return [s["season_number"] for s in (t.get("seasons") or []) if s.get("air_date") and s["air_date"] <= today]


def fsk_value(cert: str | None) -> int | None:
    if not cert:
        return None
    c = cert.upper().replace("FSK", "").replace("AB", "").strip()
    return FSK_ORDER.get(c)

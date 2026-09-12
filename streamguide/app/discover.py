"""Entdecken/Filtern über TMDB-Discover + lokale Filter (IMDb, FSK), Suche, Startseite."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from . import db, justwatch, library, people, titles, tmdb

MAX_PAGES_PER_CALL = 4
PAGE_SIZE = 20

# TMDB-Schlagwörter für den "Adult"-Modus (erotisches Genre); include_adult schaltet zusätzlich Erwachseneninhalte frei.
ADULT_KEYWORDS = (256466, 325693, 155477, 207767, 302868, 298666, 10053, 314184, 337325, 226010, 207807)


def _active_sub_ids(region: str = tmdb.REGION) -> list[int]:
    """Aktive Anbieter-IDs eines Landes inkl. aller Varianten desselben Katalogs (siehe titles.active_providers)."""
    return titles.active_ids_by_region().get(region, [])


def extra_region_params(media_type: str, f: dict[str, Any]) -> list[dict[str, Any]]:
    """Zusätzliche Discover-Abfragen für Zusatzländer (VPN) mit dort aktiven Anbietern, nur bei „meine Anbieter“."""
    if (f.get("availability") or "mine") != "mine":
        return []
    out = []
    for region in tmdb.extra_regions():
        ids = _active_sub_ids(region)
        if ids:
            out.append({**build_params(media_type, f), "watch_region": region,
                        "with_watch_providers": "|".join(str(i) for i in ids)})
    return out


def build_params(media_type: str, f: dict[str, Any]) -> dict[str, Any]:
    p: dict[str, Any] = {}
    date_key = "primary_release_date" if media_type == "movie" else "first_air_date"
    if f.get("year_from"):
        p[f"{date_key}.gte"] = f"{int(f['year_from'])}-01-01"
    if f.get("year_to"):
        p[f"{date_key}.lte"] = f"{int(f['year_to'])}-12-31"
    if f.get("genres"):
        p["with_genres"] = "|".join(str(g) for g in f["genres"])
    if f.get("exclude_genres"):
        p["without_genres"] = ",".join(str(g) for g in f["exclude_genres"])
    if f.get("countries"):
        p["with_origin_country"] = "|".join(f["countries"])
    if f.get("language"):
        p["with_original_language"] = f["language"]
    fsk = _fsk_set(f)
    if media_type == "movie" and fsk:
        p["certification_country"] = "DE"
        p["certification.lte"] = str(max(fsk))
        p["certification.gte"] = str(min(fsk))
    if f.get("tmdb_min"):
        p["vote_average.gte"] = float(f["tmdb_min"])
    if f.get("adult"):
        p["include_adult"] = "true"
        p["with_keywords"] = "|".join(str(k) for k in ADULT_KEYWORDS)
        p["vote_count.gte"] = min(int(f.get("min_votes") or 50), 10)
    else:
        p["vote_count.gte"] = int(f.get("min_votes") or 50)
    if f.get("runtime_min") and media_type == "movie":
        p["with_runtime.gte"] = int(f["runtime_min"])
    availability = f.get("availability") or "mine"
    if availability == "mine":
        ids = _active_sub_ids()
        if ids:
            p["with_watch_providers"] = "|".join(str(i) for i in ids)
        p["with_watch_monetization_types"] = "flatrate|free|ads"
    elif availability == "free":
        p["with_watch_monetization_types"] = "free|ads"
    elif availability == "rent":
        p["with_watch_monetization_types"] = "rent|buy"
    elif availability == "stream":
        p["with_watch_monetization_types"] = "flatrate|free|ads"
    sort = f.get("sort") or "popularity"
    p["sort_by"] = {
        "popularity": "popularity.desc",
        "tmdb": "vote_average.desc",
        "newest": f"{date_key}.desc",
        "oldest": f"{date_key}.asc",
        "imdb": "vote_average.desc",  # Vorfilter; endgültig lokal sortiert
        "votes": "vote_count.desc",
    }.get(sort, "popularity.desc")
    return p


def _fsk_set(f: dict[str, Any]) -> set[int]:
    """Erlaubte FSK-Werte: explizite Liste (fsk) oder Obergrenze (fsk_max)."""
    if f.get("fsk"):
        return {int(x) for x in f["fsk"]}
    if f.get("fsk_max") not in (None, ""):
        return {v for v in (0, 6, 12, 16, 18) if v <= int(f["fsk_max"])}
    return set()


def _passes_local(t: dict[str, Any], f: dict[str, Any]) -> bool:
    imdb_min = f.get("imdb_min")
    if imdb_min:
        if t.get("imdb_rating") is None or t["imdb_rating"] < float(imdb_min):
            return False
    fsk = _fsk_set(f)
    if fsk:
        v = titles.fsk_value(t.get("certification"))
        if v not in fsk and not (f.get("adult") and v is None):
            return False  # im Adult-Modus fehlt die FSK oft, dann nicht ausschließen
    want = {str(x).lower() for x in (f.get("languages") or [])}
    if want:
        langs = titles.offer_languages(t.get("availability") or {}, f.get("availability") or "mine")
        if langs is not None and not (want & set(langs)):
            return False  # ohne Sprachdaten (JustWatch) nicht ausschließen
    if f.get("hide_seen", True):
        u = t.get("user") or {}
        if u.get("status") in ("watched", "disliked", "dropped"):
            return False
    if f.get("runtime_min") and t.get("runtime") and t["runtime"] < int(f["runtime_min"]):
        return False  # lokal auch für Serien (Folgenlänge); ohne Laufzeitangabe nicht ausschließen
    excl_c = {str(x).upper() for x in (f.get("exclude_countries") or [])}
    if excl_c and excl_c & {str(c).upper() for c in (t.get("origin_countries") or [])}:
        return False  # Produktionsland ausgeschlossen (ohne Länderangabe nicht ausschließen)
    if f.get("hide_listed"):
        u = t.get("user") or {}
        if u.get("status") in ("watchlist", "watching"):
            return False  # bereits auf der Watchlist bzw. verfolgte Serie
    if t.get("blocked_by"):
        return False  # Hauptrolle einer Person aus "Nicht mein Fall"
    if (f.get("availability") or "mine") == "mine":
        av = t.get("availability") or {}
        if not av.get("mine"):
            return False
    return True


def _passes_search(t: dict[str, Any], f: dict[str, Any]) -> bool:
    """Filter, die Discover sonst TMDB überlässt – bei der Suche lokal angewandt (Jahr, Genre, Land, Stimmen,
    Bewertung, Originalsprache, Verfügbarkeitsart)."""
    y = t.get("year")
    if f.get("year_from") and (y is None or y < int(f["year_from"])):
        return False
    if f.get("year_to") and (y is None or y > int(f["year_to"])):
        return False
    gids = set(t.get("genre_ids") or [])
    if f.get("genres") and not (gids & {int(g) for g in f["genres"]}):
        return False
    if f.get("exclude_genres") and gids & {int(g) for g in f["exclude_genres"]}:
        return False
    if f.get("countries"):
        want = {str(c).upper() for c in f["countries"]}
        if not (want & {str(c).upper() for c in (t.get("origin_countries") or [])}):
            return False
    if f.get("language") and t.get("original_language") != f["language"]:
        return False
    if f.get("tmdb_min") and (t.get("tmdb_rating") or 0) < float(f["tmdb_min"]):
        return False
    min_votes = int(f.get("min_votes") or 0)
    if min_votes and (t.get("tmdb_votes") or 0) < min_votes:
        return False
    av = t.get("availability") or {}
    mode = f.get("availability") or "mine"
    if mode == "free" and not (av.get("free") or av.get("other_free")):
        return False
    if mode == "stream" and not (av.get("sub") or av.get("free") or av.get("other_sub") or av.get("other_free")):
        return False
    if mode == "rent" and not (av.get("rent") or av.get("buy")):
        return False
    return True  # "mine" prüft _passes_local, "any" alles


def _sort_results(results: list[dict[str, Any]], f: dict[str, Any], media_types: list[str], local_all: bool) -> None:
    """Sortierung: Discover sortiert bei TMDB vor (nur IMDb lokal), die Suche komplett lokal."""
    sort = f.get("sort") or "popularity"
    if sort == "imdb":
        results.sort(key=lambda t: (t.get("imdb_rating") or 0, t.get("imdb_votes") or 0), reverse=True)
    elif local_all and sort == "tmdb":
        results.sort(key=lambda t: (t.get("tmdb_rating") or 0, t.get("tmdb_votes") or 0), reverse=True)
    elif local_all and sort == "votes":
        results.sort(key=lambda t: t.get("tmdb_votes") or 0, reverse=True)
    elif local_all and sort in ("newest", "oldest"):
        results.sort(key=lambda t: t.get("year") or 0, reverse=(sort == "newest"))
    elif len(media_types) > 1 and sort == "popularity":
        results.sort(key=lambda t: t.get("tmdb_votes") or 0, reverse=True)


async def run_search(q: str, f: dict[str, Any]) -> dict[str, Any]:
    """Suche (TMDB-Multi-Suche) mit den Entdecken-Filtern: TMDB kennt bei der Suche keine Filter, deshalb werden die
    Treffer lokal gefiltert und wie bei Discover so lange nachgeladen, bis PAGE_SIZE Treffer zusammen sind."""
    media_types = [f["media_type"]] if f.get("media_type") in ("movie", "tv") else ["movie", "tv"]
    page = int(f.get("page") or 1)
    results: list[dict[str, Any]] = []
    exhausted = True
    last_page = page
    for p in range(page, page + MAX_PAGES_PER_CALL):
        last_page = p
        data = await tmdb.search_multi(q, p)
        hits = [r for r in data.get("results", []) if r.get("media_type") in media_types]
        for r in hits:
            titles.upsert_lite(r["media_type"], r)
        keys = [(r["media_type"], r["id"]) for r in hits]
        await titles.ensure_many(keys)
        if f.get("languages"):
            await justwatch.ensure_many(keys)
        rows = [titles.get_title(mt, tid) for mt, tid in keys]
        decorated = titles.decorate([r for r in rows if r])
        results.extend(t for t in decorated if _passes_search(t, f) and _passes_local(t, f))
        if p >= int(data.get("total_pages") or 0):
            exhausted = True
            break
        exhausted = False
        if len(results) >= PAGE_SIZE:
            break
    _sort_results(results, f, media_types, local_all=True)
    return {"results": results, "next_page": None if exhausted else last_page + 1, "page": page}


async def run(f: dict[str, Any]) -> dict[str, Any]:
    """Discover mit Nachladen mehrerer TMDB-Seiten, bis PAGE_SIZE lokale Treffer zusammen sind.
    Mit Suchbegriff (`q`) stattdessen Suche mit lokal angewandten Filtern."""
    q = (f.get("q") or "").strip()
    if q:
        return await run_search(q, f)
    media_types = [f["media_type"]] if f.get("media_type") in ("movie", "tv") else ["movie", "tv"]
    page = int(f.get("page") or 1)
    results: list[dict[str, Any]] = []
    exhausted = True
    last_page = page
    for p in range(page, page + MAX_PAGES_PER_CALL):
        last_page = p
        batch: list[tuple[str, dict[str, Any]]] = []
        more = False
        for mt in media_types:
            seen: set[int] = set()
            for params in (build_params(mt, f), *extra_region_params(mt, f)):
                data = await tmdb.discover(mt, {**params, "page": p})
                for r in data.get("results", []):
                    if r["id"] not in seen:
                        seen.add(r["id"])
                        batch.append((mt, r))
                if p < int(data.get("total_pages") or 0):
                    more = True
        for mt, r in batch:
            titles.upsert_lite(mt, r)
        keys = [(mt, r["id"]) for mt, r in batch]
        await titles.ensure_many(keys)
        if f.get("languages"):
            await justwatch.ensure_many(keys)  # Wiedergabesprachen nur bei aktivem Sprachfilter nachladen
        rows = [titles.get_title(mt, tid) for mt, tid in keys]
        decorated = titles.decorate([r for r in rows if r])
        results.extend(t for t in decorated if _passes_local(t, f))
        if not more:
            exhausted = True
            break
        exhausted = False
        if len(results) >= PAGE_SIZE:
            break
    _sort_results(results, f, media_types, local_all=False)
    return {"results": results, "next_page": None if exhausted else last_page + 1, "page": page}


async def search(q: str, page: int = 1) -> dict[str, Any]:
    data = await tmdb.search_multi(q, page)
    hits = [r for r in data.get("results", []) if r.get("media_type") in ("movie", "tv")]
    for r in hits:
        titles.upsert_lite(r["media_type"], r)
    keys = [(r["media_type"], r["id"]) for r in hits]
    await titles.ensure_many(keys)
    rows = [titles.get_title(mt, tid) for mt, tid in keys]
    return {
        "results": titles.decorate([r for r in rows if r]),
        "page": page,
        "total_pages": data.get("total_pages", 1),
    }


async def home() -> dict[str, Any]:
    """Startseite: verfügbare Watchlist, neue Staffeln, Weiterschauen, Beliebt bei meinen Anbietern."""
    watchlist = library.list_titles(status=["watchlist"])
    stale = [(t["media_type"], t["tmdb_id"]) for t in watchlist
             if not t["details_fetched"] or t["availability"] is None]
    if stale:
        await titles.ensure_many(stale[:40], providers_ttl=timedelta(days=2))
        watchlist = library.list_titles(status=["watchlist"])
    available = [t for t in watchlist if (t.get("availability") or {}).get("mine")]
    watching = library.list_titles(status=["watching"], media_type="tv")
    for t in watching:
        t["progress"] = library.series_progress(t)
    new_seasons = [t for t in watching if t["user"].get("new_season_flag")]
    # Weiterschauen: nur Serien, die gerade bei den eigenen Anbietern laufen (Abo oder kostenlos)
    continue_watching = [t for t in watching if t["progress"]["pending"] > 0 and not t["user"].get("new_season_flag")
                         and (t.get("availability") or {}).get("mine")]
    continue_watching.sort(key=lambda t: not t["progress"]["started"])
    newly_available = [t for t in watchlist + watching if t["user"].get("newly_available")]
    upcoming = sorted([t for t in watching if t.get("next_episode_air")], key=lambda t: t["next_episode_air"])[:12]

    popular: list[dict[str, Any]] = []
    try:
        pop = await run({"availability": "mine", "sort": "popularity", "hide_seen": True, "page": 1, "min_votes": 200})
        popular = pop["results"][:20]
    except tmdb.TMDBError:
        pass
    from_people = []
    try:
        pn = people.new_from_favorites(limit=20)
        pkeys = [(c["media_type"], c["tmdb_id"]) for c in pn]
        await titles.ensure_many(pkeys[:20])
        prow = {(t["media_type"], t["tmdb_id"]): t for t in titles.decorate([r for r in (titles.get_title(*k) for k in pkeys) if r])}
        for c in pn:
            t = prow.get((c["media_type"], c["tmdb_id"]))
            if t and (t.get("user") or {}).get("status") not in ("watched", "disliked", "dropped") and not t.get("blocked_by"):
                from_people.append({**t, "people": c["people"], "date": c.get("date")})
    except tmdb.TMDBError:
        pass
    return {
        "available_watchlist": available[:30],
        "newly_available": newly_available[:30],
        "from_people": from_people[:20],
        "new_seasons": new_seasons,
        "continue_watching": continue_watching[:20],
        "upcoming": upcoming,
        "popular": popular,
        "counts": {"watchlist": len(watchlist), "available": len(available), "watching": len(watching)},
    }


async def for_you(limit: int = 30) -> list[dict[str, Any]]:
    """Einfache Empfehlungen: TMDB-Recommendations zu den bestbewerteten eigenen Titeln, gefiltert auf eigene Anbieter."""
    liked = db.query("SELECT media_type, tmdb_id FROM user_titles WHERE rating >= 8 ORDER BY rated_at DESC LIMIT 25")
    if not liked:
        return []
    seen = {(r["media_type"], r["tmdb_id"]) for r in db.query("SELECT media_type, tmdb_id FROM user_titles")}
    counter: dict[tuple[str, int], int] = {}
    lite: dict[tuple[str, int], dict[str, Any]] = {}

    async def one(r: dict[str, Any]) -> None:
        try:
            for rec in await tmdb.recommendations(r["media_type"], r["tmdb_id"]):
                key = (rec.get("media_type") or r["media_type"], rec["id"])
                if key in seen:
                    continue
                counter[key] = counter.get(key, 0) + 1
                lite[key] = rec
        except tmdb.TMDBError:
            pass

    await asyncio.gather(*(one(r) for r in liked))
    ranked = sorted(counter.items(), key=lambda kv: (kv[1], lite[kv[0]].get("vote_average") or 0), reverse=True)[:80]
    for key, _ in ranked:
        titles.upsert_lite(key[0], lite[key])
    await titles.ensure_many([k for k, _ in ranked])
    rows = [titles.get_title(*k) for k, _ in ranked]
    decorated = titles.decorate([r for r in rows if r])
    good = [t for t in decorated if (t.get("imdb_rating") or 0) >= 6.5 and not t.get("blocked_by")]
    mine = [t for t in good if (t.get("availability") or {}).get("mine")]
    picked = mine or good
    picked.sort(key=lambda t: (counter.get((t["media_type"], t["tmdb_id"]), 0), t.get("imdb_rating") or 0), reverse=True)
    return picked[:limit]

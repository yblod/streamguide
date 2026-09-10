"""JustWatch (inoffizielle GraphQL-Schnittstelle): Wiedergabe-/Untertitelsprachen je Streaming-Angebot in DE.

TMDB kennt keine Synchronfassungen. JustWatch liefert pro Angebot `audioLanguages`; die Zuordnung zum TMDB-Titel
erfolgt über die von JustWatch mitgelieferte TMDB-ID. Die Schnittstelle ist nicht offiziell dokumentiert und kann
sich ändern; Fehler werden abgefangen (dann fehlen nur die Sprachdaten)."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

import httpx

from . import db

URL = "https://apis.justwatch.com/graphql"
COUNTRY = "DE"
LANGUAGE = "de"
TTL = timedelta(days=7)
_sem = asyncio.Semaphore(4)
_client: httpx.AsyncClient | None = None

QUERY = """
query Search($country: Country!, $language: Language!, $first: Int!, $filter: TitleFilter) {
  popularTitles(country: $country, first: $first, filter: $filter) {
    edges { node {
      id objectType
      content(country: $country, language: $language) {
        title originalReleaseYear fullPath
        externalIds { imdbId tmdbId }
      }
      offers(country: $country, platform: WEB) {
        monetizationType
        package { packageId clearName technicalName }
        audioLanguages subtitleLanguages
        standardWebURL
      }
    } }
  }
}"""


def _client_get() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0),
                                    headers={"User-Agent": "Mozilla/5.0 (StreamGuide, privat)", "Content-Type": "application/json"})
    return _client


async def close() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def _norm_lang(code: str) -> str:
    return (code or "").split("-")[0].lower()


async def lookup(title: str, year: int | None, media_type: str, tmdb_id: int, imdb_id: str | None = None
                 ) -> dict[str, Any] | None:
    """Sucht den Titel bei JustWatch und gibt die DE-Angebote mit Sprachen zurück (None = nicht gefunden/Fehler)."""
    want_type = "MOVIE" if media_type == "movie" else "SHOW"
    body = {"query": QUERY, "variables": {"country": COUNTRY, "language": LANGUAGE, "first": 6,
                                          "filter": {"searchQuery": title, "objectTypes": [want_type]}}}
    async with _sem:
        try:
            r = await _client_get().post(URL, json=body)
        except httpx.HTTPError:
            return None
    if r.status_code != 200:
        return None
    try:
        edges = r.json()["data"]["popularTitles"]["edges"]
    except (KeyError, TypeError, ValueError):
        return None
    node = None
    for e in edges:
        n = e.get("node") or {}
        ext = ((n.get("content") or {}).get("externalIds") or {})
        if str(ext.get("tmdbId") or "") == str(tmdb_id) or (imdb_id and ext.get("imdbId") == imdb_id):
            node = n
            break
    if node is None:  # Fallback: Titel + Jahr
        for e in edges:
            n = e.get("node") or {}
            c = n.get("content") or {}
            if (c.get("title") or "").lower() == title.lower() and (not year or c.get("originalReleaseYear") == year):
                node = n
                break
    if node is None:
        return {"found": False, "offers": []}
    offers: dict[tuple[str, str], dict[str, Any]] = {}
    for o in node.get("offers") or []:
        pkg = o.get("package") or {}
        key = (pkg.get("clearName") or pkg.get("technicalName") or "?", (o.get("monetizationType") or "").lower())
        cur = offers.setdefault(key, {"name": key[0], "kind": key[1], "audio": set(), "subs": set(), "url": o.get("standardWebURL")})
        cur["audio"].update(_norm_lang(x) for x in (o.get("audioLanguages") or []) if x)
        cur["subs"].update(_norm_lang(x) for x in (o.get("subtitleLanguages") or []) if x)
    return {
        "found": True,
        "path": (node.get("content") or {}).get("fullPath"),
        "offers": [{"name": v["name"], "kind": v["kind"], "audio": sorted(v["audio"]), "subs": sorted(v["subs"]), "url": v["url"]}
                   for v in offers.values()],
    }


def _stale(ts: str | None) -> bool:
    if not ts:
        return True
    try:
        return datetime.fromisoformat(ts) < datetime.utcnow() - TTL
    except ValueError:
        return True


async def ensure(media_type: str, tmdb_id: int, force: bool = False) -> dict[str, Any] | None:
    """Sprachdaten für einen Titel sicherstellen (Cache in titles.jw_offers)."""
    row = db.query_one("SELECT title, original_title, year, imdb_id, jw_offers, jw_fetched_at FROM titles WHERE media_type=? AND tmdb_id=?",
                       (media_type, tmdb_id))
    if not row:
        return None
    if not force and not _stale(row.get("jw_fetched_at")):
        return db.loads(row.get("jw_offers"), None)
    data = await lookup(row.get("title") or row.get("original_title") or "", row.get("year"), media_type, tmdb_id, row.get("imdb_id"))
    if data is None:
        return db.loads(row.get("jw_offers"), None)  # Fehler: alte Daten behalten
    if not data["found"] and row.get("original_title") and row["original_title"] != row.get("title"):
        alt = await lookup(row["original_title"], row.get("year"), media_type, tmdb_id, row.get("imdb_id"))
        if alt and alt["found"]:
            data = alt
    db.execute("UPDATE titles SET jw_offers=?, jw_fetched_at=? WHERE media_type=? AND tmdb_id=?",
               (json.dumps(data), datetime.utcnow().replace(microsecond=0).isoformat(), media_type, tmdb_id))
    return data


async def ensure_many(keys: list[tuple[str, int]], force: bool = False) -> None:
    keys = list(dict.fromkeys(keys))
    if keys:
        await asyncio.gather(*(ensure(mt, tid, force) for mt, tid in keys))

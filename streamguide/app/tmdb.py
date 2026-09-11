"""Asynchroner TMDB-Client (v3) mit Ratenbegrenzung und Wiederholung."""
from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from . import db

BASE = "https://api.themoviedb.org/3"
REGION = "DE"
LANG = "de-DE"
# Zusätzliche Länder, deren Angebote (per VPN) mitgezählt werden dürfen; Auswahl in den Einstellungen.
EXTRA_REGIONS = ("GB", "US", "AT", "CH", "FR", "IT", "ES", "NL", "SE", "DK")


def extra_regions() -> list[str]:
    """In den Einstellungen gewählte Zusatzländer (ohne DE), nur erlaubte Kürzel."""
    raw = db.get_setting("extra_regions", []) or []
    return [r for r in EXTRA_REGIONS if r in {str(x).upper() for x in raw}]


def regions() -> list[str]:
    return [REGION, *extra_regions()]

_client: httpx.AsyncClient | None = None
_sem = asyncio.Semaphore(16)


class TMDBError(Exception):
    pass


class NoApiKey(TMDBError):
    pass


def api_key() -> str:
    key = db.get_setting("tmdb_api_key") or os.environ.get("TMDB_API_KEY") or ""
    return key.strip()


def _auth(params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    key = api_key()
    if not key:
        raise NoApiKey("Kein TMDB-API-Schlüssel hinterlegt (Einstellungen).")
    if key.startswith("eyJ"):  # v4 Read Access Token
        return params, {"Authorization": f"Bearer {key}"}
    return {**params, "api_key": key}, {}


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0), http2=False)
    return _client


async def close() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def request(method: str, path: str, params: dict[str, Any] | None = None,
                  json_body: dict[str, Any] | None = None, raise_404: bool = False) -> Any:
    params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    params, headers = _auth(params)
    url = f"{BASE}{path}"
    last_exc: Exception | None = None
    for attempt in range(4):
        async with _sem:
            try:
                r = await client().request(method, url, params=params, json=json_body, headers=headers)
            except httpx.HTTPError as e:  # Netzwerkfehler
                last_exc = e
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
        if r.status_code == 429:
            retry = float(r.headers.get("Retry-After", "1"))
            await asyncio.sleep(min(retry, 5.0))
            continue
        if r.status_code == 404:
            if raise_404:
                raise TMDBError("Nicht gefunden")
            return None
        if r.status_code == 401:
            raise TMDBError("TMDB: Ungültiger API-Schlüssel (401).")
        if r.status_code >= 500:
            await asyncio.sleep(0.5 * (attempt + 1))
            continue
        if r.status_code >= 400:
            try:
                msg = r.json().get("status_message", r.text)
            except Exception:
                msg = r.text
            raise TMDBError(f"TMDB {r.status_code}: {msg}")
        return r.json()
    raise TMDBError(f"TMDB nicht erreichbar: {last_exc}")


async def get(path: str, **params: Any) -> Any:
    return await request("GET", path, params)


async def post(path: str, body: dict[str, Any], **params: Any) -> Any:
    return await request("POST", path, params, json_body=body)


# ---------- Bequemlichkeits-Funktionen ----------

async def validate_key() -> dict[str, Any]:
    return await get("/configuration")


async def genres(media_type: str) -> list[dict[str, Any]]:
    data = await get(f"/genre/{media_type}/list", language=LANG)
    return data.get("genres", []) if data else []


async def watch_providers(media_type: str, region: str = REGION) -> list[dict[str, Any]]:
    data = await get(f"/watch/providers/{media_type}", watch_region=region, language=LANG)
    return data.get("results", []) if data else []


async def details(media_type: str, tmdb_id: int) -> dict[str, Any] | None:
    extra = "external_ids,watch/providers," + ("release_dates,credits" if media_type == "movie" else "content_ratings,aggregate_credits")
    return await get(f"/{media_type}/{tmdb_id}", language=LANG, append_to_response=extra)


async def providers_only(media_type: str, tmdb_id: int) -> dict[str, Any] | None:
    """Angebote je Land (TMDB-`results`, Schlüssel = Länderkürzel); None bei Fehler."""
    data = await get(f"/{media_type}/{tmdb_id}/watch/providers")
    if not data:
        return None
    return data.get("results") or {}


async def find_by_imdb(imdb_id: str) -> dict[str, Any] | None:
    return await get(f"/find/{imdb_id}", external_source="imdb_id", language=LANG)


async def search_multi(q: str, page: int = 1) -> dict[str, Any]:
    data = await get("/search/multi", query=q, page=page, language=LANG, region=REGION, include_adult="false")
    return data or {"results": [], "total_pages": 0}


async def search_single(media_type: str, q: str, year: int | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"query": q, "language": LANG, "region": REGION, "include_adult": "false"}
    if year:
        params["year" if media_type == "movie" else "first_air_date_year"] = year
    data = await get(f"/search/{media_type}", **params)
    return (data or {}).get("results", [])


async def discover(media_type: str, params: dict[str, Any]) -> dict[str, Any]:
    base = {"language": LANG, "watch_region": REGION, "include_adult": "false"}
    if media_type == "tv":
        base["include_null_first_air_dates"] = "false"
    data = await get(f"/discover/{media_type}", **{**base, **params})
    return data or {"results": [], "total_pages": 0, "page": 1}


async def trending(media_type: str, window: str = "week") -> list[dict[str, Any]]:
    data = await get(f"/trending/{media_type}/{window}", language=LANG)
    return (data or {}).get("results", [])


async def recommendations(media_type: str, tmdb_id: int) -> list[dict[str, Any]]:
    data = await get(f"/{media_type}/{tmdb_id}/recommendations", language=LANG)
    return (data or {}).get("results", [])


async def videos(media_type: str, tmdb_id: int) -> list[dict[str, Any]]:
    """YouTube-Videos (Trailer/Teaser) in Deutsch und Englisch."""
    data = await get(f"/{media_type}/{tmdb_id}/videos", language=LANG, include_video_language="de,en,null")
    return (data or {}).get("results", [])


async def season(tv_id: int, season_number: int) -> dict[str, Any] | None:
    return await get(f"/tv/{tv_id}/season/{season_number}", language=LANG)


# ---------- Account (v3 Session) ----------

async def auth_new_token() -> str:
    data = await get("/authentication/token/new")
    return data["request_token"]


async def auth_create_session(request_token: str) -> str:
    data = await post("/authentication/session/new", {"request_token": request_token})
    return data["session_id"]


async def account(session_id: str) -> dict[str, Any]:
    return await get("/account", session_id=session_id)


async def account_list(account_id: int, kind: str, media_type: str, session_id: str) -> list[dict[str, Any]]:
    """kind: watchlist | rated | favorite ; media_type: movies | tv"""
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        data = await get(f"/account/{account_id}/{kind}/{media_type}", session_id=session_id,
                         page=page, language=LANG, sort_by="created_at.desc")
        if not data:
            break
        out.extend(data.get("results", []))
        if page >= int(data.get("total_pages") or 1):
            break
        page += 1
    return out


async def account_set_watchlist(account_id: int, session_id: str, media_type: str, tmdb_id: int, on: bool) -> None:
    await post(f"/account/{account_id}/watchlist",
               {"media_type": media_type, "media_id": tmdb_id, "watchlist": on}, session_id=session_id)


async def rate(media_type: str, tmdb_id: int, session_id: str, value: float) -> None:
    await post(f"/{media_type}/{tmdb_id}/rating", {"value": max(0.5, min(10.0, float(value)))}, session_id=session_id)


async def delete_rating(media_type: str, tmdb_id: int, session_id: str) -> None:
    await request("DELETE", f"/{media_type}/{tmdb_id}/rating", {"session_id": session_id})

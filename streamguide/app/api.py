"""REST-API für das Frontend."""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel

from . import auth, backup, db, discover, imdb, jobs, justwatch, library, people, sync, titles, tmdb
from .version import VERSION

router = APIRouter(prefix="/api")

SETTING_KEYS = ("tmdb_api_key", "count_all_free", "dislike_threshold", "tmdb_mirror_watchlist", "tmdb_mirror_ratings", "theme")


def _err(e: Exception) -> HTTPException:
    if isinstance(e, tmdb.NoApiKey):
        return HTTPException(status_code=428, detail=str(e))
    if isinstance(e, tmdb.TMDBError):
        return HTTPException(status_code=502, detail=str(e))
    return HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ---------- Status / Einstellungen ----------

@router.get("/status")
async def status_endpoint(request: Request) -> dict[str, Any]:
    return await status(request)


async def status(request: Request | None = None) -> dict[str, Any]:
    s = db.all_settings()
    key = tmdb.api_key()
    return {
        "version": VERSION,
        "auth": {
            "enabled": auth.enabled(),
            "lan_without_login": auth.lan_without_login(),
            "logged_in": bool(request) and auth.logged_in(request),
            "lan": bool(request) and auth.is_lan(request),
            "tunnel": bool(request) and auth.via_tunnel(request),
        },
        "has_key": bool(key),
        "key_masked": (key[:4] + "…" + key[-4:]) if len(key) > 10 else ("•" * len(key)),
        "providers_seeded": bool(db.query_one("SELECT 1 FROM providers LIMIT 1")),
        "tmdb_connected": bool(s.get("tmdb_session_id")),
        "tmdb_username": s.get("tmdb_username"),
        "settings": {k: s.get(k) for k in SETTING_KEYS if k != "tmdb_api_key"},
        "stats": library.stats(),
        "jobs": jobs.running(),
    }


class SettingsIn(BaseModel):
    tmdb_api_key: str | None = None
    count_all_free: bool | None = None
    dislike_threshold: int | None = None
    tmdb_mirror_watchlist: bool | None = None
    tmdb_mirror_ratings: bool | None = None
    theme: str | None = None


@router.put("/settings")
async def put_settings(body: SettingsIn) -> dict[str, Any]:
    if body.tmdb_api_key is not None:
        key = body.tmdb_api_key.strip()
        if key:
            db.set_setting("tmdb_api_key", key)
            try:
                await tmdb.validate_key()
                await sync.bootstrap()
            except tmdb.TMDBError as e:
                db.set_setting("tmdb_api_key", "")
                raise HTTPException(status_code=400, detail=f"Schlüssel ungültig: {e}")
        else:
            db.set_setting("tmdb_api_key", "")
    for k in ("count_all_free", "dislike_threshold", "tmdb_mirror_watchlist", "tmdb_mirror_ratings", "theme"):
        v = getattr(body, k)
        if v is not None:
            db.set_setting(k, v)
    return await status()


@router.get("/providers")
async def get_providers(all: bool = False) -> list[dict[str, Any]]:
    try:
        await sync.seed_providers()
    except tmdb.TMDBError as e:
        raise _err(e)
    rows = db.query("SELECT * FROM providers ORDER BY active DESC, display_priority ASC, name ASC")
    for r in rows:
        r["active"] = bool(r["active"])
        r["media_types"] = db.loads(r["media_types"], [])
    return rows if all else rows[:120]


class ProviderToggle(BaseModel):
    active: bool


@router.put("/providers/{provider_id}")
async def toggle_provider(provider_id: int, body: ProviderToggle) -> dict[str, Any]:
    db.execute("UPDATE providers SET active=? WHERE id=?", (1 if body.active else 0, provider_id))
    sync.check_new_seasons()
    return {"ok": True}


@router.post("/providers/refresh")
async def refresh_providers() -> dict[str, Any]:
    try:
        n = await sync.seed_providers(force=True)
        await sync.seed_genres(force=True)
    except tmdb.TMDBError as e:
        raise _err(e)
    return {"providers": n}


@router.get("/genres")
async def get_genres() -> dict[str, list[dict[str, Any]]]:
    try:
        await sync.seed_genres()
    except tmdb.TMDBError:
        pass
    out: dict[str, list[dict[str, Any]]] = {"movie": [], "tv": []}
    for r in db.query("SELECT id, media_type, name FROM genres ORDER BY name"):
        out[r["media_type"]].append({"id": r["id"], "name": r["name"]})
    return out


# ---------- Entdecken / Suche / Start ----------

@router.get("/home")
async def home() -> dict[str, Any]:
    try:
        return await discover.home()
    except tmdb.TMDBError as e:
        raise _err(e)


@router.get("/search")
async def search(q: str = Query(min_length=1), page: int = 1) -> dict[str, Any]:
    try:
        return await discover.search(q, page)
    except tmdb.TMDBError as e:
        raise _err(e)


class DiscoverIn(BaseModel):
    media_type: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    genres: list[int] = []
    exclude_genres: list[int] = []
    countries: list[str] = []
    exclude_countries: list[str] = []
    language: str | None = None
    languages: list[str] = []
    imdb_min: float | None = None
    tmdb_min: float | None = None
    fsk_max: int | None = None
    fsk: list[int] = []
    adult: bool = False
    availability: str = "mine"
    sort: str = "popularity"
    hide_seen: bool = True
    hide_listed: bool = False
    min_votes: int | None = None
    runtime_min: int | None = None
    page: int = 1


@router.post("/discover")
async def post_discover(body: DiscoverIn) -> dict[str, Any]:
    try:
        return await discover.run(body.model_dump())
    except tmdb.TMDBError as e:
        raise _err(e)


@router.get("/for-you")
async def for_you() -> dict[str, Any]:
    try:
        return {"results": await discover.for_you()}
    except tmdb.TMDBError as e:
        raise _err(e)


# ---------- Titel ----------

@router.get("/title/{media_type}/{tmdb_id}")
async def get_title(media_type: str, tmdb_id: int, refresh: bool = False) -> dict[str, Any]:
    if media_type not in ("movie", "tv"):
        raise HTTPException(status_code=400, detail="media_type muss movie oder tv sein")
    try:
        row = await titles.ensure_title(media_type, tmdb_id, force=refresh, providers_ttl=timedelta(hours=12))
    except tmdb.TMDBError as e:
        raise _err(e)
    if not row:
        raise HTTPException(status_code=404, detail="Titel nicht gefunden")
    if not refresh:
        library.clear_new_flags(media_type, tmdb_id)
    try:
        await justwatch.ensure(media_type, tmdb_id, force=refresh)
        row = titles.get_title(media_type, tmdb_id) or row
    except Exception:  # noqa: BLE001 - Sprachdaten sind optional
        pass
    t = titles.decorate([row])[0]
    if media_type == "tv":
        t["progress"] = library.series_progress(t)
    return t


@router.get("/title/{media_type}/{tmdb_id}/videos")
async def get_videos(media_type: str, tmdb_id: int) -> dict[str, Any]:
    """Bester Trailer (YouTube): deutsch vor englisch, Trailer vor Teaser, offizielle zuerst."""
    if media_type not in ("movie", "tv"):
        raise HTTPException(status_code=400, detail="media_type muss movie oder tv sein")
    try:
        vids = await tmdb.videos(media_type, tmdb_id)
    except tmdb.TMDBError as e:
        raise _err(e)
    yt = [v for v in vids if (v.get("site") or "").lower() == "youtube" and v.get("key")]
    type_rank = {"Trailer": 0, "Teaser": 1, "Clip": 2, "Featurette": 3, "Opening Credits": 4}
    lang_rank = {"de": 0, "en": 1}

    def rank(v: dict[str, Any]) -> tuple:
        return (lang_rank.get((v.get("iso_639_1") or "").lower(), 2), type_rank.get(v.get("type"), 9),
                0 if v.get("official") else 1, v.get("published_at") or "")

    yt.sort(key=rank)
    out = [{"key": v["key"], "name": v.get("name"), "type": v.get("type"), "lang": v.get("iso_639_1"), "official": bool(v.get("official"))} for v in yt]
    return {"best": out[0] if out else None, "videos": out[:10]}


@router.get("/title/tv/{tmdb_id}/season/{season_number}")
async def get_season(tmdb_id: int, season_number: int) -> dict[str, Any]:
    try:
        s = await tmdb.season(tmdb_id, season_number)
    except tmdb.TMDBError as e:
        raise _err(e)
    if not s:
        raise HTTPException(status_code=404, detail="Staffel nicht gefunden")
    return {
        "season_number": s.get("season_number"), "name": s.get("name"), "overview": s.get("overview"),
        "air_date": s.get("air_date"),
        "episodes": [{"episode_number": e.get("episode_number"), "name": e.get("name"), "air_date": e.get("air_date"),
                      "runtime": e.get("runtime"), "overview": e.get("overview"), "still_path": e.get("still_path"),
                      "vote_average": e.get("vote_average")} for e in s.get("episodes", [])],
    }


# ---------- Bibliothek ----------

@router.get("/library")
async def get_library(status: str | None = None, media_type: str | None = None, sort: str = "added") -> dict[str, Any]:
    sts = status.split(",") if status else None
    items = library.list_titles(sts, media_type, sort)
    for t in items:
        if t["media_type"] == "tv":
            t["progress"] = library.series_progress(t)
    return {"results": items, "count": len(items)}


class StatusIn(BaseModel):
    status: str
    rating: int | None = None


@router.put("/library/{media_type}/{tmdb_id}/status")
async def put_status(media_type: str, tmdb_id: int, body: StatusIn) -> dict[str, Any]:
    try:
        existing = library.get_entry(media_type, tmdb_id)
        was_watchlist = bool(existing and existing["status"] == "watchlist")
        if not titles.get_title(media_type, tmdb_id):
            await titles.ensure_title(media_type, tmdb_id)
        rating = body.rating
        if body.status == "disliked" and rating is None and not (existing and existing["rating"] is not None):
            rating = int(db.get_setting("dislike_threshold", 1))  # Konvention: 1 = kein Interesse
        entry = library.set_status(media_type, tmdb_id, body.status, rating=rating)
        if body.status == "watchlist" and not was_watchlist:
            asyncio.create_task(sync.push_watchlist(media_type, tmdb_id, True))
        elif was_watchlist and body.status != "watchlist":
            asyncio.create_task(sync.push_watchlist(media_type, tmdb_id, False))
        if rating is not None and not (existing and existing["rating"] == rating):
            asyncio.create_task(sync.push_rating(media_type, tmdb_id, rating))
    except (ValueError, tmdb.TMDBError) as e:
        raise _err(e) if isinstance(e, tmdb.TMDBError) else HTTPException(status_code=400, detail=str(e))
    return await get_title(media_type, tmdb_id)


class RatingIn(BaseModel):
    rating: int | None


@router.put("/library/{media_type}/{tmdb_id}/rating")
async def put_rating(media_type: str, tmdb_id: int, body: RatingIn) -> dict[str, Any]:
    if body.rating is not None and not (1 <= body.rating <= 10):
        raise HTTPException(status_code=400, detail="Bewertung 1–10")
    if not titles.get_title(media_type, tmdb_id):
        try:
            await titles.ensure_title(media_type, tmdb_id)
        except tmdb.TMDBError as e:
            raise _err(e)
    library.set_rating(media_type, tmdb_id, body.rating)
    asyncio.create_task(sync.push_rating(media_type, tmdb_id, body.rating))
    return await get_title(media_type, tmdb_id)


class SeasonsIn(BaseModel):
    watched_seasons: list[int]


@router.put("/library/tv/{tmdb_id}/seasons")
async def put_seasons(tmdb_id: int, body: SeasonsIn) -> dict[str, Any]:
    if not titles.get_title("tv", tmdb_id):
        try:
            await titles.ensure_title("tv", tmdb_id)
        except tmdb.TMDBError as e:
            raise _err(e)
    library.set_seasons("tv", tmdb_id, body.watched_seasons)
    return await get_title("tv", tmdb_id)


class EpisodeIn(BaseModel):
    season: int
    episode: int
    watched: bool = True
    up_to: bool = False


@router.put("/library/tv/{tmdb_id}/episode")
async def put_episode(tmdb_id: int, body: EpisodeIn) -> dict[str, Any]:
    if not titles.get_title("tv", tmdb_id):
        try:
            await titles.ensure_title("tv", tmdb_id)
        except tmdb.TMDBError as e:
            raise _err(e)
    library.mark_episode(tmdb_id, body.season, body.episode, body.watched, body.up_to)
    return await get_title("tv", tmdb_id)


class SeasonIn(BaseModel):
    season: int
    watched: bool = True
    include_previous: bool = True


@router.put("/library/tv/{tmdb_id}/season")
async def put_season(tmdb_id: int, body: SeasonIn) -> dict[str, Any]:
    if not titles.get_title("tv", tmdb_id):
        try:
            await titles.ensure_title("tv", tmdb_id)
        except tmdb.TMDBError as e:
            raise _err(e)
    library.mark_season(tmdb_id, body.season, body.watched, body.include_previous)
    return await get_title("tv", tmdb_id)


@router.post("/library/tv/{tmdb_id}/complete")
async def post_complete(tmdb_id: int) -> dict[str, Any]:
    if not titles.get_title("tv", tmdb_id):
        try:
            await titles.ensure_title("tv", tmdb_id)
        except tmdb.TMDBError as e:
            raise _err(e)
    library.mark_all_watched(tmdb_id)
    return await get_title("tv", tmdb_id)


@router.delete("/library/{media_type}/{tmdb_id}")
async def delete_entry(media_type: str, tmdb_id: int) -> dict[str, Any]:
    existing = library.get_entry(media_type, tmdb_id)
    library.remove(media_type, tmdb_id)
    if existing and existing["status"] == "watchlist":
        asyncio.create_task(sync.push_watchlist(media_type, tmdb_id, False))
    if existing and existing["rating"] is not None:
        asyncio.create_task(sync.push_rating(media_type, tmdb_id, None))  # Bewertung auch bei TMDB löschen
    return await get_title(media_type, tmdb_id)


# ---------- Personen ----------

@router.get("/people/search")
async def people_search(q: str = Query(min_length=1)) -> dict[str, Any]:
    try:
        return {"results": await people.search(q)}
    except tmdb.TMDBError as e:
        raise _err(e)


@router.get("/people/trending")
async def people_trending() -> dict[str, Any]:
    try:
        return {"results": await people.trending()}
    except tmdb.TMDBError as e:
        raise _err(e)


@router.get("/people/favorites")
async def people_favorites() -> dict[str, Any]:
    return {"results": people.favorites()}


@router.get("/people/new")
async def people_new() -> dict[str, Any]:
    items = people.new_from_favorites()
    keys = [(c["media_type"], c["tmdb_id"]) for c in items[:30]]
    try:
        await titles.ensure_many(keys)
    except tmdb.TMDBError:
        pass
    rows = [titles.get_title(mt, tid) for mt, tid in keys]
    decorated = {(t["media_type"], t["tmdb_id"]): t for t in titles.decorate([r for r in rows if r])}
    out = []
    for c in items[:30]:
        t = decorated.get((c["media_type"], c["tmdb_id"]))
        if t and not t.get("blocked_by"):
            out.append({**t, "people": c["people"], "date": c.get("date")})
    return {"results": out}


@router.get("/people/blocked")
async def people_blocked() -> dict[str, Any]:
    return {"results": people.blocked()}


class BlockedIn(BaseModel):
    blocked: bool


@router.put("/people/{person_id}/blocked")
async def person_blocked(person_id: int, body: BlockedIn) -> dict[str, Any]:
    if not people.get(person_id):
        try:
            await people.ensure(person_id)
        except tmdb.TMDBError as e:
            raise _err(e)
    people.set_blocked(person_id, body.blocked)
    if body.blocked:
        people.set_favorite(person_id, False)  # Favorit und gesperrt schließen sich aus
    row = people.get(person_id)
    return people.decorate_person(row, with_credits=False) if row else {"id": person_id, "blocked": body.blocked}


@router.get("/people/{person_id}")
async def person_detail(person_id: int, refresh: bool = False) -> dict[str, Any]:
    try:
        row = await people.ensure(person_id, force=refresh)
    except tmdb.TMDBError as e:
        raise _err(e)
    if not row:
        raise HTTPException(status_code=404, detail="Person nicht gefunden")
    # Hauptrollen ohne vollständige Titeldaten nachladen (IMDb-ID → IMDb-Bewertung, Verfügbarkeit, Status)
    credits = db.loads(row.get("credits"), []) or []
    main_keys = [(c["media_type"], c["tmdb_id"]) for c in credits if people.is_main_role(c)]
    missing = []
    for mt, tid in main_keys:
        t = titles.get_title(mt, tid)
        if not t or not t.get("details_fetched_at"):
            missing.append((mt, tid))
    if missing:
        try:
            await titles.ensure_many(missing[:60], providers_ttl=timedelta(days=30))
        except tmdb.TMDBError:
            pass
    return people.decorate_person(row)


class FavoriteIn(BaseModel):
    favorite: bool


@router.put("/people/{person_id}/favorite")
async def person_favorite(person_id: int, body: FavoriteIn) -> dict[str, Any]:
    if body.favorite and not people.get(person_id):
        try:
            await people.ensure(person_id)
        except tmdb.TMDBError as e:
            raise _err(e)
    people.set_favorite(person_id, body.favorite)
    if body.favorite:
        try:
            await people.ensure(person_id)
        except tmdb.TMDBError:
            pass
    row = people.get(person_id)
    return people.decorate_person(row, with_credits=False) if row else {"id": person_id, "favorite": body.favorite}


@router.post("/people/import")
async def people_import(file: UploadFile = File(...)) -> dict[str, Any]:
    """IMDb-Listen-Export (Spalten Const=nm…, Name) als Favoriten importieren."""
    if not tmdb.api_key():
        raise HTTPException(status_code=428, detail="Zuerst TMDB-API-Schlüssel hinterlegen.")
    content = await file.read()
    rows = imdb.parse_people_export(content)
    if not rows:
        raise HTTPException(status_code=400, detail="Keine Personen (Spalte 'Const' mit nm…) gefunden.")

    async def work(job: jobs.Job) -> None:
        stats = {"imported": 0, "existing": 0, "unmatched": 0}
        job.update(0, len(rows), "Schauspieler werden zugeordnet …")
        sem = asyncio.Semaphore(8)
        done = 0

        async def one(r: dict[str, Any]) -> None:
            nonlocal done
            async with sem:
                try:
                    pid = await people.resolve_imdb(r["imdb_id"])
                except tmdb.TMDBError:
                    pid = None
                if pid is None:
                    stats["unmatched"] += 1
                    db.execute("INSERT INTO import_log(job_id,source,ref,title,result) VALUES(?,?,?,?,?)",
                               (job.id, "imdb_people", r["imdb_id"], r["name"], "nicht bei TMDB gefunden"))
                elif pid in people.favorite_ids():
                    stats["existing"] += 1
                else:
                    people.set_favorite(pid, True, source="imdb")
                    stats["imported"] += 1
                done += 1
                job.update(done, len(rows), f"{done}/{len(rows)} zugeordnet")

        await asyncio.gather(*(one(r) for r in rows))
        job.update(done, len(rows), "Filmografien werden geladen …")
        await people.ensure_many(sorted(people.favorite_ids()))
        job.result = stats
        job.update(len(rows), len(rows), f"Fertig: {stats['imported']} neu, {stats['existing']} vorhanden, {stats['unmatched']} nicht gefunden")

    try:
        job = jobs.start("import_people", work)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"job_id": job.id, "rows": len(rows)}


# ---------- Importe / Jobs ----------

@router.post("/import/imdb")
async def import_imdb(file: UploadFile = File(...), mode: str = Form("ratings")) -> dict[str, Any]:
    if mode not in ("ratings", "watchlist"):
        raise HTTPException(status_code=400, detail="mode: ratings | watchlist")
    if not tmdb.api_key():
        raise HTTPException(status_code=428, detail="Zuerst TMDB-API-Schlüssel hinterlegen.")
    content = await file.read()
    try:
        preview = imdb.parse_export(content)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"CSV nicht lesbar: {e}")
    if not preview:
        raise HTTPException(status_code=400, detail="Keine IMDb-Einträge (Spalte 'Const') gefunden.")
    try:
        job = jobs.start("import_imdb", lambda j: sync.import_imdb_csv(j, content, mode))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"job_id": job.id, "rows": len(preview)}


class ListImportIn(BaseModel):
    text: str
    status: str = "watchlist"
    media_type: str | None = None


@router.post("/import/list")
async def import_list(body: ListImportIn) -> dict[str, Any]:
    if body.status not in library.STATUSES:
        raise HTTPException(status_code=400, detail="Ungültiger Status")
    if not tmdb.api_key():
        raise HTTPException(status_code=428, detail="Zuerst TMDB-API-Schlüssel hinterlegen.")
    try:
        job = jobs.start("import_list", lambda j: sync.import_title_list(j, body.text, body.status, body.media_type))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"job_id": job.id}


@router.post("/imdb/dataset")
async def update_imdb_dataset() -> dict[str, Any]:
    async def work(job: jobs.Job) -> None:
        loop = asyncio.get_running_loop()

        def progress(got: int, total: int, msg: str) -> None:
            loop.call_soon_threadsafe(job.update, got, total, msg)

        n = await asyncio.to_thread(imdb.download_ratings_dataset, progress)
        job.result = {"rows": n}
        job.update(n, n, f"Fertig: {n:,} IMDb-Bewertungen")

    try:
        job = jobs.start("imdb_dataset", work)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"job_id": job.id}


@router.post("/library/refresh")
async def refresh_library(only_series: bool = False, everything: bool = False) -> dict[str, Any]:
    if not tmdb.api_key():
        raise HTTPException(status_code=428, detail="Zuerst TMDB-API-Schlüssel hinterlegen.")
    try:
        job = jobs.start("refresh_library", lambda j: sync.refresh_library(j, only_series, everything))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"job_id": job.id}


@router.get("/jobs")
async def get_jobs() -> dict[str, Any]:
    return {"running": jobs.running(), "recent": jobs.recent(8)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    row = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Job nicht gefunden")
    row["result"] = db.loads(row.get("result"), {})
    row["log"] = db.query("SELECT ref, title, result FROM import_log WHERE job_id=? ORDER BY id LIMIT 300", (job_id,))
    return row


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str) -> dict[str, Any]:
    return {"cancelled": jobs.cancel(job_id)}


# ---------- TMDB-Konto ----------

@router.post("/tmdb/auth/start")
async def tmdb_auth_start(request: Request) -> dict[str, Any]:
    try:
        token = await tmdb.auth_new_token()
    except tmdb.TMDBError as e:
        raise _err(e)
    db.set_setting("tmdb_request_token", token)
    # Hinter dem Cloudflare-Tunnel kommt die Anfrage per http an, der Browser spricht aber https.
    base = str(request.base_url).rstrip("/")
    if auth.is_https(request) and base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    redirect = base + "/api/tmdb/auth/callback"
    return {"approve_url": f"https://www.themoviedb.org/authenticate/{token}?redirect_to={redirect}"}


@router.get("/tmdb/auth/callback")
async def tmdb_auth_callback(request_token: str | None = None, approved: str | None = None) -> Any:
    token = request_token or db.get_setting("tmdb_request_token")
    if not token or approved == "false":
        return HTMLResponse("<p>Verbindung abgelehnt. Du kannst dieses Fenster schließen.</p>")
    try:
        sid = await tmdb.auth_create_session(token)
        acc = await tmdb.account(sid)
    except tmdb.TMDBError as e:
        return HTMLResponse(f"<p>Fehler: {e}</p>", status_code=400)
    db.set_setting("tmdb_session_id", sid)
    db.set_setting("tmdb_account_id", acc["id"])
    db.set_setting("tmdb_username", acc.get("username"))
    return RedirectResponse(url="/#/settings?tmdb=connected")


@router.post("/tmdb/auth/finish")
async def tmdb_auth_finish() -> dict[str, Any]:
    """Fallback, wenn der Redirect nicht funktioniert hat: Session aus dem gespeicherten Token erzeugen."""
    token = db.get_setting("tmdb_request_token")
    if not token:
        raise HTTPException(status_code=400, detail="Kein Anfrage-Token vorhanden.")
    try:
        sid = await tmdb.auth_create_session(token)
        acc = await tmdb.account(sid)
    except tmdb.TMDBError as e:
        raise _err(e)
    db.set_setting("tmdb_session_id", sid)
    db.set_setting("tmdb_account_id", acc["id"])
    db.set_setting("tmdb_username", acc.get("username"))
    return {"username": acc.get("username")}


@router.delete("/tmdb/auth")
async def tmdb_auth_disconnect() -> dict[str, Any]:
    for k in ("tmdb_session_id", "tmdb_account_id", "tmdb_username", "tmdb_request_token"):
        db.set_setting(k, None)
    return {"ok": True}


@router.post("/tmdb/sync")
async def tmdb_sync() -> dict[str, Any]:
    if not sync.tmdb_session():
        raise HTTPException(status_code=428, detail="Kein TMDB-Konto verbunden.")
    try:
        job = jobs.start("tmdb_sync", sync.sync_tmdb_account)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"job_id": job.id}


@router.get("/import/log")
async def import_log(limit: int = 200) -> list[dict[str, Any]]:
    return db.query("SELECT * FROM import_log ORDER BY id DESC LIMIT ?", (limit,))


@router.get("/export")
async def export_library() -> dict[str, Any]:
    rows = db.query("SELECT u.*, t.title, t.year, t.imdb_id FROM user_titles u "
                    "LEFT JOIN titles t ON t.media_type=u.media_type AND t.tmdb_id=u.tmdb_id ORDER BY u.added_at")
    for r in rows:
        r["watched_seasons"] = db.loads(r["watched_seasons"], [])
    return {"exported_at": titles.now_iso(), "items": rows}


@router.post("/export/restore")
async def restore_library(body: dict[str, Any]) -> dict[str, Any]:
    items = body.get("items") or []
    n = 0
    for r in items:
        try:
            library.set_status(r["media_type"], int(r["tmdb_id"]), r["status"], rating=r.get("rating"),
                               rated_at=r.get("rated_at"), source=r.get("source") or "restore",
                               watched_seasons=r.get("watched_seasons") or [])
            n += 1
        except (KeyError, ValueError):
            continue
    return {"restored": n}


# ---------- Sicherung (ZIP mit Datenbank) ----------

BACKUP_DIR = db.DATA_DIR / "backups"


def _prune_backup_files(keep: int = 3) -> None:
    files = sorted(BACKUP_DIR.glob("streamguide-backup-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files[keep:]:
        try:
            p.unlink()
        except OSError:
            pass


@router.get("/backup")
async def download_backup(background: BackgroundTasks) -> FileResponse:
    """Erzeugt eine ZIP-Sicherung (Datenbank ohne IMDb-Datensatz) und liefert sie zum Download."""
    name = f"streamguide-backup-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    dest = BACKUP_DIR / name
    try:
        await asyncio.to_thread(backup.export_live, dest, VERSION)
    except Exception as e:  # noqa: BLE001
        raise _err(e)
    background.add_task(_prune_backup_files)
    return FileResponse(dest, media_type="application/zip", filename=name)


@router.post("/backup/restore")
async def restore_backup(file: UploadFile = File(...)) -> dict[str, Any]:
    """Ersetzt die Datenbank durch eine hochgeladene Sicherung (ZIP aus /api/backup oder tools/export_pc_data.py)."""
    if jobs.running():
        raise HTTPException(status_code=409, detail="Bitte warten, bis laufende Jobs beendet sind.")
    tmp_dir = Path(tempfile.mkdtemp(prefix="sg-upload-"))
    try:
        zip_path = tmp_dir / "upload.zip"
        with open(zip_path, "wb") as out:
            shutil.copyfileobj(file.file, out)
        try:
            result = await asyncio.to_thread(backup.restore, zip_path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:  # noqa: BLE001
            raise _err(e)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return result

"""FastAPI-App: API + statisches Frontend + Login (Home-Assistant-Add-on-Version)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import api, auth, db, imdb, jobs, justwatch, sync, tmdb
from .version import VERSION

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"


async def _auto_tasks() -> None:
    """Nach dem Start: IMDb-Datensatz aktualisieren, wenn älter als 7 Tage; Serien prüfen."""
    await asyncio.sleep(3)
    updated = db.get_setting("imdb_dataset_updated")
    stale = True
    if updated:
        try:
            stale = datetime.fromisoformat(updated) < datetime.utcnow() - timedelta(days=7)
        except ValueError:
            stale = True
    if stale:
        async def work(job: jobs.Job) -> None:
            loop = asyncio.get_running_loop()
            n = await asyncio.to_thread(
                imdb.download_ratings_dataset,
                lambda got, total, msg: loop.call_soon_threadsafe(job.update, got, total, msg))
            job.result = {"rows": n}
            job.update(n, n, f"Fertig: {n:,} IMDb-Bewertungen")
        try:
            jobs.start("imdb_dataset", work)
        except RuntimeError:
            pass
    if tmdb.api_key() and db.query_one("SELECT 1 FROM user_titles WHERE status IN ('watching','watchlist') LIMIT 1"):
        try:
            jobs.start("refresh_library", lambda j: sync.refresh_library(j))
        except RuntimeError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect()
    jobs.mark_orphans()
    print(f"StreamGuide {VERSION} – Daten in {db.DATA_DIR} – Login {'aktiv' if auth.enabled() else 'aus'}"
          f"{' (Heimnetz ohne Login)' if auth.enabled() and auth.lan_without_login() else ''}", flush=True)
    task = asyncio.create_task(_auto_tasks())
    yield
    task.cancel()
    await tmdb.close()
    await justwatch.close()


app = FastAPI(title="StreamGuide", version=VERSION, lifespan=lifespan)
app.include_router(api.router)
# Frontend-Dateien zusätzlich unter einem versionierten Pfad: index.html verweist auf /static/v<Version>/…,
# damit Browser (v. a. Safari mit ES-Modulen) nach einem Update garantiert frische Dateien laden.
STATIC_VERSIONED = f"/static/v{VERSION}"
app.mount(STATIC_VERSIONED, StaticFiles(directory=STATIC), name="static_versioned")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def guard_and_cache(request: Request, call_next):
    """Login erzwingen (außer öffentliche Pfade) und Frontend-Dateien immer revalidieren lassen."""
    if not auth.allowed(request):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Nicht angemeldet."}, status_code=401)
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(url=f"/login?next={target}", status_code=303)
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/", include_in_schema=False)
async def index() -> HTMLResponse:
    html = (STATIC / "index.html").read_text(encoding="utf-8").replace('"/static/', f'"{STATIC_VERSIONED}/')
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/health", include_in_schema=False)
async def health() -> dict:
    return {"ok": True, "version": VERSION}


@app.get("/login", include_in_schema=False)
async def login_form(request: Request, next: str | None = None):
    if not auth.enabled() or auth.logged_in(request) or (auth.lan_without_login() and auth.is_lan(request)):
        return RedirectResponse(url=auth.safe_next(next), status_code=303)
    return auth.login_page(auth.safe_next(next))


@app.post("/login", include_in_schema=False)
async def login_submit(request: Request, password: str = Form(""), next: str = Form("/")):
    ok = auth.enabled() and auth.check_password(password)
    await auth.throttle(ok)
    if not ok:
        return auth.login_page(auth.safe_next(next), "Falsches Passwort.")
    resp = RedirectResponse(url=auth.safe_next(next), status_code=303)
    resp.set_cookie(auth.COOKIE, auth.make_token(), max_age=auth.SESSION_DAYS * 86400, httponly=True,
                    samesite="lax", secure=auth.is_https(request), path="/")
    return resp


@app.get("/logout", include_in_schema=False)
@app.post("/logout", include_in_schema=False)
async def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp

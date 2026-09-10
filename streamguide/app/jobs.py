"""Hintergrund-Jobs (asyncio-Tasks) mit Fortschritt in der DB."""
from __future__ import annotations

import asyncio
import json
import traceback
import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable

from . import db

_tasks: dict[str, asyncio.Task] = {}


class Job:
    def __init__(self, kind: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.progress = 0
        self.total = 0
        self.message = ""
        self.result: dict[str, Any] = {}
        db.execute("INSERT INTO jobs(id,kind,status,message) VALUES(?,?,?,?)", (self.id, kind, "running", ""))

    def update(self, progress: int | None = None, total: int | None = None, message: str | None = None) -> None:
        if progress is not None:
            self.progress = progress
        if total is not None:
            self.total = total
        if message is not None:
            self.message = message
        db.execute("UPDATE jobs SET progress=?, total=?, message=? WHERE id=?",
                   (self.progress, self.total, self.message, self.id))

    def finish(self, status: str, message: str | None = None) -> None:
        db.execute("UPDATE jobs SET status=?, message=?, result=?, finished_at=? WHERE id=?",
                   (status, message if message is not None else self.message, json.dumps(self.result),
                    datetime.utcnow().replace(microsecond=0).isoformat(), self.id))


def running(kind: str | None = None) -> list[dict[str, Any]]:
    rows = db.query("SELECT * FROM jobs WHERE status='running' ORDER BY started_at DESC")
    return [r for r in rows if kind is None or r["kind"] == kind]


def start(kind: str, coro_factory: Callable[[Job], Awaitable[None]], single: bool = True) -> Job:
    if single:
        for r in running(kind):
            if r["id"] in _tasks and not _tasks[r["id"]].done():
                raise RuntimeError(f"Ein Job vom Typ '{kind}' läuft bereits.")
    job = Job(kind)

    async def runner() -> None:
        try:
            await coro_factory(job)
            job.finish("done")
        except asyncio.CancelledError:
            job.finish("cancelled", "Abgebrochen")
            raise
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            job.finish("error", f"{type(e).__name__}: {e}")
        finally:
            _tasks.pop(job.id, None)

    _tasks[job.id] = asyncio.create_task(runner())
    return job


def cancel(job_id: str) -> bool:
    t = _tasks.get(job_id)
    if t and not t.done():
        t.cancel()
        return True
    return False


def recent(limit: int = 10) -> list[dict[str, Any]]:
    rows = db.query("SELECT * FROM jobs ORDER BY started_at DESC LIMIT ?", (limit,))
    for r in rows:
        r["result"] = db.loads(r.get("result"), {})
    return rows


def mark_orphans() -> None:
    """Beim Start: Jobs, die als 'running' hinterlassen wurden, als abgebrochen markieren."""
    db.execute("UPDATE jobs SET status='cancelled', message='Abgebrochen (Neustart)' WHERE status='running'")

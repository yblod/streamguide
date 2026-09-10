"""Persönliche Bibliothek: Watchlist, Gesehen, Serientracking auf Folgen-Ebene, Statistik."""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from . import db, titles

STATUSES = ("watchlist", "watching", "watched", "disliked", "dropped")


def get_entry(media_type: str, tmdb_id: int) -> dict[str, Any] | None:
    return db.query_one("SELECT * FROM user_titles WHERE media_type=? AND tmdb_id=?", (media_type, tmdb_id))


def set_status(media_type: str, tmdb_id: int, status: str, *, rating: int | None = None,
               rated_at: str | None = None, source: str = "manual", keep_rating: bool = True,
               watched_seasons: list[int] | None = None) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"Unbekannter Status: {status}")
    if media_type == "tv" and status == "watchlist":
        status = "watching"  # Serien: nur "Verfolgen" (nicht begonnen / weiterschauen / auf Stand)
    existing = get_entry(media_type, tmdb_id)
    if existing:
        new_rating = rating if rating is not None else (existing["rating"] if keep_rating else None)
        new_rated_at = rated_at or (existing["rated_at"] if new_rating is not None else None)
        ws = json.dumps(watched_seasons) if watched_seasons is not None else existing["watched_seasons"]
        db.execute(
            "UPDATE user_titles SET status=?, rating=?, rated_at=?, source=?, watched_seasons=?, "
            "new_season_flag=CASE WHEN ?='watching' THEN new_season_flag ELSE 0 END, "
            "new_kind=CASE WHEN ?='watching' THEN new_kind ELSE NULL END, updated_at=datetime('now') "
            "WHERE id=?",
            (status, new_rating, new_rated_at, source, ws, status, status, existing["id"]),
        )
    else:
        db.execute(
            "INSERT INTO user_titles(media_type,tmdb_id,status,rating,rated_at,source,watched_seasons) VALUES(?,?,?,?,?,?,?)",
            (media_type, tmdb_id, status, rating, rated_at or (date.today().isoformat() if rating else None),
             source, json.dumps(watched_seasons or [])),
        )
    if media_type == "tv" and status == "watched":
        mark_all_watched(tmdb_id)
    return get_entry(media_type, tmdb_id) or {}


def set_rating(media_type: str, tmdb_id: int, rating: int | None) -> dict[str, Any]:
    existing = get_entry(media_type, tmdb_id)
    threshold = int(db.get_setting("dislike_threshold", 1))
    if existing is None:
        status = "disliked" if rating is not None and rating <= threshold else "watched"
        return set_status(media_type, tmdb_id, status, rating=rating)
    status = existing["status"]
    if rating is not None and rating <= threshold:
        status = "disliked"
    elif status in ("disliked", "watchlist") and rating is not None:
        status = "watched"
    db.execute("UPDATE user_titles SET rating=?, rated_at=?, status=?, updated_at=datetime('now') WHERE id=?",
               (rating, date.today().isoformat() if rating is not None else None, status, existing["id"]))
    return get_entry(media_type, tmdb_id) or {}


def remove(media_type: str, tmdb_id: int) -> None:
    db.execute("DELETE FROM user_titles WHERE media_type=? AND tmdb_id=?", (media_type, tmdb_id))


def clear_new_flags(media_type: str, tmdb_id: int) -> None:
    db.execute("UPDATE user_titles SET newly_available=0 WHERE media_type=? AND tmdb_id=?", (media_type, tmdb_id))


# ---------- Serien: Folgen-Ebene ----------

def aired_counts(t: dict[str, Any]) -> dict[int, int]:
    """Anzahl ausgestrahlter Folgen je Staffel (aus TMDB last_episode_to_air bzw. Staffel-Startdatum)."""
    today = date.today().isoformat()
    last_s, last_e = t.get("last_ep_season"), t.get("last_ep_number")
    out: dict[int, int] = {}
    for s in t.get("seasons") or []:
        n = s["season_number"]
        cnt = int(s.get("episode_count") or 0)
        if last_s is not None and last_e is not None:
            if n < last_s:
                aired = cnt
            elif n == last_s:
                aired = min(cnt, int(last_e)) if cnt else int(last_e)
            else:
                aired = 0
        else:
            aired = cnt if (s.get("air_date") and s["air_date"] <= today) else 0
        if aired > 0:
            out[n] = aired
    return out


def _load_episodes(entry: dict[str, Any]) -> dict[int, set[int]]:
    raw = db.loads(entry.get("watched_episodes"), {}) or {}
    return {int(k): set(int(e) for e in v) for k, v in raw.items()}


def _save_episodes(tmdb_id: int, eps: dict[int, set[int]], t: dict[str, Any] | None) -> None:
    aired = aired_counts(t) if t else {}
    seasons_done = sorted(n for n, cnt in aired.items() if len(eps.get(n, set())) >= cnt)
    clean = {str(k): sorted(v) for k, v in sorted(eps.items()) if v}
    db.execute("UPDATE user_titles SET watched_episodes=?, watched_seasons=?, updated_at=datetime('now') "
               "WHERE media_type='tv' AND tmdb_id=?", (json.dumps(clean), json.dumps(seasons_done), tmdb_id))
    _recompute_flags(tmdb_id)


def _title_for(tmdb_id: int) -> dict[str, Any] | None:
    row = titles.get_title("tv", tmdb_id)
    return titles.decorate([row])[0] if row else None


def _ensure_watching(tmdb_id: int) -> dict[str, Any]:
    entry = get_entry("tv", tmdb_id)
    if entry is None:
        set_status("tv", tmdb_id, "watching")
        entry = get_entry("tv", tmdb_id) or {}
    return entry


def mark_episode(tmdb_id: int, season: int, episode: int, watched: bool, up_to: bool = False) -> dict[str, Any]:
    """Einzelne Folge (oder alles bis einschließlich dieser Folge) als gesehen/ungesehen markieren."""
    entry = _ensure_watching(tmdb_id)
    t = _title_for(tmdb_id)
    eps = _load_episodes(entry)
    aired = aired_counts(t) if t else {}
    if up_to:
        for n, cnt in aired.items():
            if n < season:
                eps[n] = set(range(1, cnt + 1))
        eps[season] = set(range(1, episode + 1))
    elif watched:
        eps.setdefault(season, set()).add(episode)
    else:
        eps.get(season, set()).discard(episode)
        if not up_to:
            # spätere Folgen derselben Staffel bleiben unberührt
            pass
    _save_episodes(tmdb_id, eps, t)
    return get_entry("tv", tmdb_id) or {}


def mark_season(tmdb_id: int, season: int, watched: bool, include_previous: bool = True) -> dict[str, Any]:
    entry = _ensure_watching(tmdb_id)
    t = _title_for(tmdb_id)
    eps = _load_episodes(entry)
    aired = aired_counts(t) if t else {}
    if watched:
        for n, cnt in aired.items():
            if n == season or (include_previous and n < season):
                eps[n] = set(range(1, cnt + 1))
        if season not in aired:
            eps[season] = eps.get(season, set())
    else:
        eps.pop(season, None)
    _save_episodes(tmdb_id, eps, t)
    return get_entry("tv", tmdb_id) or {}


def mark_all_watched(tmdb_id: int) -> dict[str, Any]:
    entry = get_entry("tv", tmdb_id) or _ensure_watching(tmdb_id)
    t = _title_for(tmdb_id)
    eps = {n: set(range(1, cnt + 1)) for n, cnt in (aired_counts(t) if t else {}).items()}
    _save_episodes(tmdb_id, eps, t)
    return get_entry("tv", tmdb_id) or {}


def set_seasons(media_type: str, tmdb_id: int, watched: list[int]) -> dict[str, Any]:
    """Kompatibilität: Liste komplett gesehener Staffeln setzen."""
    entry = _ensure_watching(tmdb_id)
    t = _title_for(tmdb_id)
    eps = _load_episodes(entry)
    aired = aired_counts(t) if t else {}
    want = set(int(s) for s in watched)
    for n, cnt in aired.items():
        if n in want:
            eps[n] = set(range(1, cnt + 1))
        elif len(eps.get(n, set())) >= cnt:
            eps.pop(n, None)
    _save_episodes(tmdb_id, eps, t)
    return get_entry("tv", tmdb_id) or {}


def series_progress(t: dict[str, Any]) -> dict[str, Any]:
    """Fortschritt für eine dekorierte Serie (t['user'] enthält watched_episodes)."""
    u = t.get("user") or {}
    eps: dict[int, set[int]] = {int(k): set(v) for k, v in (u.get("watched_episodes") or {}).items()}
    aired = aired_counts(t)
    seasons_out = []
    total = watched_total = 0
    nxt = None
    for s in t.get("seasons") or []:
        n = s["season_number"]
        cnt = aired.get(n, 0)
        w = len([e for e in eps.get(n, set()) if e <= cnt]) if cnt else 0
        total += cnt
        watched_total += w
        if nxt is None and cnt and w < cnt:
            for e in range(1, cnt + 1):
                if e not in eps.get(n, set()):
                    nxt = {"season": n, "episode": e, "season_name": s.get("name")}
                    break
        seasons_out.append({
            "season_number": n, "name": s.get("name"), "episode_count": s.get("episode_count"),
            "aired": cnt, "watched": w, "complete": bool(cnt) and w >= cnt, "air_date": s.get("air_date"),
            "watched_episodes": sorted(eps.get(n, set())),
        })
    pending = total - watched_total
    started = watched_total > 0
    new_season = bool(nxt) and started and nxt["episode"] == 1 and all(
        s["complete"] for s in seasons_out if s["season_number"] < nxt["season"] and s["aired"])
    return {
        "aired_total": total, "watched_total": watched_total, "pending": pending,
        "next": nxt, "complete": total > 0 and pending == 0, "started": started,
        "new_season": new_season, "seasons": seasons_out,
        "watched": [s["season_number"] for s in seasons_out if s["complete"]],
        "unwatched": [s["season_number"] for s in seasons_out if s["aired"] and not s["complete"]],
        "next_season": nxt["season"] if nxt else None,
        "aired": [s["season_number"] for s in seasons_out if s["aired"]],
    }


def _recompute_flags(tmdb_id: int) -> None:
    """new_season_flag/new_kind für eine Serie neu berechnen (nur wenn verfolgt, begonnen und bei mir verfügbar)."""
    t = _title_for(tmdb_id)
    if not t or not t.get("user"):
        return
    u = t["user"]
    prog = series_progress(t)
    avail = (t.get("availability") or {}).get("mine")
    flag = u["status"] == "watching" and prog["started"] and prog["pending"] > 0 and bool(avail)
    kind = ("season" if prog["new_season"] else "episodes") if flag else None
    db.execute("UPDATE user_titles SET new_season_flag=?, new_kind=? WHERE media_type='tv' AND tmdb_id=?",
               (1 if flag else 0, kind, tmdb_id))


# ---------- Listen / Statistik ----------

def list_titles(status: str | list[str] | None = None, media_type: str | None = None,
                sort: str = "added") -> list[dict[str, Any]]:
    where, params = [], []
    if status:
        sts = [status] if isinstance(status, str) else list(status)
        where.append(f"u.status IN ({','.join('?' * len(sts))})")
        params.extend(sts)
    if media_type:
        where.append("u.media_type=?")
        params.append(media_type)
    order = {
        "added": "u.added_at DESC",
        "rated": "u.rated_at DESC, u.updated_at DESC",
        "title": "t.title COLLATE NOCASE",
        "year": "t.year DESC",
        "rating": "u.rating DESC, u.rated_at DESC",
        "updated": "u.updated_at DESC",
    }.get(sort, "u.added_at DESC")
    sql = ("SELECT t.*, u.status AS u_status, u.rating AS u_rating, u.rated_at AS u_rated_at, u.added_at AS u_added_at, "
           "u.watched_seasons AS u_watched_seasons, u.watched_episodes AS u_watched_episodes, "
           "u.new_season_flag AS u_new_season_flag, u.new_kind AS u_new_kind, u.newly_available AS u_newly_available, "
           "u.notes AS u_notes, u.media_type AS media_type, u.tmdb_id AS tmdb_id "
           "FROM user_titles u LEFT JOIN titles t ON t.media_type=u.media_type AND t.tmdb_id=u.tmdb_id ")
    if where:
        sql += "WHERE " + " AND ".join(where) + " "
    sql += "ORDER BY " + order
    rows = db.query(sql, params)
    user_map = {
        (r["media_type"], r["tmdb_id"]): titles.user_entry({
            "status": r["u_status"], "rating": r["u_rating"], "rated_at": r["u_rated_at"], "added_at": r["u_added_at"],
            "watched_seasons": r["u_watched_seasons"], "watched_episodes": r["u_watched_episodes"],
            "new_season_flag": r["u_new_season_flag"], "new_kind": r["u_new_kind"],
            "newly_available": r["u_newly_available"], "notes": r["u_notes"],
        }) for r in rows
    }
    return titles.decorate(rows, user_map)


def stats() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for r in db.query("SELECT status, media_type, COUNT(*) AS n FROM user_titles GROUP BY status, media_type"):
        out.setdefault(r["status"], {})[r["media_type"]] = r["n"]
    out["ratings"] = db.query_one("SELECT COUNT(*) AS n, AVG(rating) AS avg FROM user_titles WHERE rating IS NOT NULL") or {}
    out["imdb_dataset"] = db.query_one("SELECT COUNT(*) AS n FROM imdb_ratings") or {}
    out["imdb_dataset_updated"] = db.get_setting("imdb_dataset_updated")
    out["titles_cached"] = (db.query_one("SELECT COUNT(*) AS n FROM titles") or {}).get("n", 0)
    return out

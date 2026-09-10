"""App-Login: Passwort aus den Add-on-Optionen, signiertes Session-Cookie, optional ohne Login im Heimnetz."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import os
import secrets
import time
from html import escape

from fastapi import Request
from fastapi.responses import HTMLResponse

from . import db

COOKIE = "sg_session"
SESSION_DAYS = 365
PUBLIC_PREFIXES = ("/static/", "/login", "/health", "/favicon.ico")

_secret: bytes | None = None
_failures = 0


def password() -> str:
    return (os.environ.get("STREAMGUIDE_PASSWORD") or "").strip()


def enabled() -> bool:
    return bool(password())


def lan_without_login() -> bool:
    return (os.environ.get("STREAMGUIDE_LAN_WITHOUT_LOGIN") or "true").strip().lower() in ("1", "true", "yes", "on")


def _get_secret() -> bytes:
    global _secret
    if _secret is None:
        f = db.DATA_DIR / "secret.key"
        if f.exists():
            _secret = bytes.fromhex(f.read_text().strip())
        else:
            _secret = secrets.token_bytes(32)
            f.write_text(_secret.hex())
    return _secret


def _sign(exp: int) -> str:
    # Passwort-Hash im Signaturmaterial: neues Passwort macht alte Cookies ungültig.
    msg = f"{exp}.{hashlib.sha256(password().encode()).hexdigest()}".encode()
    return hmac.new(_get_secret(), msg, hashlib.sha256).hexdigest()


def make_token() -> str:
    exp = int(time.time()) + SESSION_DAYS * 86400
    return f"{exp}.{_sign(exp)}"


def valid_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    exp_s, sig = token.split(".", 1)
    try:
        exp = int(exp_s)
    except ValueError:
        return False
    if exp < time.time():
        return False
    return hmac.compare_digest(sig, _sign(exp))


def via_tunnel(request: Request) -> bool:
    """Anfragen über den Cloudflare-Tunnel tragen Cloudflare-Header."""
    h = request.headers
    return bool(h.get("cf-connecting-ip") or h.get("cf-ray") or h.get("cf-visitor"))


def is_lan(request: Request) -> bool:
    if via_tunnel(request):
        return False
    host = request.client.host if request.client else ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def is_https(request: Request) -> bool:
    h = request.headers
    return request.url.scheme == "https" or h.get("x-forwarded-proto") == "https" or '"https"' in (h.get("cf-visitor") or "")


def logged_in(request: Request) -> bool:
    return valid_token(request.cookies.get(COOKIE))


def allowed(request: Request) -> bool:
    """Darf diese Anfrage ohne Login durch?"""
    if not enabled():
        return True
    path = request.url.path
    if path.startswith(PUBLIC_PREFIXES):
        return True
    if lan_without_login() and is_lan(request):
        return True
    return logged_in(request)


def check_password(given: str) -> bool:
    return hmac.compare_digest(given.encode(), password().encode())


async def throttle(success: bool) -> None:
    """Einfacher Schutz gegen Durchprobieren: nach Fehlversuchen kurz warten."""
    global _failures
    if success:
        _failures = 0
        return
    _failures += 1
    await asyncio.sleep(min(5.0, 0.5 * _failures))


def safe_next(value: str | None) -> str:
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return "/"


def login_page(next_url: str = "/", error: str | None = None) -> HTMLResponse:
    err = f'<p class="err">{escape(error)}</p>' if error else ""
    html = f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>StreamGuide – Anmelden</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🎬</text></svg>">
<style>
  :root {{ color-scheme: light dark; --bg:#0f1220; --card:rgba(255,255,255,.08); --bd:rgba(255,255,255,.18); --fg:#f3f4f8; --muted:#a3a8c3; --accent:#7c5cff; --err:#ff6b8a; }}
  @media (prefers-color-scheme: light) {{ :root {{ --bg:#eef0f8; --card:rgba(255,255,255,.65); --bd:rgba(0,0,0,.1); --fg:#1a1d2e; --muted:#5b6078; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; min-height:100vh; display:grid; place-items:center; font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; color:var(--fg);
         background:var(--bg) radial-gradient(60vw 60vw at 10% 10%, rgba(124,92,255,.35), transparent 60%), radial-gradient(50vw 50vw at 90% 90%, rgba(0,200,255,.25), transparent 60%); }}
  form {{ width:min(92vw,380px); padding:32px 28px; border-radius:22px; background:var(--card); border:1px solid var(--bd); backdrop-filter:blur(18px); -webkit-backdrop-filter:blur(18px); box-shadow:0 20px 60px rgba(0,0,0,.25); }}
  h1 {{ margin:0 0 4px; font-size:26px; }} p {{ margin:0 0 18px; color:var(--muted); font-size:14px; }}
  input {{ width:100%; padding:13px 14px; font-size:17px; border-radius:12px; border:1px solid var(--bd); background:rgba(127,127,127,.12); color:inherit; outline:none; }}
  input:focus {{ border-color:var(--accent); box-shadow:0 0 0 3px rgba(124,92,255,.25); }}
  button {{ width:100%; margin-top:14px; padding:13px; font-size:17px; font-weight:600; border:0; border-radius:12px; background:var(--accent); color:#fff; cursor:pointer; }}
  .err {{ color:var(--err); margin:10px 0 0; }}
</style></head><body>
<form method="post" action="/login">
  <h1>🎬 StreamGuide</h1><p>Bitte Passwort eingeben.</p>
  <input type="hidden" name="next" value="{escape(next_url, quote=True)}">
  <input type="password" name="password" placeholder="Passwort" autofocus autocomplete="current-password" required>
  <button type="submit">Anmelden</button>{err}
</form></body></html>"""
    return HTMLResponse(html, status_code=401 if error else 200)

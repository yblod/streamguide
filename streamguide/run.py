"""Startet StreamGuide als Home-Assistant-Add-on (oder lokal zum Testen).

Im Add-on liegen die Optionen in /data/options.json; sie werden hier in Umgebungsvariablen übersetzt.
Lokal (ohne /data) gelten .env bzw. bereits gesetzte Umgebungsvariablen.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

OPTIONS = Path(os.environ.get("STREAMGUIDE_OPTIONS") or "/data/options.json")
ENV_FILE = ROOT / ".env"


def _load_env_file() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _load_addon_options() -> None:
    if not OPTIONS.exists():
        return
    try:
        opts = json.loads(OPTIONS.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"Warnung: {OPTIONS} nicht lesbar: {e}", flush=True)
        return
    mapping = {
        "tmdb_api_key": "TMDB_API_KEY",
        "password": "STREAMGUIDE_PASSWORD",
        "lan_without_login": "STREAMGUIDE_LAN_WITHOUT_LOGIN",
        "log_level": "STREAMGUIDE_LOG_LEVEL",
        "port": "STREAMGUIDE_PORT",
    }
    for key, env in mapping.items():
        val = opts.get(key)
        if val is None or val == "":
            continue
        os.environ[env] = str(val).strip() if not isinstance(val, bool) else ("true" if val else "false")
    os.environ.setdefault("STREAMGUIDE_DATA_DIR", str(OPTIONS.parent))


_load_env_file()
_load_addon_options()

HOST = os.environ.get("STREAMGUIDE_HOST", "0.0.0.0")
PORT = int(os.environ.get("STREAMGUIDE_PORT", "8765"))
LOG_LEVEL = (os.environ.get("STREAMGUIDE_LOG_LEVEL") or "info").lower()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload="--reload" in sys.argv,
                log_level=LOG_LEVEL, proxy_headers=False, access_log=LOG_LEVEL == "debug")

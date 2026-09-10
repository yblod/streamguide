"""Versionsnummer aus config.yaml (Add-on-Metadaten), damit App und Add-on dieselbe Nummer zeigen."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_version() -> str:
    cfg = ROOT / "config.yaml"
    if cfg.exists():
        m = re.search(r'^version:\s*"?([^"\s]+)"?', cfg.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1)
    return "dev"


VERSION = read_version()

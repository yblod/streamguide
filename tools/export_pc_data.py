"""Erzeugt eine StreamGuide-Sicherung (ZIP) aus der Datenbank der PC-Version.

Die Quelle wird nur gelesen: Datenbank samt WAL/SHM wird in ein Temp-Verzeichnis kopiert und
ausschließlich die Kopie geöffnet. Die ZIP lässt sich im Add-on unter Einstellungen → Sicherung
hochladen.

Aufruf (aus F:\\Claude\\streamguide-ha):
    python tools\\export_pc_data.py
    python tools\\export_pc_data.py --db "F:\\Claude\\streamguide\\data\\streamguide.db" --out streamguide-pc.zip
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "streamguide"))

from app import backup  # noqa: E402

DEFAULT_DB = Path(r"F:\Claude\streamguide\data\streamguide.db")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"Quell-Datenbank (Standard: {DEFAULT_DB})")
    ap.add_argument("--out", type=Path, default=ROOT / "streamguide-pc-export.zip", help="Ziel-ZIP")
    args = ap.parse_args()
    if not args.db.exists():
        print(f"Datenbank nicht gefunden: {args.db}")
        return 1
    m = backup.export_file(args.db, args.out, version="pc-export")
    print(f"Sicherung geschrieben: {args.out} ({m['size'] / 1e6:.1f} MB)")
    for k, v in m["counts"].items():
        print(f"  {k:15s} {v:>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

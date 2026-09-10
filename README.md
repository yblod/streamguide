# StreamGuide – Home-Assistant-Add-on-Repository

Dieses Repository ist eine Add-on-Quelle für Home Assistant. In HA unter
**Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories** die URL `https://github.com/yblod/streamguide`
hinzufügen, danach erscheint das Add-on **StreamGuide** im Store.

| Add-on | Beschreibung |
|---|---|
| [streamguide](streamguide/) | Persönlicher Streaming-Guide und Watch-Tracker (TMDB, IMDb, JustWatch) für Region DE |

Installation, Optionen, Datenübernahme von der PC-Version und Fernzugriff über Cloudflared:
[streamguide/DOCS.md](streamguide/DOCS.md).

## Entwicklung auf dem PC

```
run_local.bat
```

startet die Add-on-Version lokal unter `http://127.0.0.1:8766` (Daten in `.\data`, Optionen per `.env`:
`TMDB_API_KEY`, `STREAMGUIDE_PASSWORD`, `STREAMGUIDE_LAN_WITHOUT_LOGIN`). Die Datenübernahme aus der
PC-Version erledigt `tools\export_pc_data.py` (liest nur, verändert dort nichts).

Docker-Build wie im Add-on (amd64, lokal testbar):

```
docker build --build-arg BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.22 -t streamguide-addon streamguide
docker run --rm -p 8767:8765 -v %cd%\data-docker:/data streamguide-addon
```

Aufbau: `repository.yaml` (Repo-Metadaten), `streamguide/` (Add-on: `config.yaml`, `Dockerfile`, `build.yaml`,
`run.py`, `app/`, `static/`), `tools/` (Hilfsskripte).

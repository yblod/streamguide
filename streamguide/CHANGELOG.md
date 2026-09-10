# Changelog

## 1.0.1 – 2026-09-11

- Oberfläche und Doku ohne persönliche Angaben (Kontonamen, Domain, IP), da das Repository öffentlich ist.
- Doku: Zugriff im Heimnetz über die IP statt `homeassistant.local`, Hinweise zum Cloudflared-Eintrag.

## 1.0.0 – 2026-09-10

Erste Add-on-Version von StreamGuide (Abzweig der PC-Version vom 10.09.2026).

- Läuft als Home-Assistant-Add-on (aarch64/amd64), Daten persistent in `/data`.
- TMDB-Schlüssel, App-Passwort und „Heimnetz ohne Login“ als Add-on-Optionen.
- App-Login mit langlebigem Session-Cookie (für den Zugriff über den Cloudflare-Tunnel).
- Sicherung als ZIP (Datenbank ohne IMDb-Datensatz) und Wiederherstellung in den Einstellungen.
- Hilfsskript `tools/export_pc_data.py` zum Übernehmen der Daten aus der PC-Version.
- Watchdog-Endpunkt `/health`.

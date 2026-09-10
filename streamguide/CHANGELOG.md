# Changelog

## 1.0.4 – 2026-09-11

- Touch: Das Ausblenden des doppelten Status-Badges griff in Safari nicht (CSS `:has()` nicht unterstützt);
  jetzt über eine Klasse an der Karte, funktioniert in allen Browsern.

## 1.0.3 – 2026-09-11

- Touch: Status-Symbol (🔖/📺/✕) erschien auf Karten doppelt, als Badge und als markierter Schnellaktions-Button.
  Auf Touch-Geräten zeigt jetzt nur der Button den Status; Maus-Ansicht unverändert.

## 1.0.2 – 2026-09-11

- Kopfzeile auf Tablets im Querformat (iPad): kompaktere Navigation, der Theme-Schalter ragte rechts aus der Leiste.
- Touch-Bedienung: Karten öffnen mit einem Tipp (vorher zwei, weil der erste Tipp nur den Hover-Zustand auslöste).
  Hover-Effekte gelten nur noch bei Maus/Trackpad; auf Touch-Geräten sind die Schnellaktionen dauerhaft rechts unter
  den Badges sichtbar, der Trailer-Button im Poster ebenfalls.

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

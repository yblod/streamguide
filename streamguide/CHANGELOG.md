# Changelog

## 1.2.1 – 2026-09-12

- Abos: Titel je Anbieter sind direkt sichtbar (nach „nur hier“ und IMDb sortiert); „NUR HIER“ markiert Titel,
  die bei keinem anderen Streaming-Anbieter laufen. Vertriebswege desselben Katalogs zählen als ein Anbieter
  (z. B. HBO Max direkt und über Amazon, WOW/Sky Go), Aktivieren schaltet alle Varianten.
- Watchlist: Filter „Leihen“ zeigt nur leihbare Titel, die nicht bei den eigenen Anbietern laufen (kein Kaufen).

## 1.2.0 – 2026-09-12

- Neu: Tab **Abos** – Abos/Quellen direkt verwalten und je Anbieter sehen, welche Titel der Watchlist und der
  verfolgten Serien dort laufen (Titelreihe direkt sichtbar, nach IMDb sortiert); für nicht aktive Anbieter als
  Entscheidungshilfe („lohnt sich ein Abo?“) mit Aktivieren/Deaktivieren. Titel, die bei keinem anderen
  Streaming-Anbieter laufen, sind mit „NUR HIER“ markiert und stehen vorn.
- Suche ist in **Entdecken** integriert: Suchtreffer werden mit den Filtern darunter verfeinert (Verfügbarkeit,
  Jahr, Genre, Land, FSK, IMDb …); ohne Suchbegriff arbeitet Entdecken wie bisher. Der Tab „Suche“ entfällt,
  alte Links leiten weiter.
- Entdecken: „Zurücksetzen“ setzt die Filter jetzt tatsächlich zurück (die Seite wurde zuvor nur ein zweites Mal
  darunter aufgebaut).
- Watchlist: Filter „Anderes Abo / Leihen“ ist jetzt „Leihen“ und zeigt nur Titel, die nicht bei den eigenen
  Anbietern laufen, aber leihbar sind (Kaufangebote bleiben außen vor).
- Startseite: „Serien weiterschauen oder anfangen“ zeigt nur Serien, die gerade bei den eigenen Anbietern laufen
  (Abo oder kostenlos, z. B. ZDF/Arte).

## 1.1.0 – 2026-09-11

- Neu: **Weitere Länder (per VPN)** in den Einstellungen, z. B. Großbritannien für BBC iPlayer. Angebote der gewählten
  Länder werden zusätzlich zu Deutschland geladen; dort aktiv geschaltete Anbieter zählen als „meine Anbieter“
  (Startseite, Watchlist-Verfügbarkeit, Entdecken). Inaktive Auslandsangebote werden ignoriert.
  Beim Hinzufügen von Großbritannien sind BBC iPlayer, ITVX und Channel 4 vorbelegt.
- Auslandsangebote sind auf Karten und in der Detailansicht mit Flagge gekennzeichnet.
- Datenbank: Anbieter werden je Land gespeichert (automatische Migration, Sicherungen älterer Versionen lassen sich
  weiterhin einspielen).

## 1.0.5 – 2026-09-11

- Frontend-Dateien werden unter einem versionierten Pfad (`/static/v<Version>/…`) eingebunden. Safari auf dem iPad
  hielt nach Updates alte JavaScript-Module trotz Neuladen fest; ab jetzt lädt jede Version garantiert frische Dateien.

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

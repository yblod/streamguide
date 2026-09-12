# StreamGuide – Home-Assistant-Add-on

Persönlicher Streaming-Guide und Watch-Tracker für Deutschland: Watchlist-Verfügbarkeit bei den eigenen
Anbietern, Entdecken-Filter (Jahr, Genre, IMDb, Land, FSK, Wiedergabesprache), Serientracking auf Folgen-Ebene,
Schauspieler-Favoriten. Datenquellen: TMDB, offizieller IMDb-Bewertungsdatensatz, JustWatch (Sprachen).

## Installation

1. Home Assistant → **Einstellungen → Add-ons → Add-on Store** → Menü „⋮“ oben rechts → **Repositories**.
2. `https://github.com/yblod/streamguide` eintragen → **Hinzufügen**.
3. Seite neu laden, **StreamGuide** auswählen → **Installieren**. Das Image wird auf dem Gerät gebaut
   (Raspberry Pi 4: einige Minuten).
4. Unter **Konfiguration** die Optionen setzen (siehe unten) → **Speichern** → **Starten**.

Die App ist danach im Heimnetz unter `http://<IP-des-HA>:8765` erreichbar (bei einer Fritzbox auch
`http://homeassistant.fritz.box:8765`). `homeassistant.local` funktioniert unter Windows oft nicht (mDNS liefert
nur IPv6-Link-Local). Es gibt bewusst keinen Eintrag in der HA-Seitenleiste (kein Ingress).

## Optionen

| Option | Bedeutung |
|---|---|
| `tmdb_api_key` | TMDB-API-Schlüssel (v3 API Key oder v4 Read Access Token). Kann alternativ in der App unter Einstellungen hinterlegt werden; die Option hat Vorrang. |
| `password` | App-Passwort. Leer = kein Login (nur sinnvoll, solange die App nicht von außen erreichbar ist). Ein neues Passwort meldet alle Geräte ab. |
| `lan_without_login` | `true`: Zugriffe aus dem Heimnetz (private IP, nicht über den Cloudflare-Tunnel) brauchen kein Passwort. `false`: Passwort immer. |
| `log_level` | `debug` (mit Zugriffslog), `info`, `warning`, `error`. |

Das Login-Cookie gilt ein Jahr, ein Gerät muss sich also nur einmal anmelden.

## Daten

Alles liegt in `/data` des Add-ons (SQLite-Datenbank `streamguide.db`, Sicherungen unter `backups/`) und ist
damit Teil der Home-Assistant-Backups. Beim ersten Start lädt die App den IMDb-Bewertungsdatensatz (~7 MB,
1,7 Mio. Zeilen); das dauert auf dem Pi einige Minuten und läuft im Hintergrund.

### Abos

Im Tab „Abos“ werden die aktiven Abos und Quellen verwaltet (hinzufügen per Suche, deaktivieren). Darunter steht
für jeden nicht aktiven Anbieter, welche Titel der Watchlist und der verfolgten Serien man damit zusätzlich sehen
könnte – als Entscheidungshilfe, ob sich ein Abo gerade lohnt. Gesehenes, bereits Verfügbares und Serien ohne
ungesehene Folgen zählen nicht mit; „NUR HIER“ markiert Titel, die kein anderer Streaming-Anbieter hat.
Varianten eines Anbieters (mit/ohne Werbung, Amazon Channel) gelten als ein Anbieter.

### Direktlinks zu den Anbietern

In der Detailansicht ist jedes Angebot mit „↗“ ein Link zur Titelseite beim Anbieter (Quelle JustWatch, auch für
die VPN-Länder). Am PC/Mac öffnet der Web-Player, auf iPad/Handy in der Regel die App des Anbieters. Im Browser
eines Fernsehers öffnet der Link nur im TV-Browser, nicht in der TV-App. Angebote ohne Link kennt JustWatch (noch)
nicht.

### Profile

In den Einstellungen (Hauptprofil) lassen sich weitere Profile anlegen, z. B. für Kinder. Jedes Profil hat eine
eigene Watchlist, eigene Serien, Bewertungen und Schauspieler (eigene Datei unter `/data/profiles/`, in der
Sicherung enthalten). Abos, TMDB-Schlüssel, Länder und der Titel-Cache sind gemeinsam. Der Wechsel erfolgt über den
👤-Knopf oben rechts; für den Wechsel zurück ins Hauptprofil kann eine PIN gesetzt werden.

Ein Profil mit Altersgrenze (z. B. „bis 15 Jahre“) sieht in Suche, Entdecken, Startseite, Filmografien und Details
nur Titel mit bekannter Freigabe bis zu diesem Alter. Grundlage ist die deutsche FSK; fehlt sie, wird die US- oder
GB-Einstufung als Näherung verwendet (Anzeige „FSK ~12“). Titel ganz ohne Einstufung bleiben ausgeblendet. Die
Altersgrenze wird im Hauptprofil in den Einstellungen geändert.

### Weitere Länder (per VPN)

Wer per VPN auch ausländische Mediatheken nutzt (z. B. BBC iPlayer in Großbritannien), wählt in den Einstellungen
unter „Weitere Länder“ das Land aus. Die App lädt dann die Anbieter und Angebote dieses Landes zusätzlich zu
Deutschland. Nur Anbieter, die dort aktiv geschaltet werden, zählen als „meine Anbieter“; alle übrigen
Auslandsangebote werden ignoriert. Solche Angebote erscheinen auf Karten und in der Detailansicht mit Flagge.
Nach dem Hinzufügen eines Landes werden die Angebote der Bibliothek im Hintergrund neu geladen.

### Daten von der PC-Version übernehmen

1. Auf dem PC in `F:\Claude\streamguide-ha`:
   ```
   python tools\export_pc_data.py
   ```
   Erzeugt `streamguide-pc-export.zip` aus der Datenbank der PC-Version (nur lesend, ohne IMDb-Datensatz).
2. In der Add-on-App: **Einstellungen → Sicherung** → ZIP hineinziehen → bestätigen.
3. Danach unter **Einstellungen → TMDB-Konto** prüfen, ob die Verbindung noch besteht; sonst neu verbinden.

Dieselbe Funktion dient als Sicherung/Wiederherstellung der Add-on-Daten (**⬇ Sicherung herunterladen**).

## Zugriff von außen (Cloudflared-Add-on)

Das Add-on ist im HA-internen Netz unter dem Container-Hostnamen erreichbar. Der steht auf der
Add-on-Infoseite unter **Hostname** und hat die Form `<hash>-streamguide`.

Im Cloudflared-Add-on unter **Zusätzliche Hosts** (`additional_hosts`) ergänzen:

```yaml
- hostname: stream.example.de
  service: http://<hash>-streamguide:8765
```

Cloudflared legt den DNS-Eintrag (CNAME) selbst an. Am besten in der YAML-Ansicht der Konfiguration eintragen
und das Add-on danach über die lokale HA-Adresse neu starten (ein Neustart über den Tunnel trennt die eigene
Verbindung und meldet fälschlich einen Fehler). Vorher unbedingt `password` setzen; `lan_without_login`
kann dabei `true` bleiben, weil Tunnel-Anfragen an den Cloudflare-Headern erkannt und immer zum Login geführt werden.

## Aktualisieren

Neue Versionen erscheinen im Add-on-Store, sobald `version` in `config.yaml` im Repository erhöht wurde.
Die Datenbank wird beim Start automatisch migriert.

## Fehlersuche

- **Protokoll** des Add-ons zeigt Start (`StreamGuide <Version> – Daten in /data – Login aktiv …`) und Fehler.
- `http://<IP-des-HA>:8765/health` liefert `{"ok": true}`; der Watchdog startet das Add-on sonst neu.
- Suche/Entdecken liefern Fehler 428 → kein TMDB-Schlüssel hinterlegt.

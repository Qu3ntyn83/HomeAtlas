# LabVis

Interaktive Homelab-Dokumentation in **einem Docker-Container**: Topologie-Diagramm, Rack-Ansicht,
VLANs/IP-Übersicht, automatischer Netzwerk-Scan und Anbindungen, die Systeme regelmäßig auslesen.

Die Idee kombiniert zwei Projekte:

- **[Homelable](https://github.com/Pouzor/homelable)** – interaktiver Canvas, nmap-Scan mit Fundliste, Live-Status
- **[homelab-diagram](https://github.com/Goblinmine/homelab-diagram)** – die Optik: Ordner-Karten, Kabelbreite = Link-Geschwindigkeit,
  Trunks als helles Kabel mit dunklem Kern, Hardware-Kacheln, Container als Chips mit einer Zeile pro App

Der Code ist eigenständig geschrieben (FastAPI + SQLite, Oberfläche ohne Build-Schritt).

## Start

```bash
cp .env.example .env        # Passwort setzen
docker compose up -d --build
```

Danach: `http://<host>:8099`. Die Daten liegen in `./data`.

## Anmeldung

LabVis hat eine eigene Anmeldeseite mit Benutzerkonten:

- **Erstes Konto:** Ist `LABVIS_PASSWORD` in der `.env` gesetzt, wird beim ersten Start das Konto `LABVIS_USER` (Standard `admin`)
  damit angelegt. Ohne die Variable fragt die Seite beim ersten Aufruf nach Benutzername und Passwort. Richte das Konto in diesem
  Fall direkt nach dem Start ein – bis dahin kann es jeder im Netz anlegen.
- Die Variablen wirken nur, solange es noch kein Konto gibt. Danach änderst du Passwörter unter *System → Konto*.
- Weitere Benutzer legt ein Admin unter *System → Benutzerverwaltung* an und vergibt dort eines von drei Rechten:

  | Recht | darf |
  |---|---|
  | **Lesen** | alles ansehen, SVG exportieren, das eigene Passwort ändern |
  | **Ändern** | zusätzlich Geräte, Kabel, Racks und Netzwerke pflegen, Scans starten, Funde übernehmen, Anbindungen einrichten |
  | **Admin** | zusätzlich Benutzer verwalten, Systemeinstellungen ändern, Daten exportieren und wiederherstellen |

  Das erste Konto ist immer Admin. Die Rechte prüft der Server; die Oberfläche blendet gesperrte Funktionen nur zusätzlich aus.
- Passwörter liegen als scrypt-Hash in der Datenbank, Sitzungen als HttpOnly-Cookie (30 Tage). Ein Passwortwechsel meldet alle
  anderen Sitzungen des Kontos ab. Nach fünf Fehlversuchen wird die Anmeldung von dieser Adresse kurz gesperrt.
- **Passwort vergessen:** `docker compose exec labvis python -c "from app import db; db.x('DELETE FROM sessions'); db.x('DELETE FROM users')"`
  löscht alle Konten; danach greift wieder die Ersteinrichtung.

Der Container läuft im **Host-Netz** mit `NET_RAW`. Nur so liefert der Scan MAC-Adressen und Hersteller
für das Netz, in dem der Docker-Host selbst hängt. Für andere VLANs gilt: Die Firewall muss den Scan vom
Docker-Host aus erlauben, MAC-Adressen gibt es dort nicht (Erkennung dann über Ports, Web-Titel und SNMP).

## Bereiche

| Bereich | Inhalt |
|---|---|
| **Topologie** | Karten frei verschieben, zoomen, VLAN-Filter, Klick öffnet Details. VMs/Container erscheinen als Chips im Host, deren Container als Zeilen. Export als SVG. |
| **Racks** | Racks mit beliebig vielen HE, Geräte per Ziehen umsetzen, freie HE antippen zum Einbauen. |
| **Netzwerke** | VLANs mit Subnetz, Gateway, Farbe und Regel; IP-Belegung je Netz (online, offline, neu gefunden, frei); Scan je Netz. |
| **Funde** | Was der Scan gefunden hat und noch nicht dokumentiert ist – mit Typ-Vermutung und Schnittstellen-Vorschlägen. |
| **Anbindungen** | Proxmox, Docker, SNMP, OPNsense. Vorschläge aus dem Scan lassen sich mit einem Klick einrichten. |
| **System** | Intervalle, SNMP-Community, Export/Import. |

## Scan und Erkennung

1. `nmap -sn` findet Hosts (im eigenen Netz per ARP, inklusive MAC und Hersteller).
2. Ein Port-Scan prüft rund 50 typische Ports, dazu Web-Titel und eine SNMP-Abfrage.
3. `app/fingerprints.py` leitet daraus Typ, Icon und Vorschläge ab, z. B.:

| Indiz | Vorschlag |
|---|---|
| Port 8006 / Titel „Proxmox Virtual Environment" | Proxmox-API *(Connector)* |
| Port 2375/2376, Portainer, Dockhand | Docker-API *(Connector)* |
| Antwort auf SNMP, Hersteller Aruba/HP/Cisco/MikroTik … | SNMP *(Connector)* |
| Titel „OPNsense" | OPNsense-API *(Connector, experimentell)* |
| Synology, QNAP, TrueNAS, UniFi, Home Assistant, Checkmk, FRITZ!Box, IPMI, Windows, SSH | Hinweis auf die passende Schnittstelle (noch kein Connector) |

Bekannte Geräte werden über MAC bzw. IP wiedererkannt und bekommen ihren Online-Status aus dem Scan.

## Verbindungsarten

Eine Verbindung zwischen zwei Geräten ist entweder ein **Kabel** (Breite = Geschwindigkeit, Trunk hell mit dunklem Kern), eine
**API-Verbindung** (gestrichelt, mit Pfeil vom abfragenden zum abgefragten System und Protokoll als Beschriftung, z. B. „API · REST :8006")
oder **logisch** (gepunktet, etwa VPN oder Cloud). Im Gerät legt „API-Verbindung" direkt eine solche an.

## Geräte mit mehreren Netzwerkkarten

Ein Gerät kann beliebig viele Adressen haben (z. B. ein NAS mit vier NICs in zwei VLANs):

- **Zusammenführen** (im Gerät): Ein zweiter Eintrag geht in diesem auf. Seine IP/MAC wird zur weiteren Adresse, Kabel, enthaltene
  Geräte und Anbindungen wandern mit.
- **Zu Gerät hinzufügen** (unter *Funde*): Ein neu gefundener Host wird direkt als weitere Adresse an ein vorhandenes Gerät gehängt.
- **+ Adresse** (im Gerät): Adresse von Hand eintragen, etwa für ein Storage-Netz, das der Scanner nicht erreicht.

Der Scan erkennt jede Adresse einzeln wieder. Das Gerät gilt als online, solange mindestens eine Adresse antwortet; die IP-Übersicht
zeigt den Zustand je Adresse.

## Anbindungen einrichten

**Proxmox** – read-only Token:

```bash
pveum user add labvis@pve
pveum aclmod / -user labvis@pve -role PVEAuditor
pveum user token add labvis@pve labvis --privsep 0
```

Token-ID `labvis@pve!labvis` und das Secret eintragen. Gelesen werden Nodes (CPU, RAM, Version), VMs und
LXC-Container samt IP (bei VMs nur mit QEMU-Guest-Agent). Bereits gescannte Hosts mit gleicher IP oder
gleichem Namen werden übernommen statt doppelt angelegt.

**Docker** – pro Docker-Host einen read-only Socket-Proxy starten und `http://<host>:2375` eintragen:

```yaml
services:
  socket-proxy:
    image: tecnativa/docker-socket-proxy
    restart: unless-stopped
    environment: { CONTAINERS: 1 }
    volumes: ["/var/run/docker.sock:/var/run/docker.sock:ro"]
    ports: ["2375:2375"]     # nur intern erreichbar machen!
```

**SNMP (v2c)** – liest Systemname, Ports mit Status, Geschwindigkeit und PVID sowie LLDP-Nachbarn. Stimmt der
Nachbarname mit einem dokumentierten Gerät überein, entsteht daraus automatisch ein Kabel mit der ausgehandelten Geschwindigkeit.

**OPNsense** – API-Key und Secret eines Benutzers mit Leserechten auf die Interfaces; importiert VLANs und Subnetze.

## Import aus homelab-diagram

Unter *System → inventory.yaml importieren* wird eine Datei im Format von homelab-diagram eingelesen
(VLANs, Firewall, Switch-Ports, Geräte, Server mit Gästen und Apps, Kabel).

## Stand und Grenzen

- Getestet: API, Scan-Ablauf, Proxmox- und Docker-Sync gegen Test-Server, SNMP/LLDP-Auswertung mit Beispieldaten, Container-Build und -Start, Anmeldung (Einrichtung, Login, Sperre, Passwortwechsel, Benutzerverwaltung, Rechte Lesen/Ändern/Admin).
- **Nicht** gegen echte Geräte getestet: SNMP-Abruf an realen Switches und der OPNsense-Connector (API-Pfade können je Version abweichen).
- Zugangsdaten der Anbindungen liegen unverschlüsselt in `data/labvis.db` – das Verzeichnis entsprechend schützen.
- Für Zugriff von außen gehört ein Reverse Proxy mit TLS davor; das Sitzungs-Cookie wird dann nur noch über HTTPS gesendet.
- Service-Icons werden beim ersten Bedarf von [dashboard-icons](https://github.com/homarr-labs/dashboard-icons) geladen und in `data/icons` abgelegt.

## Lizenz und Dank

MIT, siehe `LICENSE`. Glyph-Icons (`glyph-*.svg`) aus homelab-diagram (MIT, Goblinmine). Schriften Fira Sans / Fira Code (SIL OFL).

Wenn dir das Projekt hilft: [Buy Me a Coffee](https://buymeacoffee.com/quentyn83)

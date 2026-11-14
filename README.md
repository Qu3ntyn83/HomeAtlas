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

Danach: `http://<host>:8099` (Benutzer `admin`, Passwort aus `.env`). Die Daten liegen in `./data`.

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

- Getestet: API, Scan-Ablauf, Proxmox- und Docker-Sync gegen Test-Server, SNMP/LLDP-Auswertung mit Beispieldaten, Container-Build und -Start.
- **Nicht** gegen echte Geräte getestet: SNMP-Abruf an realen Switches und der OPNsense-Connector (API-Pfade können je Version abweichen).
- Zugangsdaten der Anbindungen liegen unverschlüsselt in `data/labvis.db` – das Verzeichnis entsprechend schützen.
- Die eingebaute Anmeldung ist HTTP-Basic. Für Zugriff von außen gehört ein Reverse Proxy mit TLS davor.
- Service-Icons werden beim ersten Bedarf von [dashboard-icons](https://github.com/homarr-labs/dashboard-icons) geladen und in `data/icons` abgelegt.

## Lizenz und Dank

MIT, siehe `LICENSE`. Glyph-Icons (`glyph-*.svg`) aus homelab-diagram (MIT, Goblinmine). Schriften Fira Sans / Fira Code (SIL OFL).

Wenn dir das Projekt hilft: [Buy Me a Coffee](https://buymeacoffee.com/quentyn83)

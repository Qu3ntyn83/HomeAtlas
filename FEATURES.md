# HomeAtlas – Funktionen

Vollständige Übersicht, was HomeAtlas kann. Einrichtung und Betrieb stehen in der [README](README.md).

**Inhalt:** [Oberfläche](#oberfläche) · [Topologie](#topologie) · [Verbindungsarten](#verbindungsarten) · [Geräte](#geräte) ·
[Gerätetypen & Icons](#gerätetypen--icons) · [Racks](#racks) · [Netzwerke & WLAN](#netzwerke--wlan) · [IPAM & DNS](#ipam--dns) ·
[Internetzugang](#internetzugang) · [Überwachung](#überwachung) · [Scan & Funde](#scan--funde) · [Anbindungen](#anbindungen) ·
[Benutzer & Rechte](#benutzer--rechte) · [Daten & Export](#daten--export) · [Technik](#technik) · [Noch nicht umgesetzt](#noch-nicht-umgesetzt)

---

## Oberfläche

- Seitenmenü links, einklappbar auf eine Symbolleiste (wird im Browser gemerkt); auf dem Handy als Schublade
- **Eigene Links im Menü** (z. B. Radarr, IPMI) mit aufklappbaren Kategorien, Reihenfolge, Icon; Adresse und Icon aus einem Gerät übernehmbar
- Unterpunkte je Netz unter *IPAM & DNS*
- **Auswahlfelder mit Suche** in allen Formularen ab 8 Einträgen: Tippen grenzt ein (ohne Groß-/Kleinschreibung und Akzente), Pfeiltasten, Enter, Escape;
  Mehrfachauswahlen mit Filterfeld und Zähler
- Eigenes Logo, Favicon und App-Symbol; „Zum Startbildschirm hinzufügen“ legt HomeAtlas wie eine App ab
- Aktualisiert sich alle 15 Sekunden; lädt sich nach einem Update von selbst neu
- Version und Build auf der Anmeldeseite und unter *System*

## Topologie

- Geräte als Ordner-Karten (Optik von homelab-diagram), frei verschiebbar, Zoom und Verschieben auch per Touch
- **Auto-Layout** nach Ebenen (Internet → Router/Firewall → Switch → Server …), **Einpassen**, **SVG-Export**
- VMs und Container als Chips im Host, deren Container als Zeilen; Hardware-Kacheln (CPU, RAM, Platten, Netzteile …)
- **Größe von Hand:** Bereiche und Karten mit Inhalt am Griff unten rechts ziehen; die Breite bestimmt die Spaltenzahl; zweimal antippen = automatisch
- **VLAN-Filter**, Gerätesuche springt zur Karte
- **Ansicht Normal | Räume:** je Raum eine Karte, Verbindungen zwischen Räumen; Bereiche werden dort aufgelöst, auch verschachtelte – jedes Gerät steht in seinem Raum,
  ohne eigenen Raum gilt der des nächsten übergeordneten Geräts bzw. Bereichs. Geräte an einer Bridge oder einem Host mit anderem Raum (Lampe im
  Schlafzimmer an der Bridge im Keller) stehen einzeln in ihrem Raum, VMs ohne eigenen Raum bleiben im Host
- **Etagen:** Räume lassen sich Etagen zuordnen (Raumkarte anklicken oder „Etagen“ in der Raumansicht). Etagen anlegen, umbenennen,
  sortieren (oberste zuerst) und löschen. Die Raumansicht ordnet die Räume in Bändern je Etage von oben nach unten an, oben lässt sich
  auf eine Etage filtern. Etage steht auch im Geräte-Panel; Etagen und Zuordnungen sind Teil von Export und Wiederherstellung
- **Bereiche** (Gruppen), z. B. alle Lampen eines Raums; „Bereich auflösen“ löscht nichts
- **Mehrfachauswahl** (Auswählen bzw. Strg/Umschalt + Klick) mit Sammeländerung, Gruppieren, Zusammenführen, Löschen
- Statuspunkt je Gerät (online/offline/unbekannt), gelb, wenn ein Dienst des Geräts ausfällt
- Legende mit Kabelbreiten und den tatsächlich verwendeten Verbindungsarten

## Verbindungsarten

| Gruppe | Arten | Darstellung |
|---|---|---|
| Netzwerk | Kabel (Ethernet), WLAN | Kabel in VLAN-Farbe, Breite = Geschwindigkeit, Trunk hell mit dunklem Kern; WLAN gepunktet mit SSID |
| Internet | Internetzugang (WAN) | orange Doppellinie, bei Funkzugang gepunktet, beschriftet mit Zugang und Bandbreite |
| Logisch | API / Datenabfrage, logisch (VPN, Cloud) | API gestrichelt mit Pfeil vom abfragenden zum abgefragten System |
| Smarthome-Funk | Zigbee, Z-Wave, Thread, Bluetooth/BLE, DECT ULE, Homematic IP, EnOcean, 433/868 MHz, LoRa, Infrarot | gepunktet, je Art eigene Farbe und Beschriftung |
| Smarthome-Netz | Matter, MQTT | Matter strich-punktiert, MQTT gestrichelt mit Pfeil zum Broker |
| Bus | KNX, Feldbus (RS-485, Modbus, 1-Wire), USB/seriell | strich-punktiert |

- Formular zeigt nur passende Felder (Geschwindigkeit, VLAN, Trunk nur bei Kabel; SSID nur bei WLAN) und passende Beschriftungen
- **Vernetzung am Gerät** (z. B. Zigbee über die Hue Bridge) als farbige Marke am Chip; der Home-Assistant-Import setzt sie aus der Integration
- Ports an beiden Enden, Access-VLAN, Notiz

## Geräte

- Name, Typ, Netzwerk, IP, MAC, Hostname, Web-URL, Modell, System, Raum, Icon, „läuft auf / gehört zu“, Kurzbeschreibung
- **Notizen** (mehrzeilig), auf der Karte ein- und ausblendbar
- **Mehrere Adressen** je Gerät (z. B. NAS mit vier NICs): Bezeichnung und Notiz je Adresse, „Als Hauptadresse“ tauscht,
  Zustand je Adresse, online, solange eine antwortet
- **Zusammenführen** zweier Einträge (Adressen, Kabel, Kinder und Anbindungen wandern mit)
- Rack-Platz (Rack, unterste HE, Höhe)
- Knopf **IPAM** springt zur Adresse in der Adresskarte
- Abschnitte für Anbindungen, Checks, Verbindungen, enthaltene Geräte

## Gerätetypen & Icons

- 35 eingebaute Typen, darunter Server, Hypervisor, NAS, Switch, Firewall, Access Point, Client, **Smartphone, Tablet**,
  Smarthome (Lampe, Steckdose, Sensor, Thermostat, Rollladen, Türschloss, Saugroboter, Kamera, Lautsprecher, TV) und Rack-Platzhalter
- Je Typ anpassbar: **Bezeichnung, Icon, Bereich** (Netzwerk, Server, Speicher, Dienste, Smarthome, Endgeräte, Sonstiges), **Erkennung**
  (Hersteller oder Hostname enthält …), **ausblenden**; Zurücksetzen auf Standard
- **Eigene Typen** mit Vorlage („verhält sich wie“, z. B. USV wie Server → passt ins Rack); beim Löschen bekommen Geräte den Vorlagentyp
- **Eigene Icons** hochladen (SVG, PNG, WebP, JPG bis 512 KB) – auf der Typen-Seite (auch Ziehen und Ablegen) oder direkt in jedem Icon-Feld;
  SVG wird bereinigt; Name `up-…`; Verwendung je Icon sichtbar
- Service-Icons aus [dashboard-icons](https://github.com/homarr-labs/dashboard-icons) per Name, lokal zwischengespeichert

## Racks

- Racks mit beliebig vielen HE, Geräte per Ziehen umsetzen, freie HE antippen zum Einbauen
- Platzhalter: **Patchpanel** (mit Portzahl), **Rackboden** (mit den Geräten darauf), **Blende**, **Kabelführung**
- **Patchpanel-Ports beschriften:** je Port Beschriftung (Dose/Ziel), Endgerät, Switch und Switch-Port, Notiz; Port antippen oder alle als
  Liste („7: Büro 2“) bearbeiten; belegte Ports grün im Rack, Patchpanel-Port am Endgerät und am Switch sichtbar, Beschriftungen in der Suche
- Geräte ohne eigenen Raum übernehmen den Standort ihres Racks

## Netzwerke & WLAN

- VLANs mit VID, Subnetz, Gateway, Farbe, „automatisch scannen“ und Regel/Notiz
- Ansicht als Raster (IP-Belegung je Netz) oder sortierbare **Adress-Tabelle** mit Suche, Netzwerk-Filter, Mehrfachauswahl und **CSV-Export**
- **WLAN:** SSIDs mit Netz, Band, Verschlüsselung und ausstrahlenden Access Points; SSIDs als Pillen auf den AP-Karten

## IPAM & DNS

Daten aus der OPNsense (beim Abgleich der Anbindung), abgeglichen mit der Dokumentation.

- **Übersicht aller Netze:** Mini-Adresskarte, Belegung, dokumentiert/unbekannt/Konflikte/umgezogen, DHCP-Größe, nächste freie Adresse
- **Adresskarte je Netz** (bis /22 als Raster, größer als Liste): dokumentiert, nicht dokumentiert, Gateway, Reservierung, nur DNS, DHCP-Bereich,
  umgezogen, Konflikt; Klick zeigt alle Quellen (Gerät, DNS, Reservierung, Lease, ARP mit Hersteller)
- **Konflikte:** doppelte Adresse, Reservierung oder ARP mit anderer MAC, feste Adresse im DHCP-Bereich ohne Reservierung
- **Nächste freie Adresse** außerhalb des DHCP-Bereichs, mit Kopieren
- **Fehlende Netze:** Adressen, die die Firewall kennt, die aber in keinem dokumentierten Netz liegen – mit „Netz anlegen“
- **DNS-Abgleich** nach Netzen gruppiert: passt · Adresse veraltet (mit „auf … ändern“) · kein Gerät · doppelt
- **Geräte ohne DNS-Eintrag** mit Namensvorschlag, Auswahl und Sammelanlage
- **Schreiben** (nur mit Freigabe in der Anbindung): DNS-Einträge anlegen, ändern, löschen (Unbound oder Dnsmasq);
  DHCP-Reservierungen anlegen und löschen (Kea oder Dnsmasq); danach wird der Dienst neu geladen
- **ARP der Firewall:** ergänzt fehlende MAC-Adressen und Hersteller an Geräten und Funden (auch aus anderen VLANs), meldet Geräte, die unter
  einer neuen Adresse antworten („Adresse übernehmen“)

## Internetzugang

- Internet-Gerät je Leitung mit **Anschlussdaten:** Anbieter, Zugang (Glasfaser, VDSL, ADSL, Kabel, LTE, 5G, Satellit, Richtfunk), Download/Upload,
  IPv4-Art (dynamisch, statisch, CGNAT, DS-Lite), öffentliche IPv4, IPv6-Präfix, DynDNS, Modem/ONT, Kundennummer, Hotline, Laufzeit, Kosten
- Karte zeigt Anbieter, öffentliche Adresse, Zugang, Bandbreite
- **Live aus der OPNsense:** Gateway-Zustand, Latenz, Paketverlust, Prüfziel, WAN-Adresse (IPv4/IPv6), Hinweis auf NAT davor oder CGNAT;
  Gerätestatus folgt dem Gateway; bei einer Leitung und einem Gateway automatische Zuordnung
- „WAN-Verbindung anlegen“ verbindet die Leitung mit Firewall bzw. Router

## Überwachung

- **Aus Dokumentation erzeugen:** Ping je Gerät mit IP, Port-Check je bekanntem Dienst, HTTP-Check je Weboberfläche – Auswahl nach Bereich mit Vorschau
- Eigene Checks (Ping, TCP-Port, HTTP) je Gerät, Intervall je Check
- **Übersicht** nach dem Vorbild von [Overlook](https://github.com/bnlqn/overlook): was ist los, Zustand je Bereich, letzte 30 Ergebnisse,
  Verfügbarkeit 24 h, Ereignisse der Woche; Zahl der Probleme im Menü
- Problem erst nach zwei Fehlschlägen; erneute Prüfung nach 15 Sekunden; „noch nie erreichbar“ meldet nichts und lässt sich gesammelt entfernen
- **Benachrichtigungen** an beliebig viele Ziele: ntfy, Gotify, Telegram, Discord, Slack/Mattermost/Rocket.Chat, Webhook (Text oder JSON),
  E-Mail (SMTP). Je Ziel: Bereiche, nur Ausfälle/nur Wiederkehr, **Ruhezeit** (z. B. 22:00–07:00, auch nur für bestimmte Bereiche),
  Meldungen aus der Ruhezeit danach gesammelt oder gar nicht; gebündelt, Testmeldung je Ziel, letzter Fehler am Ziel sichtbar.
  Eine bisher eingetragene ntfy-/Webhook-Adresse wird beim Update als Ziel übernommen
- **Gatus-Export** der Checks
- Verlauf: Einzelergebnisse 12 Stunden, Stundenwerte 8 Tage, Ereignisse 30 Tage

## Scan & Funde

- Scan im festen Takt (Standard 60 Minuten) für alle Netze mit „automatisch scannen“ und von Hand je Netz: `nmap -sn`, Port-Scan (rund 50 typische Ports), Web-Titel, SNMP
- MACs auch für geroutete Netze und Geräte ohne Ping-Antwort über die ARP-Tabelle der Firewall
- Erkennung von Typ und Icon (Fingerprints + Erkennungsregeln der Gerätetypen) und **Vorschläge für passende Anbindungen**
- Bekannte Geräte werden über MAC bzw. IP wiedererkannt und bekommen ihren Online-Status
- **Funde:** übernehmen, als weitere Adresse an ein Gerät hängen, verwerfen; Suche
- **Nicht mehr gesehen:** Geräte, die seit 7–180 Tagen (wählbar) nicht mehr erreichbar waren, mit Herkunft und Zahl der Geräte darunter;
  löschen (einzeln oder alle), „Behalten“ für Saisongeräte, alte Funde gesammelt verwerfen. Nur dokumentierte Geräte ohne Sichtung zählen nicht

## Anbindungen

| Anbindung | liest | schreibt |
|---|---|---|
| **Proxmox VE** | Nodes (CPU, RAM, Version), VMs und LXC mit IP; erkennt Token ohne Rechte | – |
| **Docker** | Container mit Status, Image, Compose-Projekt, Ports – lokal über den Socket oder per Socket-Proxy | – |
| **SNMP v2c** | Systemname, Ports mit Status, Geschwindigkeit, PVID; LLDP-Nachbarn → Kabel | – |
| **OPNsense** | VLANs und Subnetze, DNS (Unbound/Dnsmasq), DHCP (Kea/Dnsmasq/ISC), ARP, Gateways, WAN-Adressen | DNS-Einträge, DHCP-Reservierungen (mit Freigabe) |
| **Home Assistant** | Geräte ausgewählter Integrationen mit Raum, Typ, Hersteller, Modell, Status, Vernetzung; MAC-Zuordnung über Netzwerk-Tracker | – |
| **QNAP QTS / QuTS hero** | Modell, Firmware, Netzwerkkarten, CPU, RAM, Platten mit SMART, Volumes | – |
| **Synology DSM** | Modell, DSM-Version, Netzwerkkarten, CPU, RAM, Platten, Volumes mit RAID-Typ | – |
| **IPMI / Redfish** | Mainboard, BIOS/BMC-Version, Zustand, Temperaturen, Lüfter, Leistung, Netzteile; BMC-Adresse am Server | – |
| **UniFi Network** | Gateway, Switches, APs mit Modell, Firmware, Status und Uplinks (Kabel mit Ports, Mesh per WLAN); Clients → vorhandenen Geräten zugeordnet (MAC/IP) mit Kabel zum Switch-Port bzw. WLAN mit SSID zum AP; SSIDs; auf Wunsch unbekannte Clients anlegen | – |

- Beim Anlegen ein dokumentiertes Gerät oder einen Fund auswählen; passende Treffer markiert
- Abgleich im festen Takt (unter *System*, Standard 15 Minuten) und „Synchronisieren“ von Hand; verständliche Fehlermeldungen (Port zu, TLS, Rechte, 2FA …)
- Port 80 bzw. eine Weboberfläche ohne TLS wird erkannt
- Geräte, die eine Anbindung angelegt hat, behalten von Hand vergebene Namen

## Benutzer & Rechte

- Eigene Anmeldeseite, Benutzerkonten mit **Lesen**, **Ändern**, **Admin**; der Server prüft jede Anfrage
- scrypt-Hashes, HttpOnly-Sitzungscookie (30 Tage), Abmelden aller anderen Sitzungen beim Passwortwechsel, Sperre nach Fehlversuchen
- Ersteinrichtung über Umgebungsvariable oder im Browser

## Daten & Export

- **Export/Wiederherstellung** (Admin) als JSON: Geräte, Kabel, Racks, Netzwerke, WLANs, Anbindungen, Checks, Menü-Links, Gerätetypen,
  eigene Icons, Einstellungen; ältere Exporte bleiben einspielbar
- **Automatische Sicherungen** (Admin) unter *System*: täglich zur eingestellten Stunde, dazu vor jedem Update und vor jedem Wiederherstellen;
  Datenbank (konsistent per SQLite-Backup) und eigene Icons als `.tar.gz` in `data/backups`, Anzahl einstellbar (Standard 14), herunterladen und löschen
- **Import** einer `inventory.yaml` aus homelab-diagram
- CSV-Export der Adress-Tabelle, SVG-Export der Topologie, Gatus-YAML der Checks

## Technik

- Ein Docker-Container: Python 3.12, FastAPI, SQLite (WAL), Oberfläche in reinem JavaScript ohne Build-Schritt
- Die Oberfläche fragt alle 15 Sekunden mit einem Fingerabdruck nach und zeichnet nur neu, wenn sich etwas geändert hat
- nmap und net-snmp im Image; Host-Netz mit `NET_RAW` für ARP und Ping
- Daten in `./data` (Datenbank, Icon-Zwischenspeicher, hochgeladene Icons)

## Noch nicht umgesetzt

- Anbindungen für TrueNAS, Checkmk, FRITZ!Box (TR-064), Windows
- Verschlüsselte Ablage der Zugangsdaten von Anbindungen

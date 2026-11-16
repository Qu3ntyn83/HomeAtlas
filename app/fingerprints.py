"""Erkennungsregeln: aus MAC-Hersteller, offenen Ports, HTTP-Titeln und SNMP wird ein Gerätetyp
geraten und es werden passende Schnittstellen zum Anbinden/Auslesen vorgeschlagen.

Ein Vorschlag mit connector=<kind> lässt sich direkt als Anbindung einrichten (siehe connectors.py),
alle anderen sind Hinweise, welche Schnittstelle das Gerät anbietet."""
import re

SCAN_PORTS = [21, 22, 23, 25, 53, 80, 81, 111, 135, 139, 443, 445, 515, 548, 623, 631, 902, 1880, 1883, 2049,
              2375, 2376, 3000, 3001, 3306, 3389, 5000, 5001, 5432, 5900, 5985, 6053, 8000, 8006, 8007, 8080,
              8081, 8086, 8096, 8123, 8443, 9000, 9090, 9100, 9443, 11443, 32400, 49000]
HTTP_PORTS = [80, 81, 443, 3000, 3001, 5000, 5001, 8000, 8006, 8007, 8080, 8081, 8096, 8123, 8443, 9000, 9090,
              9443, 11443]
TLS_PORTS = {443, 5001, 8006, 8007, 8443, 9443, 11443}

NET_VENDORS = r"aruba|hewlett|procurve|cisco|mikrotik|routerboard|netgear|juniper|zyxel|tp-link|d-link|extreme|brocade|ruckus|lancom"


def _s(kind, title, reason, reads, connector=None, config=None):
    return {"kind": kind, "title": title, "reason": reason, "reads": reads,
            "connector": connector, "config": config or {}}


def identify(h):
    """h: {ip, mac, vendor, hostname, ports[], http{port:{title,server}}, snmp{descr,name}}"""
    ports = set(h.get("ports") or [])
    vendor = (h.get("vendor") or "").lower()
    http = h.get("http") or {}
    titles = " | ".join((v.get("title") or "") for v in http.values()).lower()
    servers = " | ".join((v.get("server") or "") for v in http.values()).lower()
    snmp = h.get("snmp") or {}
    descr = (snmp.get("descr") or "").lower()
    ip = h.get("ip")
    out = {"type": None, "icon": None, "os": None, "model": None, "url": None, "suggestions": []}
    sug = out["suggestions"]

    def setk(**kw):
        for k, v in kw.items():
            if v and not out.get(k):
                out[k] = v

    def has(*words):
        return any(w in titles for w in words)

    def web(port):
        return f"{'https' if port in TLS_PORTS else 'http'}://{ip}:{port}"

    # ---- Hypervisoren
    if 8006 in ports or has("proxmox virtual environment"):
        setk(type="hypervisor", icon="proxmox", os="Proxmox VE", url=web(8006))
        sug.append(_s("proxmox", "Proxmox-API", "Port 8006 offen",
                      "Nodes, VMs, LXC-Container, IP-Adressen, CPU/RAM, Status", "proxmox",
                      {"host": ip, "port": 8006}))
    if 8007 in ports or has("proxmox backup server"):
        setk(type="server", icon="proxmox", os="Proxmox Backup Server", url=web(8007))
        sug.append(_s("pbs", "Proxmox-Backup-Server-API", "Port 8007 offen", "Datastores, Backup-Jobs, Belegung"))
    if has("vmware esxi", "vsphere", "vcenter") or (902 in ports and 443 in ports):
        setk(type="hypervisor", icon="vmware-esxi", os="VMware ESXi", url=web(443))
        sug.append(_s("vmware", "vSphere-API", "ESXi/vCenter erkannt", "VMs, Hosts, Datastores"))

    # ---- Docker
    if ports & {2375, 2376}:
        p = 2375 if 2375 in ports else 2376
        setk(type="server", icon="docker")
        sug.append(_s("docker", "Docker-API", f"Port {p} offen", "Container, Images, Compose-Projekte, Ports, Status",
                      "docker", {"url": f"{'http' if p == 2375 else 'https'}://{ip}:{p}"}))
    elif has("portainer", "dockhand", "dockge", "komodo"):
        setk(type="server", icon="docker")
        sug.append(_s("docker", "Docker-API (per docker-socket-proxy)", "Docker-Verwaltung erkannt",
                      "Container, Images, Compose-Projekte – dazu auf dem Host einen read-only Socket-Proxy "
                      "auf Port 2375 freigeben", "docker", {"url": f"http://{ip}:2375"}))

    # ---- Firewalls / Router
    if has("opnsense"):
        setk(type="firewall", icon="opnsense", os="OPNsense", url=web(443))
        sug.append(_s("opnsense", "OPNsense-API", "Weboberfläche erkannt",
                      "VLANs, Interfaces, Subnetze (API-Key + Secret)", "opnsense", {"host": ip}))
    if has("pfsense"):
        setk(type="firewall", icon="pfsense", os="pfSense")
        sug.append(_s("pfsense", "pfSense REST-API (Paket)", "Weboberfläche erkannt", "Interfaces, VLANs, Regeln"))
    if has("watchguard", "fireware"):
        setk(type="firewall", icon="type-firewall", os="WatchGuard Fireware")
    if has("sophos"):
        setk(type="firewall", icon="sophos", os="Sophos Firewall")
    if 49000 in ports or "avm" in vendor or has("fritz!box"):
        setk(type="router", icon="fritzbox", os="FRITZ!OS", url=f"http://{ip}")
        sug.append(_s("tr064", "TR-064 (FRITZ!Box)", "AVM-Gerät erkannt", "WAN-Status, Hosts, WLAN, Portfreigaben"))

    # ---- NAS
    if "synology" in vendor or has("synology", "diskstation") or (ports >= {5000, 5001}):
        setk(type="nas", icon="synology", os="Synology DSM", url=web(5001 if 5001 in ports else 5000))
        sug.append(_s("synology", "Synology DSM-API", "DSM erkannt", "Modell, Netzwerkkarten, Platten, Volumes, Belegung"))
    if "qnap" in vendor or has("qnap", "qts"):
        setk(type="nas", icon="qnap", os="QNAP QTS", url=web(443 if 443 in ports else 8080))
        sug.append(_s("qnap", "QNAP-API", "QNAP erkannt", "Modell, Netzwerkkarten, Platten (SMART), Volumes, Belegung"))
    if has("truenas"):
        setk(type="nas", icon="truenas", os="TrueNAS", url=web(443 if 443 in ports else 80))
        sug.append(_s("truenas", "TrueNAS-API", "Weboberfläche erkannt", "Pools, vdevs, Datasets, Belegung"))

    # ---- Dienste
    if 8123 in ports and (has("home assistant") or not titles):
        setk(type="server", icon="home-assistant", os="Home Assistant", url=web(8123))
        sug.append(_s("homeassistant", "Home-Assistant-API", "Port 8123 offen",
                      "Geräte je Integration mit Hersteller, Modell, Raum und Status (langlebiges Token)",
                      "homeassistant", {"host": f"http://{ip}:8123"}))
    if has("unifi") or (8443 in ports and 8080 in ports and "ubiquiti" not in vendor and has("unifi")):
        setk(type="server", icon="unifi", url=web(8443 if 8443 in ports else 11443))
        sug.append(_s("unifi", "UniFi-Network-API", "UniFi-Controller erkannt",
                      "Access Points, Clients, SSIDs → VLANs, Uplinks"))
    if has("checkmk", "check_mk"):
        setk(type="server", icon="checkmk")
        sug.append(_s("checkmk", "Checkmk-REST-API", "Checkmk erkannt", "Host- und Service-Status als Live-Overlay"))
    if has("emby"):
        setk(type="server", icon="emby", url=web(8096))
    if has("jellyfin"):
        setk(type="server", icon="jellyfin", url=web(8096))
    if 32400 in ports:
        setk(type="server", icon="plex")
    if has("adguard"):
        setk(type="server", icon="adguard-home")
    if has("pi-hole"):
        setk(type="server", icon="pi-hole")
    if has("nextcloud"):
        setk(type="server", icon="nextcloud")
    if has("vaultwarden", "bitwarden"):
        setk(type="server", icon="vaultwarden")
    if has("grafana"):
        setk(type="server", icon="grafana")
    if has("netbox"):
        setk(type="server", icon="netbox")
        sug.append(_s("netbox", "NetBox-API", "NetBox erkannt", "Geräte, Racks, Kabel, Prefixe, VLANs"))
    if 1883 in ports:
        sug.append(_s("mqtt", "MQTT-Broker", "Port 1883 offen", "Zigbee2MQTT/Z-Wave-Geräte über Topics"))

    # ---- Netzwerkgeräte / SNMP
    netdev = re.search(NET_VENDORS, vendor) or re.search(NET_VENDORS + r"|switch|routeros", descr)
    if descr:
        sug.append(_s("snmp", "SNMP", "Antwortet auf SNMP",
                      "Systemname, Ports mit Status und Geschwindigkeit, LLDP-Nachbarn → Kabel", "snmp",
                      {"host": ip}))
        if re.search(r"switch|procurve|aruba|catalyst|routeros", descr):
            setk(type="switch")
        setk(model=(snmp.get("descr") or "")[:60])
    elif netdev:
        sug.append(_s("snmp", "SNMP (noch nicht erreichbar)", f"Netzwerkhersteller: {h.get('vendor')}",
                      "SNMP v2c am Gerät aktivieren, dann: Ports, Geschwindigkeit, LLDP-Nachbarn → Kabel", "snmp",
                      {"host": ip}))
    if netdev and not out["type"]:
        setk(type="switch", icon="type-switch")
    if "ubiquiti" in vendor and not out["type"]:
        setk(type="ap", icon="unifi")
        sug.append(_s("unifi", "UniFi-Network-API (am Controller)", "Ubiquiti-Gerät",
                      "Wird über den UniFi-Controller ausgelesen"))

    # ---- BMC, Drucker, IoT
    if 623 in ports or has("idrac", "ilo", "supermicro", "megarac"):
        sug.append(_s("ipmi", "IPMI / Redfish", "BMC erkannt", "Hardware-Inventar, Sensoren, Power-Status"))
        setk(type="server")
    if ports & {9100, 631, 515} and not out["type"]:
        setk(type="printer", icon="type-printer")
    if 6053 in ports or re.search(r"espressif|shelly|tuya|sonoff|itead", vendor) or has("tasmota", "shelly", "esphome"):
        setk(type="iot", icon="type-iot")
        sug.append(_s("homeassistant", "über Home Assistant", "IoT-Gerät erkannt",
                      "ESPHome/Tasmota/Shelly werden am einfachsten über Home Assistant inventarisiert"))
    if "raspberry" in vendor:
        setk(type="server", icon="raspberry-pi", model="Raspberry Pi")

    # ---- Betriebssystem-Indizien
    if 3389 in ports or (ports >= {135, 445}):
        setk(type="workstation" if 3389 in ports and 22 not in ports else "server", icon="windows", os="Windows")
        sug.append(_s("winrm", "WinRM / WMI", "Windows-Ports offen", "Hardware, Rollen, Dienste (Port 5985)"))
    elif 22 in ports and not out["type"]:
        setk(type="server", icon="linux")
    if 22 in ports and out["type"] in ("server", "hypervisor", "nas"):
        sug.append(_s("ssh", "SSH (read-only)", "Port 22 offen", "Hardware, Disks, Dienste per Schlüssel-Login"))
    if re.search(r"apple|samsung|google|amazon|sonos|xiaomi|lg electronics|sony|nintendo", vendor) and not out["type"]:
        setk(type="client", icon="type-client")
    if not out["url"]:
        for p in (443, 80, 8080, 8443, 3000, 9000):
            if p in ports:
                out["url"] = web(p)
                break
    setk(type="other")
    # doppelte Vorschläge (gleiche Art) entfernen
    seen, uniq = set(), []
    for s in sug:
        if s["kind"] not in seen:
            seen.add(s["kind"])
            uniq.append(s)
    out["suggestions"] = uniq
    return out

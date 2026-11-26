"""Anbindungen: lesen Systeme aus und pflegen Geräte, Kinder (VMs/Container), Ports und Kabel.

proxmox  – API-Token (read-only, Rolle PVEAuditor)
docker   – Docker-Engine-API, am besten über einen read-only docker-socket-proxy
snmp     – v2c über die net-snmp-Werkzeuge: Ports, Geschwindigkeit, PVID, LLDP-Nachbarn
opnsense – API-Key/Secret: VLANs, Subnetze, DNS, DHCP, ARP, Gateways (IPAM & DNS, Internetzugang)
"""
import base64
import http.client
import http.cookiejar
import ipaddress
import json
import re
import shutil
import socket
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import db

KINDS = {
    "proxmox": {"label": "Proxmox VE", "fields": [
        ["host", "Host/IP"], ["port", "Port", "8006"], ["token_id", "Token-ID (user@pve!name)"],
        ["token_secret", "Token-Secret", "", "password"]],
        "help": "Der Token braucht selbst Leserechte: Bei aktivierter „Privilege Separation“ (Standard) erbt er die Rechte des "
                "Benutzers nicht. In Proxmox unter Datacenter → Permissions → Add → API Token Permission den Pfad „/“, den Token und "
                "die Rolle „PVEAuditor“ eintragen (Propagate an). Ohne das meldet sich HomeAtlas zwar an, sieht aber keine VMs und Container."},
    "docker": {"label": "Docker", "fields": [["url", "API-URL (http://host:2375) – leer = lokaler Docker auf dem HomeAtlas-Host"]],
               "help": "Für den Docker auf dem Host, auf dem HomeAtlas selbst läuft, das Feld leer lassen: HomeAtlas liest dann über den "
                       "Docker-Socket. Dafür muss in der docker-compose.yml unter volumes die Zeile "
                       "„- /var/run/docker.sock:/var/run/docker.sock:ro“ stehen (in der aktuellen Vorlage enthalten). "
                       "Für andere Hosts die Adresse einer freigegebenen Docker-API oder eines docker-socket-proxy eintragen."},
    "snmp": {"label": "SNMP v2c", "fields": [["host", "Host/IP"], ["community", "Community", "public", "password"]]},
    "opnsense": {"label": "OPNsense", "fields": [
        ["host", "Host/IP oder URL (https://firewall:8443)"], ["port", "Port der Weboberfläche (80 = ohne TLS)", "443"], ["key", "API-Key"],
        ["secret", "API-Secret", "", "password"], ["write", "Änderungen an DNS-Einträgen und DHCP-Reservierungen erlauben", "", "check"]],
        "help": "Liest VLANs, DNS-Einträge (Unbound oder Dnsmasq), DHCP-Leases und -Reservierungen (Kea, Dnsmasq, ISC) und die ARP-Tabelle "
                "für die Seite „IPAM & DNS“. Der API-Benutzer braucht dafür Leserechte auf diese Seiten; zum Anlegen und Ändern "
                "zusätzlich Schreibrechte und den Haken unten. Ohne TLS (Port 80) gehen API-Schlüssel unverschlüsselt durchs Netz."},
    "qnap": {"label": "QNAP QTS / QuTS hero", "fields": [
        ["host", "Host/IP oder URL (https://nas:443)"], ["port", "Port der Weboberfläche", "443"], ["user", "Benutzer (Administratorgruppe)"],
        ["password", "Passwort", "", "password"]],
        "help": "QTS kennt keine API-Schlüssel – HomeAtlas meldet sich mit einem Benutzer an. Lege dafür am NAS einen eigenen Benutzer an "
                "(Systemsteuerung → Benutzer), Gruppe „administrators“, ohne zweistufige Anmeldung, mit langem Zufallspasswort und "
                "ohne Zugriff auf Freigaben. HomeAtlas liest nur und meldet sich nach jedem Abruf wieder ab."},
    "synology": {"label": "Synology DSM", "fields": [
        ["host", "Host/IP oder URL (https://nas:5001)"], ["port", "Port der Weboberfläche", "5001"], ["user", "Benutzer (Administratorgruppe)"],
        ["password", "Passwort", "", "password"]],
        "help": "DSM kennt keine API-Schlüssel – HomeAtlas meldet sich mit einem Benutzer an. Lege dafür in DSM einen eigenen Benutzer an "
                "(Systemsteuerung → Benutzer & Gruppe), Gruppe „administrators“, ohne 2-Faktor-Authentifizierung, mit langem Zufallspasswort, "
                "ohne Zugriff auf Freigaben und unter „Anwendungen“ nur DSM erlaubt. HomeAtlas liest nur und meldet sich nach jedem Abruf wieder ab."},
    "ipmi": {"label": "IPMI / Redfish (Supermicro, iDRAC, iLO)", "fields": [
        ["host", "Adresse des BMC (IPMI-Anschluss)"], ["port", "Port", "443"], ["user", "Benutzer", "ADMIN"], ["password", "Passwort", "", "password"]],
        "help": "Liest über Redfish, die HTTPS-Schnittstelle des BMC. Lege im IPMI einen eigenen Benutzer mit der Stufe „Operator“ oder "
                "„ReadOnly“ an. Bei „Gehört zu Gerät“ den Server wählen, zu dem der BMC gehört – die IPMI-Adresse wird dann dessen "
                "zusätzliche Adresse. Ältere Boards (z. B. Supermicro X10) brauchen dafür eine aktuelle BMC-Firmware."},
    "unifi": {"label": "UniFi Network", "fields": [
        ["host", "Adresse der Konsole/des Controllers (https://192.168.1.1)"], ["port", "Port (leer = automatisch: 443, 8443, 11443)"],
        ["site", "Standort-ID", "default"], ["api_key", "API-Key (nur UniFi OS: Konsole oder UniFi OS Server)", "", "password"],
        ["user", "oder: lokaler Benutzer"], ["password", "Passwort", "", "password"],
        ["clients", "Unbekannte Clients als Geräte anlegen (Bereich „UniFi-Clients“)", "", "check"]],
        "help": "UniFi-Konsole (UDM, UCG, Cloud Key): Port 443. UniFi OS Server: 11443. Selbst betriebene Network Application "
                "(z. B. im Docker): Port 8443 – nicht 8080, das ist nur der Inform-Port der Geräte. Leer lassen probiert alle drei. "
                "Die selbst betriebene Network Application kennt keine API-Keys: dort einen lokalen Benutzer nehmen. "
                "Liest Access Points, Switches und Gateway mit ihren Uplinks sowie die verbundenen Clients. Clients werden vorhandenen "
                "Geräten über MAC oder IP zugeordnet und bekommen ihre Verbindung: per Kabel mit Switch-Port, per WLAN mit SSID zum "
                "Access Point. Unter UniFi OS am besten einen API-Key nehmen (Network → Einstellungen → Control Plane → Integrationen). "
                "Sonst einen lokalen Benutzer anlegen (Einstellungen → Admins & Benutzer, „Nur lokaler Zugriff“, Rolle „Nur ansehen“); "
                "Ubiquiti-Konten mit Zwei-Faktor gehen nicht. "
                "Von Hand dokumentierte Verbindungen haben Vorrang."},
    "homeassistant": {"label": "Home Assistant", "fields": [
        ["host", "URL (http://homeassistant:8123)"], ["token", "Langlebiges Zugriffstoken", "", "password"]]},
}
PALETTE = ["#58a6ff", "#f0883e", "#bc8cff", "#3fb950", "#e3b341", "#39c5cf", "#f85149", "#ff7b72", "#a5d6ff"]
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=_CTX))


def _get(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {})
    with _OPENER.open(req, timeout=timeout) as r:      # direkt, ohne Proxy aus der Umgebung – Ziele liegen im LAN
        return json.loads(r.read().decode())


def reach(host, port, timeout=4):
    """Prüft vorab, ob der Port überhaupt antwortet – damit die Fehlermeldung sagt, woran es liegt."""
    try:
        socket.create_connection((host, int(port)), timeout=timeout).close()
    except socket.timeout:
        raise RuntimeError(f"Keine Antwort von {host}:{port}. Stimmen Adresse und Port, und erlaubt die Firewall "
                           f"den Zugriff vom HomeAtlas-Host auf diesen Port?") from None
    except ConnectionRefusedError:
        raise RuntimeError(f"{host}:{port} lehnt die Verbindung ab – dort läuft kein Dienst. "
                           f"Stimmt der Port?") from None
    except OSError as e:
        raise RuntimeError(f"{host}:{port} nicht erreichbar ({e.strerror or e})") from None


def explain(e, what="API"):
    """Macht aus technischen Ausnahmen eine Meldung, mit der man etwas anfangen kann."""
    if isinstance(e, urllib.error.HTTPError):
        return {401: f"{what}: Anmeldung abgelehnt (401) – Schlüssel/Token prüfen",
                403: f"{what}: Zugriff verweigert (403) – dem Benutzer fehlen die Rechte",
                404: f"{what}: Adresse nicht gefunden (404) – Version der Gegenstelle zu alt oder Pfad anders"
                }.get(e.code, f"{what}: HTTP-Fehler {e.code}")
    if isinstance(e, urllib.error.URLError):
        r = e.reason
        if isinstance(r, (socket.timeout, TimeoutError)) or "timed out" in str(r):
            return f"{what}: Zeitüberschreitung – die Gegenstelle antwortet nicht rechtzeitig"
        if isinstance(r, ssl.SSLError):
            return f"{what}: TLS-Fehler – spricht der Port wirklich HTTPS? ({r.reason or r})"
        return f"{what}: {r}"
    if isinstance(e, (socket.timeout, TimeoutError)):
        return f"{what}: Zeitüberschreitung – die Gegenstelle antwortet nicht rechtzeitig"
    if isinstance(e, KeyError):
        return f"Einstellung fehlt: {e.args[0]}"
    return str(e)


def endpoint(cfg, default_port, scheme="https"):
    """host darf auch eine ganze URL sein (https://fw.lan:8443) – liefert (schema, host, port)."""
    raw = (cfg.get("host") or "").strip()
    if "://" in raw:
        u = urllib.parse.urlparse(raw)
        return u.scheme, u.hostname, u.port or cfg.get("port") or (443 if u.scheme == "https" else 80)
    host, _, p = raw.partition(":")
    port = p or cfg.get("port") or default_port
    if str(port).strip() == "80":                    # Port 80 ist unverschlüsselt – auch ohne http:// davor
        scheme = "http"
    return scheme, host, port


def vlan_for_ip(ip):
    try:
        a = ipaddress.ip_address(ip)
    except (ValueError, TypeError):
        return None
    for v in db.q("SELECT id, subnet FROM vlans WHERE subnet IS NOT NULL AND subnet<>''"):
        try:
            if a in ipaddress.ip_network(v["subnet"], strict=False):
                return v["id"]
        except ValueError:
            pass
    return None


def _upsert(integ, ext_id, data, adopt_ip=None, adopt_name=None, adopt_mac=None):
    """Gerät dieser Anbindung anlegen/aktualisieren; vorhandene (gescannte) Geräte werden übernommen."""
    dev = db.one("SELECT * FROM devices WHERE integration_id=? AND ext_id=?", (integ["id"], ext_id))
    adopted = not dev
    if not dev and adopt_mac:
        dev = db.one("SELECT * FROM devices WHERE lower(mac)=lower(?) AND integration_id IS NULL", (adopt_mac,))
    if not dev and adopt_ip:
        dev = db.one("SELECT * FROM devices WHERE ip=? AND integration_id IS NULL", (adopt_ip,))
    if not dev and adopt_name:
        dev = db.one("SELECT * FROM devices WHERE lower(name)=lower(?) AND integration_id IS NULL", (adopt_name,))
    if dev:
        # dokumentierte/übernommene Geräte behalten ihre eigenen Angaben, nur Status und Technik werden gepflegt
        own = adopted or (dev["meta"] or {}).get("adopted") or dev["source"] != integ["kind"]
        keep = {"name", "icon", "note", "type", "url", "vlan_id"} if own else {"icon"}
        upd = {k: v for k, v in data.items() if v is not None and not (k in keep and dev.get(k))}
        upd["meta"] = {**(dev["meta"] or {}), **(upd.get("meta") or {}), **({"adopted": True} if own else {})}
        upd.update(integration_id=integ["id"], ext_id=ext_id)
        db.update("devices", dev["id"], upd)
        return dev["id"]
    data = {**data, "integration_id": integ["id"], "ext_id": ext_id, "source": integ["kind"]}
    if data.get("ip") and not data.get("vlan_id"):
        data["vlan_id"] = vlan_for_ip(data["ip"])
    return db.insert("devices", data)


def _prune(integ, prefix, seen):
    for d in db.q("SELECT id, ext_id FROM devices WHERE integration_id=? AND ext_id LIKE ?", (integ["id"], prefix + "%")):
        if d["ext_id"] not in seen:
            db.delete_device(d["id"])


# ------------------------------------------------------------------ Proxmox
def proxmox_updates(px, nn, node_id, os_name):
    """Ausstehende Paket-Updates des Nodes (Stand des letzten „apt update“ auf dem Node, HomeAtlas stößt keins an).
    Braucht Sys.Audit (ab PVE 8.4/9) bzw. Sys.Modify bei älteren Versionen."""
    from . import updates
    try:
        pk = px(f"/nodes/{nn}/apt/update") or []
    except urllib.error.HTTPError as e:
        return "Paket-Updates: Recht fehlt (Sys.Audit, ältere PVE: Sys.Modify)" if e.code in (401, 403) else ""
    except Exception:  # noqa: BLE001
        return ""
    pm = next((p for p in pk if p.get("Package") == "pve-manager"), None)
    inst = (os_name or "").replace("Proxmox VE ", "") or None
    item = {"key": "proxmox:apt", "title": "Paket-Updates", "installed": pm.get("OldVersion") if pm else inst,
            "latest": pm.get("Version") if pm else None, "available": bool(pk), "count": len(pk)}
    updates.record(node_id, "proxmox", [item])
    return f"{len(pk)} Paket-Updates" if pk else "Pakete aktuell"


def sync_proxmox(integ):
    c = integ["config"]
    _, phost, pport = endpoint(c, 8006)
    reach(phost, pport)
    base = f"https://{phost}:{pport}/api2/json"
    hdr = {"Authorization": f"PVEAPIToken={c['token_id']}={c['token_secret']}"}

    def px(path):
        return _get(base + path, hdr)["data"]

    def rights_hint(what):
        """Ein Token ohne eigene Rechte meldet sich an, bekommt aber leere Listen – das ist von „keine Gäste“ nicht zu unterscheiden."""
        try:
            perms = px("/access/permissions")
        except Exception:  # noqa: BLE001
            perms = None
        if perms is not None and any(isinstance(v, dict) and v.get("VM.Audit") for v in perms.values()):
            return None
        tok = c.get("token_id") or ""
        return (f"Proxmox: angemeldet, aber {what}. Dem Token {tok} fehlen eigene Leserechte: Datacenter → Permissions → Add → "
                f"API Token Permission, Pfad „/“, Rolle „PVEAuditor“.")

    seen, n, apt_notes = set(), 0, []
    nodes = px("/nodes")
    if not nodes:
        raise RuntimeError(rights_hint("es kommt kein Node zurück") or "Proxmox liefert keinen Node")
    for node in nodes:
        nn = node["node"]
        nd = {"name": nn, "type": "hypervisor", "icon": "proxmox",
              "status": "online" if node.get("status") == "online" else "offline", "last_seen": db.now()}
        try:
            st = px(f"/nodes/{nn}/status")
            cpu, mem = st.get("cpuinfo", {}), st.get("memory", {})
            nd["os"] = "Proxmox VE " + (st.get("pveversion", "").split("/")[1] if "/" in st.get("pveversion", "") else "")
            nd["meta"] = {"hw": [
                {"icon": "glyph-cpu", "label": "CPU", "value": re.sub(r"\(R\)|\(TM\)|CPU ", "", cpu.get("model", "")).strip(),
                 "sub": f"{cpu.get('sockets', 1)} Sockel · {cpu.get('cores', '?')} Kerne · {cpu.get('cpus', '?')} Threads"},
                {"icon": "glyph-ram", "label": "MEMORY", "value": f"{round(mem.get('total', 0) / 2**30)} GB",
                 "sub": f"{round(mem.get('used', 0) / 2**30)} GB belegt"}]}
        except Exception:
            pass
        node_id = None
        if integ.get("device_id") and db.one("SELECT id FROM devices WHERE id=?", (integ["device_id"],)):
            first = db.one("SELECT id FROM devices WHERE integration_id=? AND ext_id LIKE 'node/%'", (integ["id"],))
            target = db.one("SELECT * FROM devices WHERE id=?", (integ["device_id"],))
            if (not first and not target["ext_id"]) or target["ext_id"] == f"node/{nn}":
                db.update("devices", target["id"], {"integration_id": integ["id"], "ext_id": f"node/{nn}"})
        node_id = _upsert(integ, f"node/{nn}", nd, adopt_name=nn)
        seen.add(f"node/{nn}")
        apt_notes.append(proxmox_updates(px, nn, node_id, nd.get("os")))
        if node.get("status") != "online":
            continue
        for kind, typ in (("qemu", "vm"), ("lxc", "container")):
            for g in px(f"/nodes/{nn}/{kind}"):
                if g.get("template"):
                    continue
                vmid, ip = g["vmid"], None
                if g.get("status") == "running":
                    try:
                        if kind == "lxc":
                            for i in px(f"/nodes/{nn}/lxc/{vmid}/interfaces"):
                                if i.get("name") != "lo" and i.get("inet"):
                                    ip = i["inet"].split("/")[0]
                                    break
                        else:
                            for i in px(f"/nodes/{nn}/qemu/{vmid}/agent/network-get-interfaces")["result"]:
                                for a in i.get("ip-addresses", []):
                                    if a.get("ip-address-type") == "ipv4" and not a["ip-address"].startswith("127."):
                                        ip = ip or a["ip-address"]
                    except Exception:
                        pass
                label = "VM" if kind == "qemu" else "CT"
                data = {"name": g.get("name") or f"{label} {vmid}", "type": typ, "parent_id": node_id, "ip": ip,
                        "status": "online" if g.get("status") == "running" else "offline",
                        "last_seen": db.now() if g.get("status") == "running" else None,
                        "note": f"{label} {vmid} · {g.get('cpus', '?')} vCPU · {round(g.get('maxmem', 0) / 2**30, 1):g} GB",
                        "meta": {"vmid": vmid, "node": nn}}
                _upsert(integ, f"guest/{vmid}", data, adopt_ip=ip, adopt_name=g.get("name"))
                seen.add(f"guest/{vmid}")
                n += 1
    if not n:
        hint = rights_hint("es kommen keine VMs und Container zurück")
        if hint:
            raise RuntimeError(hint)                # vorhandene Gäste bleiben stehen, statt als verschwunden zu gelten
    _prune(integ, "guest/", seen)
    return f"{len(nodes)} {'Node' if len(nodes) == 1 else 'Nodes'} · {n} Gäste" + "".join(" · " + a for a in dict.fromkeys(apt_notes) if a)


# ------------------------------------------------------------------ Docker
GENERIC = {"server", "app", "core", "backend", "web", "docker", "main", "latest", "frontend", "aio"}


def icon_from_image(image):
    parts = [p for p in image.split("@")[0].split(":")[0].split("/") if p]
    for p in reversed(parts):
        p = re.sub(r"^(docker-|lscr\.io|ghcr\.io)", "", p)
        if p and p not in GENERIC and "." not in p:
            return p.lower()
    return "docker"


DOCKER_SOCK = "/var/run/docker.sock"


def _unix_get(sock_path, path, timeout=15):
    """HTTP-GET über einen Unix-Socket (lokaler Docker)."""
    conn = http.client.HTTPConnection("localhost", timeout=timeout)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(sock_path)
    except FileNotFoundError:
        raise RuntimeError(f"Docker-Socket {sock_path} fehlt im HomeAtlas-Container. In der docker-compose.yml unter volumes "
                           f"„- /var/run/docker.sock:/var/run/docker.sock:ro“ ergänzen und „docker compose up -d“ ausführen") from None
    except PermissionError:
        raise RuntimeError(f"Kein Zugriff auf {sock_path} – der HomeAtlas-Container muss als root laufen (Standard)") from None
    except OSError as e:
        raise RuntimeError(f"Docker-Socket {sock_path} antwortet nicht ({e.strerror or e}) – läuft Docker auf dem Host?") from None
    conn.sock = s
    try:
        conn.request("GET", path, headers={"Host": "docker"})
        r = conn.getresponse()
        body = r.read()
        if r.status >= 400:
            raise RuntimeError(f"Docker: HTTP-Fehler {r.status}")
        return json.loads(body.decode())
    finally:
        conn.close()


def local_ips():
    """IPv4-Adressen des HomeAtlas-Hosts (der Container läuft im Host-Netz), die Hauptadresse zuerst."""
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))                   # sendet nichts, liefert nur die Absenderadresse der Standardroute
        out.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        r = subprocess.run(["ip", "-4", "-o", "addr", "show", "scope", "global"], capture_output=True, text=True, timeout=5)
        for ln in r.stdout.splitlines():
            m = re.search(r"^\d+:\s+(\S+)\s+inet\s+([\d.]+)/", ln)
            if m and not m.group(1).startswith(("docker", "br-", "veth", "virbr", "cni", "flannel", "tailscale")) and m.group(2) not in out:
                out.append(m.group(2))
    except (OSError, subprocess.SubprocessError):
        pass
    return [i for i in out if not i.startswith("127.")]


def sync_docker(integ):
    c = integ["config"]
    url = (c.get("url") or "").strip().rstrip("/")
    local = url.lower() in ("", "local", "lokal") or url.startswith("unix://")
    parent = integ.get("device_id")
    if parent and not db.one("SELECT id FROM devices WHERE id=?", (parent,)):
        parent = None
    if local:
        sock = url[7:] if url.startswith("unix://") else DOCKER_SOCK
        get = lambda p: _unix_get(sock, p)            # noqa: E731
        info = get("/info")
        ips = local_ips()
        if not parent:
            d = next((x for x in (db.one("SELECT id FROM devices WHERE ip=?", (i,)) for i in ips) if x), None) or \
                (db.one("SELECT id FROM devices WHERE lower(name)=? OR lower(hostname)=?", ((info.get("Name") or "").lower(),) * 2) if info.get("Name") else None)
            parent = d["id"] if d else db.insert("devices", {"name": info.get("Name") or "Docker-Host", "ip": ips[0] if ips else None, "type": "server",
                                                              "icon": "docker", "vlan_id": vlan_for_ip(ips[0]) if ips else None})
        host = (db.one("SELECT ip FROM devices WHERE id=?", (parent,)) or {}).get("ip") or (ips[0] if ips else "localhost")
    else:
        pu = urllib.parse.urlparse(url)
        host = pu.hostname
        if not host:
            raise RuntimeError("Die API-URL muss mit http:// oder https:// beginnen – oder leer bleiben für den lokalen Docker")
        reach(host, pu.port or (443 if pu.scheme == "https" else 80))
        get = lambda p: _get(url + p)                 # noqa: E731
        if not parent:
            d = db.one("SELECT id FROM devices WHERE ip=?", (host,))
            parent = d["id"] if d else db.insert("devices", {"name": host, "ip": host, "type": "server", "icon": "docker",
                                                              "vlan_id": vlan_for_ip(host)})
    if parent != integ.get("device_id"):
        db.update("integrations", integ["id"], {"device_id": parent})
    seen = set()
    for ct in get("/containers/json?all=1"):
        name = (ct.get("Names") or ["/?"])[0].lstrip("/")
        pub = sorted({p["PublicPort"] for p in ct.get("Ports", []) if p.get("PublicPort")})
        labels = ct.get("Labels") or {}
        running = ct.get("State") == "running"
        data = {"name": name, "type": "container", "parent_id": parent, "icon": icon_from_image(ct.get("Image", "")),
                "note": ct.get("Image", "").split("@")[0], "status": "online" if running else "offline",
                "last_seen": db.now() if running else None, "ports": pub,
                "url": f"http://{host}:{pub[0]}" if pub else None,
                "meta": {"compose": labels.get("com.docker.compose.project"), "state": ct.get("Status")}}
        _upsert(integ, f"ctr/{name}", data)
        seen.add(f"ctr/{name}")
    _prune(integ, "ctr/", seen)
    db.update("devices", parent, {"status": "online", "last_seen": db.now()})
    return f"{len(seen)} Container" + (" · lokaler Docker" if local else "")


# ------------------------------------------------------------------ SNMP
def _walk(host, community, oid):
    r = subprocess.run(["snmpwalk", "-v2c", "-c", community, "-t", "2", "-r", "1", "-OQn", host, oid],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        err = [ln for ln in (r.stderr or "").splitlines() if ln.strip() and not ln.startswith("Created directory")]
        msg = err[-1].strip() if err else "SNMP-Fehler"
        if "Timeout" in msg or "No Response" in msg:
            msg = (f"Keine SNMP-Antwort von {host}. Ist SNMP v2c am Gerät aktiv, stimmt die Community, und darf "
                   f"der HomeAtlas-Host abfragen (Zugriffsliste am Gerät, UDP 161)?")
        raise RuntimeError(msg[:300])
    return parse_walk(r.stdout, oid)


def parse_walk(text, oid):
    out, pre = {}, "." + oid.lstrip(".") + "."
    for ln in text.splitlines():
        if " = " not in ln:
            continue
        k, v = ln.split(" = ", 1)
        if k.startswith(pre) and "No Such" not in v:
            out[k[len(pre):]] = v.strip().strip('"')
    return out


def speed_label(mbps):
    try:
        m = int(mbps)
    except (TypeError, ValueError):
        return "1G"
    for lim, lab in ((40000, "40G"), (25000, "25G"), (10000, "10G"), (5000, "5G"), (2500, "2.5G"), (1000, "1G")):
        if m >= lim:
            return lab
    return "100M"


def build_ifaces(w):
    """w: dict der Walk-Ergebnisse → Portliste. Getrennt vom Abruf, damit es testbar bleibt."""
    locport = w.get("lldp_loc", {})
    neigh = {}
    for idx, name in w.get("lldp_name", {}).items():
        parts = idx.split(".")
        if len(parts) >= 2:
            neigh[parts[1]] = {"neighbor": name, "neighbor_port": w.get("lldp_port", {}).get(idx, "")}
    name2lldp = {v: k for k, v in locport.items()}
    ifaces = []
    for idx, name in w.get("name", {}).items():
        typ = w.get("type", {}).get(idx, "6")
        if not (typ in ("6", "117", "62", "69") or "ethernet" in typ.lower()):   # Ethernet, GbE, Fast Ethernet
            continue
        oper = w.get("oper", {}).get(idx, "")
        n = neigh.get(idx) or neigh.get(name2lldp.get(name, "-")) or {}
        ifaces.append({"idx": int(idx), "name": name, "alias": w.get("alias", {}).get(idx, ""),
                       "up": oper in ("1", "up") or oper.startswith("up"),
                       "speed": speed_label(w.get("speed", {}).get(idx)), "pvid": w.get("pvid", {}).get(idx),
                       **n})
    return sorted(ifaces, key=lambda i: i["idx"])


def sync_snmp(integ):
    if not shutil.which("snmpwalk"):
        raise RuntimeError("snmpwalk ist nicht installiert")
    c = integ["config"]
    host, com = c["host"], c.get("community") or db.setting("snmp_community")
    oids = {"sys": "1.3.6.1.2.1.1", "name": "1.3.6.1.2.1.31.1.1.1.1", "alias": "1.3.6.1.2.1.31.1.1.1.18",
            "speed": "1.3.6.1.2.1.31.1.1.1.15", "oper": "1.3.6.1.2.1.2.2.1.8", "type": "1.3.6.1.2.1.2.2.1.3"}
    w = {"sys": _walk(host, com, oids["sys"])}
    for k, o in oids.items():                       # nicht jedes Gerät kennt jede Tabelle (Drucker, PDUs)
        if k != "sys":
            try:
                w[k] = _walk(host, com, o)
            except RuntimeError:
                w[k] = {}
    if not w["name"]:                               # ohne ifXTable: Namen aus ifDescr
        try:
            w["name"] = _walk(host, com, "1.3.6.1.2.1.2.2.1.2")
        except RuntimeError:
            pass
    for k, o in {"pvid": "1.3.6.1.2.1.17.7.1.4.5.1.1", "lldp_name": "1.0.8802.1.1.2.1.4.1.1.9",
                 "lldp_port": "1.0.8802.1.1.2.1.4.1.1.7", "lldp_loc": "1.0.8802.1.1.2.1.3.7.1.3"}.items():
        try:
            w[k] = _walk(host, com, o)
        except Exception:
            w[k] = {}
    ifaces = build_ifaces(w)
    sysname, descr = w["sys"].get("5.0", ""), w["sys"].get("1.0", "")
    dev = db.one("SELECT * FROM devices WHERE id=?", (integ.get("device_id") or 0,)) or \
        db.one("SELECT * FROM devices WHERE ip=?", (host,))
    if not dev:
        did = db.insert("devices", {"name": sysname or host, "ip": host, "type": "switch", "vlan_id": vlan_for_ip(host)})
        dev = db.one("SELECT * FROM devices WHERE id=?", (did,))
    db.update("integrations", integ["id"], {"device_id": dev["id"]})
    meta = {**(dev["meta"] or {}), "ifaces": ifaces, "sysdescr": descr}
    upd = {"meta": meta, "status": "online", "last_seen": db.now()}
    if not dev.get("hostname") and sysname:
        upd["hostname"] = sysname
    if not dev.get("model") and descr:
        upd["model"] = descr[:60]
    db.update("devices", dev["id"], upd)
    made = apply_lldp(dev["id"], ifaces)
    label = sysname or descr[:40] or host
    if not ifaces:
        return f"{label} · antwortet, meldet aber keine Netzwerk-Ports"
    return f"{label} · {len(ifaces)} Ports, {sum(1 for i in ifaces if i.get('neighbor'))} LLDP-Nachbarn, {made} neue Kabel"


def apply_lldp(dev_id, ifaces):
    made = 0
    for i in ifaces:
        nb = (i.get("neighbor") or "").strip()
        if not nb:
            continue
        short = nb.split(".")[0]
        other = db.one("SELECT id FROM devices WHERE id<>? AND (lower(name) IN (lower(?),lower(?)) OR "
                       "lower(hostname) IN (lower(?),lower(?)))", (dev_id, nb, short, nb, short))
        if not other:
            continue
        ex = db.one("SELECT id FROM links WHERE (a_id=? AND b_id=? AND ifnull(a_port,'') IN ('',?)) OR "
                    "(a_id=? AND b_id=? AND ifnull(b_port,'') IN ('',?))",
                    (dev_id, other["id"], i["name"], other["id"], dev_id, i["name"]))
        if ex:
            db.update("links", ex["id"], {"speed": i["speed"]})
            continue
        db.insert("links", {"a_id": dev_id, "b_id": other["id"], "a_port": i["name"],
                            "b_port": i.get("neighbor_port") or "", "speed": i["speed"], "source": "snmp"})
        made += 1
    return made


# ------------------------------------------------------------------ OPNsense
class OpnClient:
    """Zugang zur OPNsense-API. Befehle werden in der neuen Schreibweise (search_host_override) aufgerufen; ältere
    Versionen kennen nur camelCase (searchHostOverride) – darauf wird bei 404 ausgewichen."""

    def __init__(self, c):
        scheme, host, port = endpoint(c, 443)
        if not c.get("key") or not c.get("secret"):
            raise RuntimeError("API-Key und API-Secret fehlen (OPNsense: System → Zugang → Benutzer → API-Schlüssel)")
        reach(host, port)
        self.hdr = {"Authorization": "Basic " + base64.b64encode(f"{c['key'].strip()}:{c['secret'].strip()}".encode()).decode(),
                    "Accept": "application/json"}
        if scheme == "https" and "://" not in (c.get("host") or ""):      # Weboberfläche ohne TLS auf einem anderen Port: selbst erkennen
            try:
                _get(f"https://{host}:{port}/api/core/firmware/status", self.hdr, timeout=8)
            except urllib.error.URLError as e:
                if isinstance(e.reason, ssl.SSLError) and not isinstance(e, urllib.error.HTTPError):
                    scheme = "http"
            except Exception:  # noqa: BLE001 – alles andere klärt der eigentliche Abruf
                pass
        self.base = f"{scheme}://{host}:{port}/api"
        self.write = str(c.get("write") or "").lower() in ("1", "true", "on", "yes")

    @staticmethod
    def _alts(path):
        seg = path.split("/")                     # ['', modul, controller, befehl, (uuid)]
        if len(seg) > 3 and "_" in seg[3]:
            camel = seg[3].split("_")[0] + "".join(w.title() for w in seg[3].split("_")[1:])
            return [path, "/".join(seg[:3] + [camel] + seg[4:])]
        return [path]

    def _req(self, path, body=None, timeout=20):
        data = json.dumps(body).encode() if body is not None else None
        h = dict(self.hdr, **({"Content-Type": "application/json"} if data is not None else {}))
        req = urllib.request.Request(self.base + path, data=data, headers=h, method="POST" if data is not None else "GET")
        with _OPENER.open(req, timeout=timeout) as r:
            raw = r.read().decode()
        return json.loads(raw) if raw.strip() else {}

    def call(self, path, body=None, timeout=20):
        err = None
        for p in self._alts(path):
            try:
                return self._req(p, body, timeout)
            except urllib.error.HTTPError as e:
                err = e
                if e.code != 404:
                    break
        raise err

    def search(self, path):
        r = self.call(path, {"current": 1, "rowCount": -1, "searchPhrase": ""})
        return r.get("rows", []) if isinstance(r, dict) else (r or [])


def sync_opnsense(integ):
    cli = OpnClient(integ["config"])
    base, hdr = cli.base, cli.hdr

    def first(*paths):
        err = None
        for p in paths:
            try:
                r = _get(base + p, hdr)
                return r.get("rows", r) if isinstance(r, dict) else r
            except urllib.error.HTTPError as e:
                err = e
                if e.code in (401, 403):            # falsche Zugangsdaten: zweiter Pfad hilft nicht
                    break
            except Exception as e:  # noqa: BLE001
                err = e
        raise RuntimeError(explain(err, "OPNsense"))

    vl = first("/interfaces/vlan_settings/search_item", "/interfaces/vlan_settings/searchItem")
    try:
        info = first("/interfaces/overview/interfaces_info", "/interfaces/overview/interfacesInfo")
    except Exception:
        info = []
    addr = {}
    for i in info if isinstance(info, list) else []:
        a = i.get("addr4") or next(iter([x.get("ipaddr") for x in i.get("ipv4", []) if x.get("ipaddr")]), None)
        if a and "/" in a:
            addr[i.get("device")] = (a, i.get("description") or i.get("identifier"))
    n = 0
    for k, v in enumerate(vl):
        vid = int(v.get("tag"))
        a, descr = addr.get(v.get("vlanif"), (None, None))
        data = {"vid": vid, "name": v.get("descr") or descr or f"VLAN {vid}"}
        if a:
            data["subnet"] = str(ipaddress.ip_interface(a).network)
            data["gateway"] = a.split("/")[0]
        ex = db.one("SELECT * FROM vlans WHERE vid=?", (vid,))
        if ex:
            db.update("vlans", ex["id"], {k2: v2 for k2, v2 in data.items() if not ex.get(k2)})
        else:
            cnt = db.one("SELECT count(*) c FROM vlans")["c"]
            db.insert("vlans", {**data, "color": PALETTE[cnt % len(PALETTE)]})
        n += 1
    from . import ipam                                # DNS, DHCP und ARP für IPAM – Fehler dort brechen den VLAN-Abgleich nicht ab
    extra = ipam.fetch(integ, cli)
    fw = opnsense_firmware(integ, cli)
    head = f"{n} VLANs" if n else "verbunden, keine VLANs angelegt"
    return head + (" · " + extra if extra else "") + (" · " + fw if fw else "")


def opnsense_firmware_parse(r):
    """Antwort von /api/core/firmware/status → Update-Eintrag (None, wenn nichts Brauchbares drinsteht)."""
    prod = (r or {}).get("product") or {}
    inst, latest = prod.get("product_version"), prod.get("product_latest")
    if not inst and not latest:
        return None
    status = str((r or {}).get("status") or "")
    avail = status in ("update", "upgrade") or bool(inst and latest and _vkey(latest) > _vkey(inst))
    count = (r or {}).get("updates")
    try:
        count = int(count) if count not in (None, "") else None
    except (TypeError, ValueError):
        count = None
    return {"key": "opnsense:firmware", "title": "OPNsense", "installed": inst, "latest": latest or inst,
            "available": avail, "count": count}


def _vkey(v):
    """Versionsvergleich ohne Zusatzpaket: 24.7.10_1 < 24.7.11 < 25.1."""
    return [int(x) if x.isdigit() else x for x in re.split(r"[._\-]", str(v or "")) if x]


def opnsense_firmware(integ, cli):
    """Stand der Firmware aus dem letzten Check der OPNsense (sie prüft selbst, HomeAtlas löst keinen Check aus)."""
    from . import updates
    try:
        r = _get(cli.base + "/core/firmware/status", cli.hdr)
    except urllib.error.HTTPError as e:
        return "Firmware-Stand: Recht „System: Firmware“ fehlt" if e.code in (401, 403) else ""
    except Exception:  # noqa: BLE001
        return ""
    item = opnsense_firmware_parse(r)
    if not item:
        return ""
    host = endpoint(integ["config"], 443)[1]
    dev = db.one("SELECT * FROM devices WHERE id=?", (integ.get("device_id") or 0,)) or db.one("SELECT * FROM devices WHERE ip=?", (host,))
    if not dev:
        return ""
    updates.record(dev["id"], "opnsense", [item])
    return f"Firmware {item['installed']}" + (f" → {item['latest']} verfügbar" if item["available"] else " aktuell")


# ------------------------------------------------------------------ gemeinsame Übernahme für NAS und BMC
def apply_host(integ, info, host, kind, vendor, icon, dtype, os_name="", url="", hw_key="hw", status="online", extra_only=False):
    """Schreibt ausgelesene Daten an ein Gerät: vorhandenes Gerät (zugeordnet, gleiche IP oder MAC) übernehmen, sonst anlegen.
    extra_only: die gelesenen Adressen gehören zu einem Nebenanschluss (BMC) und werden nie zur Hauptadresse."""
    nics = [n for n in info["nics"] if n["ip"] or n["mac"]]
    main = next((n for n in nics if n["ip"] == host), None) or next((n for n in nics if n["ip"] and n["up"]), None) or \
        next((n for n in nics if n["ip"]), None) or {"ip": host if re.match(r"^[\d.]+$", host or "") else "", "mac": "", "up": True, "name": ""}
    dev = db.one("SELECT * FROM devices WHERE id=?", (integ.get("device_id") or 0,)) or \
        db.one("SELECT * FROM devices WHERE integration_id=? AND ext_id=?", (integ["id"], kind))
    for n in [main] + nics:
        if dev:
            break
        dev = (db.one("SELECT * FROM devices WHERE ip=?", (n["ip"],)) if n.get("ip") else None) or \
            (db.one("SELECT * FROM devices WHERE lower(mac)=?", (n["mac"],)) if n.get("mac") else None)
    if not dev:
        did = db.insert("devices", {"name": info["name"] or host, "type": dtype, "icon": icon, "ip": main["ip"], "mac": main["mac"],
                                    "vlan_id": vlan_for_ip(main["ip"]), "source": kind, "integration_id": integ["id"], "ext_id": kind})
        dev = db.one("SELECT * FROM devices WHERE id=?", (did,))
    meta = dict(dev["meta"] or {})
    # weitere Netzwerkkarten als zusätzliche Adressen; vorhandene Einträge (mit Notizen) bleiben, nur der Zustand wird gepflegt
    addrs = [dict(a) for a in meta.get("addrs") or []]
    own_ip = dev.get("ip") or main["ip"]
    for n in nics:
        if not n["ip"]:
            continue
        if n["ip"] == own_ip:
            if n["up"] is not None:
                meta["up0"] = n["up"]
            if not meta.get("primary_label"):
                meta["primary_label"] = n["name"]
            continue
        ex = next((a for a in addrs if a.get("ip") == n["ip"] or (n["mac"] and (a.get("mac") or "").lower() == n["mac"])), None)
        if ex:
            ex.update(ip=n["ip"], mac=n["mac"] or ex.get("mac"), **({"up": n["up"]} if n["up"] is not None else {}))
        else:
            addrs.append({"ip": n["ip"], "mac": n["mac"], "label": n["name"], "vlan_id": vlan_for_ip(n["ip"]),
                          **({"up": n["up"]} if n["up"] is not None else {})})
    if addrs:
        meta["addrs"] = addrs
    meta[hw_key] = info["hw"]
    if not extra_only:
        meta.update(ifaces=[{"idx": n["idx"], "name": n["name"], "alias": n["ip"], "up": n["up"] if n["up"] is not None else bool(n["ip"]), "speed": n.get("speed") or "1G"} for n in nics],
                    pools=info.get("pools") or [])
    if info.get("serial"):
        meta["serial"] = info["serial"]
    upd = {"meta": meta, "last_seen": db.now()}
    if status:
        upd["status"] = status
    if os_name:
        upd["os"] = os_name
    if not dev.get("integration_id") and not extra_only:   # ein Gerät, das schon einer anderen Anbindung gehört (Proxmox), bleibt dort
        upd.update(integration_id=integ["id"], ext_id=kind)
    for k, v in (("hostname", "" if extra_only else info["name"]), ("model", info["model"]), ("vendor", vendor), ("icon", icon), ("ip", main["ip"]),
                 ("mac", main["mac"] if (dev.get("ip") or main["ip"]) == main["ip"] else ""),
                 ("url", url), ("vlan_id", vlan_for_ip(main["ip"]))):
        if v and not dev.get(k):
            upd[k] = v
    if dev["type"] in ("other", "", None) or (dtype == "nas" and dev["type"] == "server"):
        upd["type"] = dtype
    db.update("devices", dev["id"], upd)
    db.update("integrations", integ["id"], {"device_id": dev["id"]})
    return dev, nics


# ------------------------------------------------------------------ QNAP
# QTS hat keine API-Schlüssel: Anmeldung mit Benutzer und Passwort liefert eine Sitzungs-ID, die nach dem Abruf wieder
# abgemeldet wird. Die Antworten sind XML.


def _size(b):
    b = float(b or 0)
    for unit, f in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6)):
        if b >= f:
            return f"{b / f:.1f}".rstrip("0").rstrip(".") + " " + unit
    return "0 GB"


def qnap_parse(sysinfo, disks=None, volumes=None):
    """XML-Antworten → Gerätedaten. Getrennt vom Abruf, damit es testbar bleibt."""
    t = lambda node, path: ((node.findtext(path) or "").strip() if node is not None else "")
    root = sysinfo.find("func/ownContent/root")
    if root is None:
        raise RuntimeError("QNAP: Systeminformationen fehlen in der Antwort – gehört der Benutzer zur Administratorgruppe?")
    out = {"name": t(root, "server_name"), "model": t(sysinfo, "model/displayModelName") or t(sysinfo, "model/modelName"),
           "serial": t(root, "serial_number"), "fw": " ".join(x for x in (t(sysinfo, "firmware/version"), t(sysinfo, "firmware/build")) if x),
           "platform": t(sysinfo, "firmware/name") or "QTS", "nics": [], "hw": [], "pools": []}
    try:
        cnt = int(t(root, "nic_cnt") or 0)
    except ValueError:
        cnt = 0
    for i in range(1, cnt + 1):
        ip, mac = t(root, f"eth_ip{i}"), t(root, f"eth_mac{i}").lower()
        if not mac and not ip:
            continue
        out["nics"].append({"idx": i, "name": t(root, f"ifname{i}") or t(root, f"dname{i}") or f"LAN {i}",
                            "ip": ip if ip and ip != "0.0.0.0" else "", "mac": mac, "up": t(root, f"eth_status{i}") == "1",
                            "speed": speed_label(t(root, f"eth_max_speed{i}"))})
    if t(root, "cpu_model"):
        out["hw"].append({"icon": "glyph-cpu", "label": "CPU", "value": re.sub(r"\(R\)|\(TM\)|CPU ", "", t(root, "cpu_model")).strip(),
                          "sub": (t(root, "cpu_tempc") + " °C") if t(root, "cpu_tempc") else ""})
    try:
        mem, free = float(t(root, "total_memory")), float(t(root, "free_memory") or 0)
        out["hw"].append({"icon": "glyph-ram", "label": "MEMORY", "value": f"{round(mem / 1000)} GB", "sub": f"{round((mem - free) / 1024, 1)} GB belegt"})
    except ValueError:
        pass
    bad = 0
    for d in disks.findall("Disk_Info/entry") if disks is not None else []:
        if not t(d, "Model"):
            continue
        health = t(d, "Health")
        ok = health.upper() in ("OK", "GOOD", "")
        bad += 0 if ok else 1
        ssd = t(d, "hd_is_ssd") == "1"
        temp = t(d, "Temperature/oC")
        out["hw"].append({"icon": "glyph-ssd" if ssd else "glyph-hdd", "label": f"SCHACHT {t(d, 'HDNo')}", "value": f"{t(d, 'Model')} {t(d, 'Capacity')}".strip(),
                          "sub": " · ".join(x for x in ("SMART " + (health or "?"), temp + " °C" if temp else "", t(d, "Serial")) if x)})
    out["bad_disks"] = bad
    if volumes is not None:
        labels = {t(v, "volumeValue"): t(v, "volumeLabel") or "Volume " + t(v, "volumeValue") for v in volumes.findall("volumeList/volume")}
        for u in volumes.findall("volumeUseList/volumeUse"):
            try:
                total, free = float(t(u, "total_size")), float(t(u, "free_size") or 0)
            except ValueError:
                continue
            if total <= 0:
                continue
            shares = [t(f, "sharename") for f in u.findall("folder_element") if t(f, "sharename")]
            out["pools"].append({"name": labels.get(t(u, "volumeValue"), "Volume " + t(u, "volumeValue")),
                                 "layout": ", ".join(shares[:8]) + (" …" if len(shares) > 8 else ""),
                                 "pct": round((total - free) / total * 100), "used": f"{_size(total - free)} von {_size(total)} belegt"})
    return out


def sync_qnap(integ):
    c = integ["config"]
    raw = (c.get("host") or "").strip()
    scheme, host, port = endpoint(c, 443)
    if "://" not in raw and str(port) in ("8080", "80"):        # 8080 ist bei QNAP der unverschlüsselte Standardport
        scheme = "http"
    if not c.get("user") or not c.get("password"):
        raise RuntimeError("Benutzer und Passwort fehlen")
    reach(host, port)
    base = f"{scheme}://{host}:{port}/cgi-bin/"

    def call(path, data=None):
        req = urllib.request.Request(base + path, data=urllib.parse.urlencode(data).encode() if data else None)
        try:
            with _OPENER.open(req, timeout=20) as r:
                body = r.read()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(explain(e, "QNAP")) from None
        try:
            return ET.fromstring(body)
        except ET.ParseError:
            raise RuntimeError("QNAP: unerwartete Antwort – ist das die Weboberfläche des NAS (Port prüfen)?") from None

    login = call("authLogin.cgi", {"user": c["user"].strip(), "pwd": base64.b64encode(c["password"].encode()).decode()})
    sid = (login.findtext("authSid") or "").strip()
    if (login.findtext("authPassed") or "").strip() != "1" or not sid:
        if (login.findtext("need_2sv") or "").strip() == "1":
            raise RuntimeError("QNAP: Für diesen Benutzer ist die zweistufige Anmeldung aktiv – dafür einen eigenen Benutzer ohne 2FA anlegen")
        raise RuntimeError("QNAP: Anmeldung abgelehnt – Benutzer/Passwort prüfen (nach mehreren Fehlversuchen sperrt das NAS die Adresse)")
    try:
        q = urllib.parse.quote(sid)
        sysinfo = call(f"management/manaRequest.cgi?subfunc=sysinfo&hd=no&multicpu=1&sid={q}")
        if (sysinfo.findtext("authPassed") or "").strip() == "0":
            raise RuntimeError("QNAP: angemeldet, aber ohne Zugriff auf die Systeminformationen – der Benutzer muss zur Administratorgruppe gehören")
        extra = []
        for path in (f"disk/qsmart.cgi?func=all_hd_data&sid={q}", f"management/chartReq.cgi?chart_func=disk_usage&disk_select=all&include=all&sid={q}"):
            try:
                extra.append(call(path))
            except RuntimeError:
                extra.append(None)                   # ältere Firmware kennt nicht jeden Abruf
        info = qnap_parse(sysinfo, *extra)
    finally:
        try:
            call(f"authLogout.cgi?logout=1&sid={urllib.parse.quote(sid)}")
        except RuntimeError:
            pass

    dev, nics = apply_host(integ, info, host, kind="qnap", vendor="QNAP", icon="qnap", dtype="nas",
                           os_name=f"{info['platform']} {info['fw']}".strip(), url=f"{scheme}://{host}:{port}")
    disks = sum(1 for h in info["hw"] if h["label"].startswith("SCHACHT"))
    warn = f" · ⚠ {info['bad_disks']} Platte(n) mit SMART-Warnung" if info["bad_disks"] else ""
    return f"{info['name'] or host} · {info['model']} · {len(nics)} Netzwerkkarten, {disks} Platten, {len(info['pools'])} Volumes{warn}"


# ------------------------------------------------------------------ Synology
SYNO_ERR = {400: "Benutzer oder Passwort falsch", 401: "das Konto ist deaktiviert", 402: "dem Benutzer fehlt die Berechtigung für DSM",
            403: "für diesen Benutzer ist die 2-Faktor-Authentifizierung aktiv – dafür einen eigenen Benutzer ohne 2FA anlegen",
            404: "für diesen Benutzer ist die 2-Faktor-Authentifizierung aktiv – dafür einen eigenen Benutzer ohne 2FA anlegen",
            406: "DSM erzwingt 2-Faktor-Authentifizierung für dieses Konto – in DSM für den HomeAtlas-Benutzer ausnehmen",
            407: "DSM hat die Adresse von HomeAtlas nach Fehlversuchen gesperrt (Systemsteuerung → Sicherheit → Konto)",
            408: "das Passwort ist abgelaufen", 409: "das Passwort ist abgelaufen", 410: "das Passwort muss erst geändert werden"}
RAID = {"raid_1": "RAID 1", "raid_5": "RAID 5", "raid_6": "RAID 6", "raid_10": "RAID 10", "raid_0": "RAID 0", "basic": "Basic",
        "shr_without_disk_protect": "SHR (ohne Schutz)", "shr_with_1_disk_protect": "SHR", "shr_with_2_disk_protect": "SHR-2", "jbod": "JBOD"}


def synology_parse(dsm, net, storage=None, system=None):
    """JSON-Antworten → Gerätedaten. Getrennt vom Abruf, damit es testbar bleibt."""
    system, storage = system or {}, storage or {}
    out = {"name": net.get("hostname") or "", "model": dsm.get("model") or system.get("model") or "", "serial": dsm.get("serial") or "",
           "fw": dsm.get("version_string") or system.get("firmware_ver") or "", "nics": [], "hw": [], "pools": [], "bad_disks": 0}
    for n, i in enumerate(net.get("interfaces") or [], 1):
        ips = i.get("ip") or []
        ip = (ips[0].get("address") if ips and isinstance(ips[0], dict) else ips[0] if ips and isinstance(ips, list) else ips if isinstance(ips, str) else "") or ""
        if i.get("type") in ("lo", "tunnel", "ovs") or (i.get("id") or "").startswith(("lo", "docker", "sit", "tun")):
            continue
        iid = i.get("id") or ""
        m = re.match(r"^(?:ovs_)?(eth|bond)(\d+)$", iid)
        name = f"{'LAN' if m.group(1) == 'eth' else 'Bond'} {int(m.group(2)) + 1}" if m else (iid or f"LAN {n}")
        out["nics"].append({"idx": n, "name": name, "ip": ip if ip and not ip.startswith("169.254.") else "",
                            "mac": (i.get("mac") or "").lower().replace("-", ":"), "up": None, "speed": "1G"})
    cpu = " ".join(x for x in (system.get("cpu_vendor"), system.get("cpu_family"), system.get("cpu_series")) if x)
    if cpu:
        out["hw"].append({"icon": "glyph-cpu", "label": "CPU", "value": cpu, "sub": f"{system.get('cpu_cores')} Kerne" if system.get("cpu_cores") else ""})
    ram = dsm.get("ram") or system.get("ram_size")
    if ram:
        out["hw"].append({"icon": "glyph-ram", "label": "MEMORY", "value": f"{round(int(ram) / 1024) or 1} GB" if int(ram) >= 1024 else f"{ram} MB",
                          "sub": f"System {dsm.get('temperature')} °C" if dsm.get("temperature") else ""})
    for d in storage.get("disks") or []:
        state, smart = d.get("status") or "", d.get("smart_status") or ""
        ok = state in ("normal", "") and smart in ("normal", "safe", "")
        out["bad_disks"] += 0 if ok else 1
        ssd = d.get("isSsd") or d.get("diskType") in ("SSD", "M.2 NVMe", "NVMe")
        try:
            size = _size(d.get("size_total"))
        except (TypeError, ValueError):
            size = ""
        out["hw"].append({"icon": "glyph-ssd" if ssd else "glyph-hdd", "label": (d.get("name") or d.get("id") or "Platte").upper().replace("DRIVE", "SCHACHT").replace("LAUFWERK", "SCHACHT"),
                          "value": f"{(d.get('vendor') or '').strip()} {(d.get('model') or '').strip()} {size}".strip(),
                          "sub": " · ".join(x for x in ("Zustand " + (state if ok else f"{state}/{smart}") if state else "", f"{d['temp']} °C" if d.get("temp") else "", d.get("serial") or "") if x)})
    for v in storage.get("volumes") or []:
        try:
            total, used = float(v["size"]["total"]), float(v["size"]["used"])
        except (KeyError, TypeError, ValueError):
            continue
        if total <= 0:
            continue
        num = re.sub(r"\D", "", v.get("id") or "")
        layout = " · ".join(x for x in (RAID.get(v.get("device_type"), v.get("device_type") or ""), v.get("fs_type") or "",
                                        "" if v.get("status") in ("normal", None) else "⚠ " + v["status"]) if x)
        out["pools"].append({"name": v.get("display_name") or (f"Volume {num}" if num else v.get("id") or "Volume"), "layout": layout,
                             "pct": round(used / total * 100), "used": f"{_size(used)} von {_size(total)} belegt"})
        out["bad_disks"] += 0 if v.get("status") in ("normal", None) else 1
    return out


def synology_update_parse(r, fw):
    """SYNO.Core.Upgrade.Server/check → Update-Eintrag. Die Felder sind nicht offiziell dokumentiert und je nach DSM
    verschieden verschachtelt (available/version, update.available/update.version); fehlt beides, gibt es keinen Eintrag."""
    if not isinstance(r, dict):
        return None
    u = r.get("update") if isinstance(r.get("update"), dict) else r
    avail = u.get("available")
    if avail is None:
        return None
    vd = u.get("version_details") if isinstance(u.get("version_details"), dict) else {}
    ver = u.get("version") or vd.get("os_version")
    fw = re.sub(r"^DSM\s*", "", fw or "")
    return {"key": "synology:dsm", "title": "DSM", "installed": fw, "latest": ver or fw, "available": bool(avail),
            "url": u.get("release_note") or None}


def sync_synology(integ):
    c = integ["config"]
    raw = (c.get("host") or "").strip()
    scheme, host, port = endpoint(c, 5001)
    if "://" not in raw and str(port) in ("5000", "80"):        # 5000 ist bei Synology der unverschlüsselte Standardport
        scheme = "http"
    if not c.get("user") or not c.get("password"):
        raise RuntimeError("Benutzer und Passwort fehlen")
    reach(host, port)
    base = f"{scheme}://{host}:{port}/webapi/"
    apis, sid = {}, ""

    def call(api, method, post=False, **params):
        a = apis.get(api) or {"path": "query.cgi" if api == "SYNO.API.Info" else "entry.cgi", "maxVersion": 1}
        q = {"api": api, "version": min(int(a.get("maxVersion") or 1), params.pop("maxv", 99)), "method": method, **params}
        if sid:
            q["_sid"] = sid
        enc = urllib.parse.urlencode(q)
        req = urllib.request.Request(base + a["path"] + ("" if post else "?" + enc), data=enc.encode() if post else None)
        try:
            with _OPENER.open(req, timeout=25) as r:
                return json.loads(r.read().decode())
        except json.JSONDecodeError:
            raise RuntimeError("Synology: unerwartete Antwort – ist das die DSM-Oberfläche (Port prüfen)?") from None
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(explain(e, "Synology")) from None

    def data(api, method, **params):
        r = call(api, method, **params)
        if not r.get("success"):
            raise RuntimeError(f"Synology: {api} abgelehnt (Fehler {(r.get('error') or {}).get('code')})")
        return r.get("data") or {}

    apis.update(data("SYNO.API.Info", "query", query="SYNO.API.Auth,SYNO.DSM.Info,SYNO.DSM.Network,SYNO.Storage.CGI.Storage,SYNO.Core.System"))
    if "SYNO.API.Auth" not in apis:
        raise RuntimeError("Synology: Anmelde-Schnittstelle nicht gefunden – ist das ein Synology-NAS?")
    login = call("SYNO.API.Auth", "login", post=True, maxv=6, account=c["user"].strip(), passwd=c["password"], session="HomeAtlas", format="sid")
    if not login.get("success"):
        code = (login.get("error") or {}).get("code")
        raise RuntimeError("Synology: Anmeldung abgelehnt – " + SYNO_ERR.get(code, f"Fehler {code}"))
    sid = login["data"]["sid"]
    try:
        try:
            dsm, net = data("SYNO.DSM.Info", "getinfo"), data("SYNO.DSM.Network", "list")
        except RuntimeError as e:
            if "Fehler 105" in str(e) or "Fehler 119" in str(e):
                raise RuntimeError("Synology: angemeldet, aber ohne Zugriff auf die Systeminformationen – der Benutzer muss zur Administratorgruppe gehören") from None
            raise
        extra = []
        for api, method, kw in (("SYNO.Storage.CGI.Storage", "load_info", {}), ("SYNO.Core.System", "info", {})):
            try:
                extra.append(data(api, method, **kw))
            except RuntimeError:
                extra.append(None)
        info = synology_parse(dsm, net, *extra)
        try:                                          # DSM-Update: Stand der eigenen Prüfung des NAS
            upg = data("SYNO.Core.Upgrade.Server", "check")
        except RuntimeError:
            upg = None
    finally:
        try:
            call("SYNO.API.Auth", "logout", maxv=6, session="HomeAtlas")
        except RuntimeError:
            pass
    dev, nics = apply_host(integ, info, host, kind="synology", vendor="Synology", icon="synology", dtype="nas",
                           os_name=info["fw"] if info["fw"].startswith("DSM") else f"DSM {info['fw']}".strip(), url=f"{scheme}://{host}:{port}")
    disks = sum(1 for h in info["hw"] if h["icon"] in ("glyph-hdd", "glyph-ssd"))
    warn = f" · ⚠ {info['bad_disks']} Warnung(en) bei Platten/Volumes" if info["bad_disks"] else ""
    miss = "" if extra[0] is not None else " · Speicher nicht lesbar (Administratorrechte nötig)"
    item = synology_update_parse(upg, info["fw"])
    if item:
        from . import updates
        updates.record(dev["id"], "synology", [item])
        miss += f" · DSM-Update {item['latest']} verfügbar" if item["available"] else ""
    return f"{info['name'] or host} · {info['model']} · {len(nics)} Netzwerkkarten, {disks} Platten, {len(info['pools'])} Volumes{warn}{miss}"


# ------------------------------------------------------------------ IPMI / Redfish
def redfish_parse(system, manager=None, nic=None, thermal=None, power=None):
    system, manager, nic, thermal, power = (x or {} for x in (system, manager, nic, thermal, power))
    health = (system.get("Status") or {}).get("HealthRollup") or (system.get("Status") or {}).get("Health") or ""
    ip = next((a.get("Address") for a in nic.get("IPv4Addresses") or [] if a.get("Address") and a["Address"] != "0.0.0.0"), "")
    board = " ".join(x for x in ((system.get("Manufacturer") or "").strip(), (system.get("Model") or "").strip()) if x)
    out = {"name": system.get("HostName") or "", "model": board, "serial": (system.get("SerialNumber") or "").strip(), "health": health,
           "power": system.get("PowerState") or "", "hw": [], "warn": [],
           "nics": [{"idx": 1, "name": "IPMI", "ip": ip, "mac": (nic.get("MACAddress") or "").lower().replace("-", ":"), "up": True}] if (ip or nic.get("MACAddress")) else []}
    out["hw"].append({"icon": "glyph-board", "label": "MAINBOARD", "value": board or "unbekannt",
                      "sub": " · ".join(x for x in ("BIOS " + system["BiosVersion"] if system.get("BiosVersion") else "",
                                                    "BMC " + manager["FirmwareVersion"] if manager.get("FirmwareVersion") else "",
                                                    "SN " + out["serial"] if out["serial"] else "") if x)})
    watts = next((p.get("PowerConsumedWatts") for p in power.get("PowerControl") or [] if p.get("PowerConsumedWatts")), None)
    temps = [(t.get("Name") or "", t.get("ReadingCelsius")) for t in thermal.get("Temperatures") or [] if isinstance(t.get("ReadingCelsius"), (int, float))]
    cpu_t = [v for n, v in temps if "cpu" in n.lower()]
    fans = [f for f in thermal.get("Fans") or [] if isinstance(f.get("Reading"), (int, float)) and f["Reading"] > 0]
    psus = [p for p in power.get("PowerSupplies") or [] if (p.get("Status") or {}).get("State") != "Absent"]
    for group, items in (("Temperatur", thermal.get("Temperatures") or []), ("Lüfter", thermal.get("Fans") or []), ("Netzteil", psus)):
        for x in items:
            st = x.get("Status") or {}
            if st.get("State") == "Enabled" and st.get("Health") not in ("OK", None, ""):
                out["warn"].append(f"{group} {x.get('Name') or ''}: {st['Health']}".strip())
    sensors = " · ".join(x for x in (f"CPU {max(cpu_t):.0f} °C" if cpu_t else f"max. {max(v for _, v in temps):.0f} °C" if temps else "",
                                     f"{len(fans)} Lüfter" if fans else "", f"{watts:.0f} W" if watts else "") if x)
    out["hw"].append({"icon": "glyph-shield", "label": "ZUSTAND", "value": {"OK": "In Ordnung", "Warning": "Warnung", "Critical": "Kritisch"}.get(health, health or "unbekannt")
                      + ({"On": "", "Off": " · ausgeschaltet"}.get(out["power"], "")), "sub": sensors})
    for n, p in enumerate(psus, 1):
        out["hw"].append({"icon": "glyph-psu", "label": f"NETZTEIL {n}", "value": (p.get("Model") or p.get("Name") or "Netzteil").strip(),
                          "sub": " · ".join(x for x in (f"{p['PowerCapacityWatts']:.0f} W" if isinstance(p.get("PowerCapacityWatts"), (int, float)) else "",
                                                        (p.get("Status") or {}).get("Health") or "") if x)})
    return out


def sync_ipmi(integ):
    c = integ["config"]
    scheme, host, port = endpoint(c, 443)
    if not c.get("user") or not c.get("password"):
        raise RuntimeError("Benutzer und Passwort fehlen")
    reach(host, port)
    base = f"{scheme}://{host}:{port}"
    hdr = {"Authorization": "Basic " + base64.b64encode(f"{c['user'].strip()}:{c['password']}".encode()).decode(), "Accept": "application/json"}

    def get(path):
        return _get(base + path, hdr, timeout=25)

    def first(coll):                                  # Sammlung → erster Eintrag
        if not coll:
            return None
        m = (get(coll["@odata.id"]).get("Members") or [])
        return get(m[0]["@odata.id"]) if m else None

    def soft(fn):
        try:
            return fn()
        except Exception:  # noqa: BLE001 – Sensoren und Netzteile sind Zugabe
            return None

    try:
        root = get("/redfish/v1/")
        system = first(root.get("Systems"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("IPMI: Anmeldung abgelehnt – Benutzer/Passwort prüfen (Groß-/Kleinschreibung zählt, Supermicro-Standard ist ADMIN)") from None
        if e.code == 404:
            raise RuntimeError("IPMI: Dieser BMC bietet kein Redfish an – die BMC-Firmware ist dafür zu alt, bitte aktualisieren") from None
        raise RuntimeError(explain(e, "IPMI")) from None
    except json.JSONDecodeError:
        raise RuntimeError("IPMI: unerwartete Antwort – ist das die Adresse des BMC?") from None
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(explain(e, "IPMI")) from None
    if not system:
        raise RuntimeError("IPMI: Der BMC meldet kein System")
    manager = soft(lambda: first(root.get("Managers")))
    nic = soft(lambda: first(manager.get("EthernetInterfaces"))) if manager else None
    chassis = soft(lambda: first(root.get("Chassis")))
    thermal = soft(lambda: get(chassis["Thermal"]["@odata.id"])) if chassis and chassis.get("Thermal") else None
    power = soft(lambda: get(chassis["Power"]["@odata.id"])) if chassis and chassis.get("Power") else None
    info = redfish_parse(system, manager, nic, thermal, power)
    if not info["nics"] and re.match(r"^[\d.]+$", host or ""):
        info["nics"] = [{"idx": 1, "name": "IPMI", "ip": host, "mac": "", "up": True}]
    vendor = (system.get("Manufacturer") or "").strip()
    # der BMC antwortet auch bei ausgeschaltetem Server: Status nur setzen, wenn er eindeutig ist und das Gerät sonst keinen hat
    dev, _ = apply_host(integ, info, host, kind="ipmi", vendor=vendor, icon="supermicro" if "supermicro" in vendor.lower() else "",
                        dtype="server", hw_key="hw_bmc", status="offline" if info["power"] == "Off" else "", extra_only=True, url="")
    warn = " · ⚠ " + "; ".join(info["warn"][:3]) if info["warn"] else ""
    return f"{dev['name']} · {info['model'] or 'BMC'} · Zustand {info['health'] or '?'}, {info['power'] or '?'}{warn}"


# ------------------------------------------------------------------ Home Assistant
# Ein einziger Aufruf der Template-API liefert die Geräte-Registry als JSON (ohne WebSocket-Verbindung).
HA_TEMPLATE = (
    "{% set ns = namespace(out=[]) %}"
    "{% for did in states | map(attribute='entity_id') | map('device_id') | reject('none') | unique %}"
    "{% set ents = device_entities(did) %}{% set ce = device_attr(did,'primary_config_entry') %}"
    # Update-Entitäten des Geräts (Firmware von Zigbee-, ESPHome-, Shelly-Geräten, HA selbst, Add-ons …)
    "{% set up = namespace(l=[]) %}{% for e in ents if e.startswith('update.') %}"
    "{% set up.l = up.l + [{'e': e, 't': state_attr(e,'title') or state_attr(e,'friendly_name'),"
    " 'i': state_attr(e,'installed_version'), 'l': state_attr(e,'latest_version'), 'on': is_state(e,'on'),"
    " 'u': state_attr(e,'release_url')}] %}{% endfor %}"
    "{% set ns.out = ns.out + [{'id': did, 'name': device_attr(did,'name_by_user') or device_attr(did,'name'),"
    " 'mf': device_attr(did,'manufacturer'), 'model': device_attr(did,'model'), 'sw': device_attr(did,'sw_version'),"
    " 'area': area_name(did), 'via': device_attr(did,'via_device_id'),"
    " 'conns': device_attr(did,'connections') | list, 'idents': device_attr(did,'identifiers') | list,"
    " 'entry': device_attr(did,'entry_type'), 'integ': (config_entry_attr(ce,'domain') if ce else none),"
    " 'doms': ents | map('regex_replace','\\\\..*','') | unique | list, 'n': ents | count,"
    " 'un': ents | select('is_state','unavailable') | list | count, 'upd': up.l}] %}"
    "{% endfor %}"
    # Netzwerk-Tracker (UniFi, FRITZ!Box …) kennen MAC und IP zusammen – damit lassen sich Geräte zuordnen,
    # die der Scan in fremden VLANs nur mit IP sieht
    "{% set tr = namespace(out=[]) %}{% for s in states.device_tracker %}"
    "{% if s.attributes.get('mac') and s.attributes.get('ip') %}"
    "{% set tr.out = tr.out + [{'mac': s.attributes.get('mac'), 'ip': s.attributes.get('ip'),"
    " 'host': s.attributes.get('host_name'), 'essid': s.attributes.get('essid')}] %}"
    "{% endif %}{% endfor %}"
    "{{ {'devs': ns.out, 'net': tr.out} | tojson }}")
HA_TYPES = [("vacuum", "vacuum"), ("camera", "camera"), ("light", "light"), ("climate", "thermostat"), ("cover", "blind"),
            ("lock", "lock"), ("media_player", "speaker"), ("switch", "plug"), ("binary_sensor", "sensor"), ("sensor", "sensor")]
HA_ICONS = {"hue": "philips-hue", "tplink": "tp-link", "smartthings": "smartthings", "roborock": "roborock", "tuya": "tuya",
            "alexa_media": "amazon-alexa", "matter": "matter", "zha": "zigbee", "mqtt": "mqtt", "esphome": "esphome",
            "shelly": "shelly", "ring": "ring", "bambu_lab": "bambu-lab", "samsungtv": "samsung", "unifi": "unifi"}

# Funkweg eines Geräts, das über eine Bridge angebunden ist (via_device), nach Integration
HA_PROTO = {"hue": "zigbee", "zha": "zigbee", "deconz": "zigbee", "tradfri": "zigbee", "zwave_js": "zwave", "matter": "matter",
            "thread": "thread", "homematicip_cloud": "homematic", "homematic": "homematic", "fritzbox": "dect", "bluetooth": "ble",
            "bthome": "ble", "switchbot": "ble", "xiaomi_ble": "ble", "govee_ble": "ble", "enocean": "enocean", "knx": "knx",
            "rfxtrx": "rf", "mqtt": "mqtt", "lutron_caseta": "rf", "velux": "rf", "somfy_mylink": "rf", "broadlink": "ir"}


def ha_type(d):
    doms = set(d.get("doms") or [])
    if "media_player" in doms and "tv" in ((d.get("model") or "") + " " + (d.get("name") or "")).lower():
        return "tv"
    return next((t for dom, t in HA_TYPES if dom in doms), None)


def ha_plan(devs, chosen):
    """Trennt, was übernommen wird: gewählte Integrationen, keine Dienste; reine Tracker reichern nur an."""
    out = []
    for d in devs:
        if d.get("entry") == "service" or d["integ"] not in chosen:
            continue
        d["mac"] = next((v.upper().replace("-", ":") for t, v in (d.get("conns") or []) if t == "mac"), None)
        d["tracker"] = set(d.get("doms") or []) <= {"device_tracker"}
        out.append(d)
    return out


def sync_homeassistant(integ):
    from . import scanner
    c = integ["config"]
    scheme, host, port = endpoint(c, 8123, "http")
    if not c.get("token"):
        raise RuntimeError("Zugriffstoken fehlt (Home Assistant: Profil → Sicherheit → Langlebige Zugriffstoken)")
    reach(host, port)
    req = urllib.request.Request(f"{scheme}://{host}:{port}/api/template", method="POST",
                                 data=json.dumps({"template": HA_TEMPLATE}).encode(),
                                 headers={"Authorization": "Bearer " + c["token"].strip(), "Content-Type": "application/json"})
    with _OPENER.open(req, timeout=90) as r:
        data = json.loads(r.read().decode())
    devs, net = (data, []) if isinstance(data, list) else (data.get("devs", []), data.get("net", []))
    mac2ip = {str(n["mac"]).upper().replace("-", ":"): n["ip"] for n in net if n.get("mac") and n.get("ip")}
    for d in devs:
        d["integ"] = d.get("integ") or (d["idents"][0][0] if d.get("idents") else "unbekannt")
    real = [d for d in devs if d.get("entry") != "service"]
    avail = {}
    for d in real:
        avail[d["integ"]] = avail.get(d["integ"], 0) + 1
    c["_available"] = dict(sorted(avail.items()))
    db.update("integrations", integ["id"], {"config": c})
    chosen = set(c.get("integrations") or [])
    if not chosen:
        ha_updates(integ, devs, {})                  # HA selbst und Add-ons auch ohne übernommene Integrationen
        return (f"{len(real)} Geräte in {len(avail)} Integrationen gefunden – unter „Bearbeiten“ auswählen, "
                f"welche Integrationen übernommen werden")
    plan = ha_plan(devs, chosen)
    by_ip, by_mac = scanner._index()
    ids, seen, new, upd, linked = {}, set(), 0, 0, 0
    for d in plan:
        ext = "ha/" + d["id"]
        name = (d.get("name") or d.get("model") or "Gerät").strip()
        own = db.one("SELECT * FROM devices WHERE integration_id=? AND ext_id=?", (integ["id"], ext))
        ip = mac2ip.get(d["mac"]) if d["mac"] else None        # IP aus den Netzwerk-Trackern
        cands = [by_mac.get(d["mac"]) if d["mac"] else None, by_ip.get(ip) if ip else None]
        hit = next((h for h in cands if h and not (own and h[0] == own["id"])), None)
        if hit and own:                           # früher neu angelegt, jetzt per IP wiedergefunden: Doppelten auflösen
            db.x("UPDATE devices SET parent_id=NULL WHERE parent_id=?", (own["id"],))
            db.delete_device(own["id"])
            own = None
        up = d["n"] == 0 or d["un"] < d["n"]
        ha_meta = {"ha": {"integration": d["integ"], "sw": d.get("sw"), "id": d["id"]}}
        proto = HA_PROTO.get(d["integ"]) if d.get("via") else None
        if hit:                                   # vorhandenes (gescanntes) Gerät: nur anreichern
            dev = db.one("SELECT * FROM devices WHERE id=?", (hit[0],))
            auto = dev["name"] in (dev.get("ip"), (dev.get("hostname") or "").split(".")[0], dev.get("mac"))
            patch = {"meta": {**(dev["meta"] or {}), **ha_meta}}
            if d["mac"] and not dev.get("mac") and hit[1] is None:
                patch["mac"] = d["mac"]           # der nächste Scan erkennt das Gerät dann auch über die MAC
            if auto and name:
                patch["name"] = name
            if not dev.get("room") and d.get("area"):
                patch["room"] = d["area"]
            if not dev.get("vendor") and d.get("mf"):
                patch["vendor"] = d["mf"]
            if not dev.get("model") and d.get("model"):
                patch["model"] = d["model"]
            if dev["type"] in ("other", "iot", "client") and ha_type(d):
                patch["type"] = ha_type(d)
            db.update("devices", dev["id"], patch)
            ids[d["id"]] = dev["id"]
            linked += 1
            continue
        if d["tracker"]:                          # reine Anwesenheits-Tracker werden nie als Gerät angelegt
            continue
        seen.add(ext)
        if own:
            patch = {"name": name, "status": "online" if up else "offline", "vendor": d.get("mf"), "model": d.get("model"),
                     "meta": {**(own["meta"] or {}), **ha_meta, **({"proto": proto} if proto and "proto" not in (own["meta"] or {}) else {})}}
            if up:
                patch["last_seen"] = db.now()
            if not own.get("room") and d.get("area"):
                patch["room"] = d["area"]
            if own["type"] == "other" and ha_type(d):
                patch["type"] = ha_type(d)
            if ip and not own.get("ip"):
                patch.update(ip=ip, vlan_id=own.get("vlan_id") or vlan_for_ip(ip))
            db.update("devices", own["id"], {k: v for k, v in patch.items() if v is not None})
            ids[d["id"]] = own["id"]
            upd += 1
        else:
            ids[d["id"]] = db.insert("devices", {
                "name": name, "type": ha_type(d) or "iot", "vendor": d.get("mf"), "model": d.get("model"), "mac": d["mac"],
                "ip": ip, "vlan_id": vlan_for_ip(ip) if ip else None,
                "room": d.get("area"), "status": "online" if up else "offline", "last_seen": db.now() if up else None,
                "source": "homeassistant", "integration_id": integ["id"], "ext_id": ext, "meta": {**ha_meta, **({"proto": proto} if proto else {})}})
            new += 1
    # Platzierung (nur einmal, danach bleibt die Zuordnung Sache des Nutzers): an die Bridge, sonst in einen Bereich je Integration
    groups, bridges = {}, {x.get("via") for x in plan if x.get("via")}
    loose = {}                                   # Geräte ohne Bridge je Integration: erst ab drei lohnt ein Bereich
    for d in plan:
        if not d.get("via") and d["id"] not in bridges and not d["tracker"]:
            loose[d["integ"]] = loose.get(d["integ"], 0) + 1
    for d in plan:
        me = db.one("SELECT * FROM devices WHERE id=?", (ids.get(d["id"]) or 0,))
        if not me or me["source"] != "homeassistant" or (me["meta"] or {}).get("ha_placed"):
            continue
        parent = ids.get(d.get("via")) if d.get("via") else None
        if parent == me["id"]:
            parent = None
        is_bridge = d["id"] in bridges
        if not parent and not is_bridge and not me.get("parent_id") and loose.get(d["integ"], 0) >= 3:
            if d["integ"] not in groups:
                g = db.one("SELECT id FROM devices WHERE integration_id=? AND ext_id=?", (integ["id"], "ha-group/" + d["integ"]))
                groups[d["integ"]] = g["id"] if g else db.insert("devices", {
                    "name": "Home Assistant · " + d["integ"], "type": "group", "icon": HA_ICONS.get(d["integ"], "home-assistant"),
                    "source": "homeassistant", "integration_id": integ["id"], "ext_id": "ha-group/" + d["integ"]})
            parent = groups[d["integ"]]
        patch = {"meta": {**(me["meta"] or {}), "ha_placed": True}}
        if parent and not me.get("parent_id"):
            patch["parent_id"] = parent
        if is_bridge:
            patch["type"] = "iot" if me["type"] in ("sensor", "plug", "other") else None
            patch["icon"] = None if me.get("icon") else HA_ICONS.get(d["integ"])
        db.update("devices", me["id"], {k: v for k, v in patch.items() if v is not None})
    _prune(integ, "ha/", seen)
    nup = ha_updates(integ, devs, ids)
    return (f"{new} neu, {upd} aktualisiert, {linked} mit vorhandenen Geräten verknüpft ({', '.join(sorted(chosen))})" +
            (f" · {nup} Updates verfügbar" if nup else ""))


def ha_update_items(d):
    return [{"key": "ha:" + u["e"], "title": (u.get("t") or u["e"]).strip(), "installed": u.get("i"), "latest": u.get("l"),
             "available": bool(u.get("on")), "url": u.get("u")} for u in d.get("upd") or [] if u.get("e")]


def ha_updates(integ, devs, ids):
    """update.*-Entitäten an die Geräte schreiben. Dienste (HA Core, OS, Supervisor, Add-ons) landen am Home-Assistant-Gerät."""
    from . import updates
    n = 0
    for d in devs:
        if d.get("entry") == "service" or not ids.get(d["id"]) or not d.get("upd"):
            continue
        n += updates.record(ids[d["id"]], "homeassistant", ha_update_items(d))
    own = [it for d in devs if d.get("entry") == "service" for it in ha_update_items(d)]
    host = endpoint(integ["config"], 8123, "http")[1]
    dev = db.one("SELECT * FROM devices WHERE id=?", (integ.get("device_id") or 0,)) or db.one("SELECT * FROM devices WHERE ip=?", (host,))
    if dev and own:
        n += updates.record(dev["id"], "homeassistant", own)
    return n


# ------------------------------------------------------------------ UniFi Network
UNIFI_TYPES = {"uap": "ap", "usw": "switch", "ugw": "router", "uxg": "router", "udm": "router", "ucg": "router", "uck": "server",
               "usp": "plug", "ubb": "ap", "uph": "client"}


class UniFiClient:
    """UniFi Network: UniFi OS (UDM, UCG, Cloud Key Gen2+) mit API-Key oder Benutzer, selbst betriebene
    Network Application (Docker, Port 8443) nur mit Benutzer – sie kennt keine API-Keys. Gelesen wird über die /stat-Schnittstellen.
    Port leer = automatisch: 443, 8443, 11443 (UniFi OS Server). Port 8080 ist nur der Inform-Port der Geräte – dann wird 8443 versucht."""

    def __init__(self, c):
        raw = (c.get("host") or "").strip()
        self.explicit = "://" in raw or bool(str(c.get("port") or "").strip()) or ":" in raw
        self.scheme, self.host, self.port = endpoint({**c, "port": c.get("port") or 443}, 443)
        self.raw_http = raw.startswith("http://")
        self.site = (c.get("site") or "default").strip() or "default"
        self.key = (c.get("api_key") or "").strip()
        self.user, self.pw = (c.get("user") or "").strip(), c.get("password") or ""
        if not self.key and not (self.user and self.pw):
            raise RuntimeError("API-Key oder Benutzer und Passwort fehlen")
        self.csrf, self.prefix, self.os = None, "", True

    def _use(self, scheme, port):
        self.scheme, self.port = scheme, int(port)
        self.base = f"{scheme}://{self.host}:{port}"
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=_CTX),
                                              urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = None

    def _req(self, method, path, body=None):
        h = {"Accept": "application/json", "Origin": self.base, "Referer": self.base + "/"}
        if body is not None:
            h["Content-Type"] = "application/json"
        if self.key:
            h["X-API-KEY"] = self.key
        csrf = self.csrf or next((c.value for c in self.jar if c.name.lower() == "csrf_token"), None)
        if csrf:                                      # UniFi verlangt das Token als Kopfzeile, sobald es als Cookie gesetzt ist
            h["X-CSRF-Token"] = csrf
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                     method=method, headers=h)
        with self.op.open(req, timeout=20) as r:
            self.csrf = r.headers.get("X-CSRF-Token") or r.headers.get("X-Updated-CSRF-Token") or self.csrf
            txt = r.read().decode() or "{}"
        try:
            return json.loads(txt)
        except ValueError:
            raise RuntimeError("UniFi: unerwartete Antwort – ist das die Adresse der UniFi-Konsole bzw. der Network Application?") from None

    def _candidates(self):
        """Welche Kombinationen aus Schema und Port probiert werden, in dieser Reihenfolge."""
        out = []
        if self.explicit:
            out.append((self.scheme, self.port))
            if int(self.port) in (8080, 443):         # 8080 ist der Inform-Port, 443 der Standard von UniFi OS
                out.append(("https", 8443))
            if self.scheme == "https" and not self.raw_http:
                out.append(("http", self.port))       # z. B. hinter einem Proxy ohne TLS
        else:
            out += [("https", 443), ("https", 8443), ("https", 11443)]
        return list(dict.fromkeys(out))

    def _try_login(self):
        if self.key:
            for prefix, is_os in (("/proxy/network", True), ("", False)):    # UniFi OS, dann selbst betrieben
                try:
                    self._req("GET", f"{prefix}/api/s/{urllib.parse.quote(self.site)}/stat/sysinfo")
                    self.prefix, self.os = prefix, is_os
                    return
                except urllib.error.HTTPError as e:
                    if e.code in (401, 403):
                        raise RuntimeError("UniFi: API-Key abgelehnt – Schlüssel prüfen (Network → Einstellungen → "
                                           "Control Plane → Integrationen)") from None
                    if e.code != 404:
                        raise RuntimeError(explain(e, "UniFi")) from None
            raise RuntimeError(f"UniFi: Standort „{self.site}“ nicht gefunden – die Standort-ID steht in der Adresszeile "
                               "der Weboberfläche (…/manage/<ID>/…), meist „default“") from None
        # Erst UniFi OS (/api/auth/login), dann die selbst betriebene Network Application (/api/login). Letztere antwortet
        # auf /api/auth/login mit 401 „LoginRequired“ – das ist kein falsches Passwort, sondern der falsche Weg.
        # Jede Antwort wird mit Status und UniFi-Meldung festgehalten, damit die Fehlermeldung zeigt, was wirklich zurückkam.
        seen = []

        def why(e, where):
            body = ""
            try:
                body = e.read().decode(errors="ignore")
            except Exception:  # noqa: BLE001
                pass
            msg = ""
            try:
                j = json.loads(body)
                msg = (j.get("meta") or {}).get("msg") or j.get("message") or j.get("code") or ""
            except ValueError:
                msg = body.strip().splitlines()[0][:60] if body.strip() else ""
            seen.append(f"{where}: HTTP {e.code}{' ' + str(msg) if msg else ''}")
            return str(msg)

        payload = {"username": self.user, "password": self.pw}
        try:
            self._req("POST", "/api/auth/login", {**payload, "rememberMe": False})
            self.prefix, self.os = "/proxy/network", True
            return
        except urllib.error.HTTPError as e:
            why(e, "UniFi OS")
            if e.code not in (400, 401, 403, 404, 405):
                raise RuntimeError(explain(e, "UniFi")) from None
        # Frisch anfangen: Cookies oder CSRF-Token aus dem ersten Versuch lassen die Network Application sonst mit 403 ablehnen
        self._use(self.scheme, self.port)
        try:
            self._req("POST", "/api/login", {**payload, "remember": False})
            self.prefix, self.os = "", False
            return
        except urllib.error.HTTPError as e2:
            msg = why(e2, "Network Application")
            if e2.code not in (400, 401, 403) and not seen[0].startswith("UniFi OS: HTTP 401") and "403" not in seen[0]:
                raise RuntimeError(explain(e2, "UniFi") + " (" + "; ".join(seen) + ")") from None
            hint = {"api.err.Invalid": "Benutzername oder Passwort stimmt nicht – Groß-/Kleinschreibung beachten, beim Benutzer "
                                       "den Anmeldenamen nehmen, nicht die E-Mail",
                    "api.err.Ubic2faTokenRequired": "das Konto verlangt Zwei-Faktor – einen lokalen Benutzer ohne 2FA anlegen",
                    "api.err.LoginRequired": "Anmeldung nicht angenommen",
                    "api.err.TooManyRequests": "zu viele Fehlversuche, ein paar Minuten warten"}.get(msg, "Benutzer/Passwort prüfen; "
                                                                                                 "es muss ein lokales Konto ohne Zwei-Faktor sein")
            raise RuntimeError(f"UniFi: Anmeldung abgelehnt – {hint}. Antworten: " + "; ".join(seen)) from None

    def login(self):
        tried = []
        for scheme, port in self._candidates():
            self._use(scheme, port)
            try:
                reach(self.host, port, timeout=3)
                self._try_login()
                return
            except RuntimeError as e:
                if str(e).startswith("UniFi:") or "fehlen" in str(e):
                    raise                             # Gegenstelle erreicht, aber Anmeldung oder Standort falsch
                tried.append(f"{scheme}://…:{port} ({str(e).split(' – ')[0].split('. ')[0]})")
            except urllib.error.URLError as e:
                r = e.reason
                why = "spricht kein HTTPS" if isinstance(r, ssl.SSLError) else str(r)
                tried.append(f"{scheme}://…:{port} ({why})")
            except (ssl.SSLError, OSError) as e:
                tried.append(f"{scheme}://…:{port} ({'spricht kein HTTPS' if isinstance(e, ssl.SSLError) else e})")
        hint = (" Die selbst betriebene Network Application (Docker) hat ihre Weboberfläche auf 8443, Port 8080 ist nur für die Geräte."
                if any(":8080" in t for t in tried) or not self.explicit else "")
        raise RuntimeError("UniFi: keine Weboberfläche gefunden. Versucht: " + "; ".join(tried) + "." + hint)

    def get(self, what):
        try:
            r = self._req("GET", f"{self.prefix}/api/s/{urllib.parse.quote(self.site)}/{what}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise RuntimeError(f"UniFi: Standort „{self.site}“ nicht gefunden oder Schnittstelle {what} fehlt – "
                                   "Standort-ID steht in der Adresszeile der Weboberfläche (…/manage/<ID>/…)") from None
            raise RuntimeError(explain(e, "UniFi")) from None
        if isinstance(r, dict) and (r.get("meta") or {}).get("rc") not in (None, "ok"):
            raise RuntimeError("UniFi: " + str((r.get("meta") or {}).get("msg") or "Fehler"))
        return r.get("data", []) if isinstance(r, dict) else r

    def logout(self):
        if self.key:
            return
        try:
            self._req("POST", "/api/auth/logout" if self.os else "/api/logout", {})
        except Exception:  # noqa: BLE001 – Abmelden ist best effort
            pass


def _mac(m):
    return (m or "").strip().lower()


def unifi_port_name(dev, idx):
    for p in (dev or {}).get("port_table") or []:
        if p.get("port_idx") == idx:
            n = (p.get("name") or "").strip()
            return n if n and n.lower() != f"port {idx}" else f"Port {idx}"
    return f"Port {idx}" if idx else ""


def unifi_parse(devices, clients, wlans=None):
    """Antworten → Infrastruktur, Clients, Verbindungen. Getrennt vom Abruf, damit es testbar bleibt."""
    by_mac = {_mac(d.get("mac")): d for d in devices}
    infra = []
    for d in devices:
        t = (d.get("type") or "").lower()
        infra.append({"mac": _mac(d.get("mac")), "name": d.get("name") or d.get("hostname") or d.get("model") or d.get("mac"),
                      "ip": d.get("ip") or "", "type": UNIFI_TYPES.get(t, "other"), "kind": t,
                      "model": d.get("model_name") or d.get("model") or "", "fw": d.get("version") or "",
                      "online": d.get("state") == 1, "ports": len(d.get("port_table") or []),
                      "upgradable": bool(d.get("upgradable")), "upgrade_to": d.get("upgrade_to_firmware") or "",
                      "clients": d.get("num_sta") or (d.get("user-num_sta") or 0) + (d.get("guest-num_sta") or 0)})
    links = []
    for d in devices:
        up = d.get("uplink") or d.get("last_uplink") or {}
        um = _mac(up.get("uplink_mac"))
        if not um or um not in by_mac or um == _mac(d.get("mac")):
            continue
        wireless = (up.get("type") or "") == "wireless"
        links.append({"a": um, "b": _mac(d.get("mac")), "kind": "wlan" if wireless else "cable",
                      "a_port": "" if wireless else unifi_port_name(by_mac[um], up.get("uplink_remote_port")),
                      "b_port": "" if wireless else unifi_port_name(d, up.get("port_idx")),
                      "speed": speed_label(up.get("speed")) if not wireless else "", "ssid": up.get("essid") or ""})
    cl = []
    for c in clients:
        m = _mac(c.get("mac"))
        if not m or m in by_mac:
            continue
        wired = bool(c.get("is_wired"))
        via = _mac(c.get("sw_mac") if wired else c.get("ap_mac"))
        item = {"mac": m, "ip": c.get("ip") or c.get("fixed_ip") or "", "name": c.get("name") or c.get("hostname") or "",
                "hostname": c.get("hostname") or "", "vendor": c.get("oui") or "", "wired": wired, "via": via if via in by_mac else "",
                "port": unifi_port_name(by_mac.get(via), c.get("sw_port")) if wired and c.get("sw_port") else "",
                "ssid": c.get("essid") or "", "signal": c.get("signal") or c.get("rssi"), "network": c.get("network") or "",
                "vlan": c.get("vlan"), "speed": speed_label(c.get("wired_rate_mbps")) if wired and c.get("wired_rate_mbps") else ""}
        cl.append(item)
    ws = [{"ssid": w.get("name"), "security": (w.get("security") or "") + ("/" + w["wpa_mode"] if w.get("wpa_mode") else ""),
           "enabled": w.get("enabled", True)} for w in (wlans or []) if w.get("name")]
    return {"infra": infra, "links": links, "clients": cl, "wlans": ws}


def _unifi_link(integ, a_id, b_id, kind, a_port="", b_port="", speed="", wlan_id=None, managed=()):
    """Verbindung der Anbindung setzen. Ein Gerät hängt immer nur an einer Stelle: alte UniFi-Verbindungen dieses
    Geräts werden ersetzt. Von Hand dokumentierte Verbindungen haben Vorrang und werden nicht verdoppelt."""
    manual = db.one("SELECT id, a_id, a_port, b_port FROM links WHERE source<>'unifi' AND kind=? AND "
                    "((a_id=? AND b_id=?) OR (a_id=? AND b_id=?))", (kind, a_id, b_id, b_id, a_id))
    if manual:
        if kind == "cable" and (a_port or b_port):        # fehlende Portangaben ergänzen
            mine_a = manual["a_id"] == a_id
            pa, pb = (a_port, b_port) if mine_a else (b_port, a_port)
            upd = {k: v for k, v in (("a_port", pa), ("b_port", pb)) if v and not manual[k]}
            if upd:
                db.update("links", manual["id"], upd)
        db.x("DELETE FROM links WHERE source='unifi' AND b_id=? AND kind IN ('cable','wlan')", (b_id,))
        return 0
    if kind == "wlan" and managed and db.one(
            "SELECT id FROM links WHERE source<>'unifi' AND kind='wlan' AND ((a_id=? AND b_id IN (%s)) OR (b_id=? AND a_id IN (%s)))"
            % (",".join("?" * len(managed)), ",".join("?" * len(managed))), (b_id, *managed, b_id, *managed)):
        return 0                                         # von Hand einem anderen AP zugeordnet: nicht anfassen
    ex = db.one("SELECT id FROM links WHERE source='unifi' AND a_id=? AND b_id=? AND kind=?", (a_id, b_id, kind))
    db.x("DELETE FROM links WHERE source='unifi' AND b_id=? AND kind IN ('cable','wlan') AND id<>?", (b_id, ex["id"] if ex else 0))
    data = {"a_port": a_port, "b_port": b_port, "speed": speed or ("1G" if kind == "cable" else ""), "wlan_id": wlan_id}
    if ex:
        db.update("links", ex["id"], data)
        return 0
    db.insert("links", {"a_id": a_id, "b_id": b_id, "kind": kind, "source": "unifi", **data})
    return 1


def sync_unifi(integ):
    c = integ["config"]
    cli = UniFiClient(c)
    cli.login()
    try:
        devices = cli.get("stat/device")
        clients = cli.get("stat/sta")
        try:
            wlans = cli.get("rest/wlanconf")
        except RuntimeError:
            wlans = []                                   # Leserecht auf WLAN-Einstellungen ist nicht nötig
    finally:
        cli.logout()
    from . import updates
    data = unifi_parse(devices, clients, wlans)
    url = f"{cli.scheme}://{cli.host}:{cli.port}"
    found = ""
    if cli.scheme == "https" and str(c.get("port") or "") != str(cli.port):   # gefundenen Port merken
        db.update("integrations", integ["id"], {"config": {**c, "port": str(cli.port)}})
        found = f" · Port {cli.port} gefunden und gespeichert"
    now = db.now()
    ids, seen = {}, set()
    for d in data["infra"]:
        ext = "unifi/" + d["mac"]
        seen.add(ext)
        ids[d["mac"]] = _upsert(integ, ext, {
            "name": d["name"], "type": d["type"], "model": d["model"], "os": f"UniFi {d['fw']}".strip(), "ip": d["ip"] or None,
            "mac": d["mac"], "vendor": "Ubiquiti", "icon": "unifi", "url": url,
            "status": "online" if d["online"] else "offline", "last_seen": now if d["online"] else None,
            "meta": {"unifi": {"kind": d["kind"], "ports": d["ports"], "clients": d["clients"]}}}, adopt_ip=d["ip"] or None, adopt_mac=d["mac"])
        if d["fw"]:
            updates.record(ids[d["mac"]], "unifi", [{"key": "unifi:firmware", "title": "Firmware", "installed": d["fw"],
                                                     "latest": d["upgrade_to"] or d["fw"], "available": d["upgradable"]}])
    _prune(integ, "unifi/", seen)
    managed = tuple(ids.values())
    # WLANs: fehlende SSIDs anlegen, leere Angaben ergänzen
    wl = {}
    for w in data["wlans"]:
        row = db.one("SELECT * FROM wlans WHERE ssid=?", (w["ssid"],))
        if row:
            if not row.get("security") and w["security"]:
                db.update("wlans", row["id"], {"security": w["security"]})
            wl[w["ssid"]] = row["id"]
        else:
            wl[w["ssid"]] = db.insert("wlans", {"ssid": w["ssid"], "security": w["security"], "note": "aus UniFi"})

    def wlan_id(ssid):
        if not ssid:
            return None
        if ssid not in wl:
            row = db.one("SELECT id FROM wlans WHERE ssid=?", (ssid,))
            wl[ssid] = row["id"] if row else db.insert("wlans", {"ssid": ssid, "note": "aus UniFi"})
        return wl[ssid]

    made = 0
    for ln in data["links"]:
        a, b = ids.get(ln["a"]), ids.get(ln["b"])
        if a and b:
            made += _unifi_link(integ, a, b, ln["kind"], ln["a_port"], ln["b_port"], ln["speed"],
                                wlan_id(ln["ssid"]) if ln["kind"] == "wlan" else None)
    # Clients: vorhandenen Geräten zuordnen (MAC, dann IP), auf Wunsch unbekannte anlegen
    create = str(c.get("clients") or "") in ("1", "true", "on", "True")
    group = None
    matched = new = 0
    for cl in data["clients"]:
        own = db.one("SELECT id FROM devices WHERE integration_id=? AND ext_id=?", (integ["id"], "unifi-client/" + cl["mac"]))
        dev = None if own else db.one("SELECT * FROM devices WHERE lower(mac)=? AND type<>'group'", (cl["mac"],))
        if not dev and not own and cl["ip"]:
            dev = db.one("SELECT * FROM devices WHERE ip=? AND type NOT IN ('group','vm','container','app','service') "
                         "AND (mac IS NULL OR mac='')", (cl["ip"],))
        if dev:
            upd = {"status": "online", "last_seen": now}
            for k in ("mac", "vendor", "hostname"):
                if cl[k] and not dev.get(k):
                    upd[k] = cl[k]
            if cl["ip"] and not dev.get("ip"):
                upd["ip"] = cl["ip"]
            upd["meta"] = {**(dev.get("meta") or {}), "unifi_client": {"ssid": cl["ssid"], "signal": cl["signal"], "network": cl["network"],
                                                                        "seen": now, "wired": cl["wired"]}}
            db.update("devices", dev["id"], upd)
            matched += 1
            did = dev["id"]
        elif create or own:
            if group is None and not own:
                g = db.one("SELECT id FROM devices WHERE integration_id=? AND ext_id='unifi-group/clients'", (integ["id"],))
                group = g["id"] if g else db.insert("devices", {"name": "UniFi-Clients", "type": "group", "icon": "unifi",
                                                                "source": "unifi", "integration_id": integ["id"], "ext_id": "unifi-group/clients"})
            info = {"unifi_client": {"ssid": cl["ssid"], "signal": cl["signal"], "network": cl["network"], "seen": now, "wired": cl["wired"]}}
            if own:                                      # Name, Typ und Platz gehören nach dem Anlegen dem Nutzer
                cur = db.one("SELECT meta FROM devices WHERE id=?", (own["id"],))
                db.update("devices", own["id"], {"status": "online", "last_seen": now, "ip": cl["ip"] or None,
                                                 "meta": {**((cur or {}).get("meta") or {}), **info}})
                did = own["id"]
                matched += 1
            else:
                did = _upsert(integ, "unifi-client/" + cl["mac"], {
                    "name": cl["name"] or cl["hostname"] or cl["mac"], "type": "client", "ip": cl["ip"] or None, "mac": cl["mac"],
                    "vendor": cl["vendor"] or None, "hostname": cl["hostname"] or None, "status": "online", "last_seen": now,
                    "parent_id": group, "meta": info})
                new += 1
        else:
            continue
        via = ids.get(cl["via"])
        if via and via != did:
            made += _unifi_link(integ, via, did, "cable" if cl["wired"] else "wlan", cl["port"] if cl["wired"] else "", "",
                                cl["speed"], None if cl["wired"] else wlan_id(cl["ssid"]), managed)
    # angelegte Clients, die gerade nicht verbunden sind: offline (sie werden nicht gelöscht, siehe „Nicht mehr gesehen“)
    live = {"unifi-client/" + cl["mac"] for cl in data["clients"]}
    for d in db.q("SELECT id, ext_id FROM devices WHERE integration_id=? AND ext_id LIKE 'unifi-client/%' AND status<>'offline'", (integ["id"],)):
        if d["ext_id"] not in live:
            db.update("devices", d["id"], {"status": "offline"})
    aps = sum(1 for d in data["infra"] if d["type"] == "ap")
    fwup = sum(1 for d in data["infra"] if d["upgradable"])
    sws = sum(1 for d in data["infra"] if d["type"] == "switch")
    off = sum(1 for d in data["infra"] if not d["online"])
    rest = len(data["clients"]) - matched - new
    return (f"{len(data['infra'])} UniFi-Geräte ({aps} APs, {sws} Switches{f', {off} offline' if off else ''}), "
            f"{len(data['clients'])} Clients: {matched} zugeordnet" + (f", {new} angelegt" if new else "") +
            (f", {rest} unbekannt" if rest and not create else "") + f" · {made} neue Verbindungen" + (f" · {fwup} Firmware-Updates" if fwup else "") + found)


from typing import Protocol

class Connector(Protocol):
    """Existing connector contract: receive integration record, return status summary."""
    def __call__(self, integ: dict) -> str: ...


SYNC: dict[str, Connector] = {"proxmox": sync_proxmox, "docker": sync_docker, "snmp": sync_snmp, "opnsense": sync_opnsense, "qnap": sync_qnap, "synology": sync_synology, "ipmi": sync_ipmi,
        "homeassistant": sync_homeassistant, "unifi": sync_unifi}


def sync(integ_id):
    integ = db.one("SELECT * FROM integrations WHERE id=?", (integ_id,))
    if not integ:
        return "nicht gefunden"
    try:
        handler = SYNC.get(integ["kind"])
        if handler is None:
            raise ValueError("Unbekannte Anbindung")
        status = "ok · " + handler(integ)
    except Exception as e:  # noqa: BLE001 – Status wird in der Oberfläche angezeigt
        status = "Fehler: " + explain(e, KINDS.get(integ["kind"], {}).get("label", "Anbindung"))[:300]
    db.x("UPDATE integrations SET last_sync=?, last_status=? WHERE id=?", (db.now(), status, integ_id))
    return status


def due_syncs():
    interval = max(1, int(db.setting("sync_interval_min") or 15)) * 60
    for i in db.q("SELECT id, last_sync FROM integrations WHERE enabled=1"):
        if db.now() - (i.get("last_sync") or 0) >= interval:
            sync(i["id"])

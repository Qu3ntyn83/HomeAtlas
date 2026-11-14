"""Anbindungen: lesen Systeme aus und pflegen Geräte, Kinder (VMs/Container), Ports und Kabel.

proxmox  – API-Token (read-only, Rolle PVEAuditor)
docker   – Docker-Engine-API, am besten über einen read-only docker-socket-proxy
snmp     – v2c über die net-snmp-Werkzeuge: Ports, Geschwindigkeit, PVID, LLDP-Nachbarn
opnsense – API-Key/Secret: VLANs und Subnetze (experimentell)
"""
import base64
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

from . import db

KINDS = {
    "proxmox": {"label": "Proxmox VE", "fields": [
        ["host", "Host/IP"], ["port", "Port", "8006"], ["token_id", "Token-ID (user@pve!name)"],
        ["token_secret", "Token-Secret", "", "password"]]},
    "docker": {"label": "Docker", "fields": [["url", "API-URL (http://host:2375)"]]},
    "snmp": {"label": "SNMP v2c", "fields": [["host", "Host/IP"], ["community", "Community", "public", "password"]]},
    "opnsense": {"label": "OPNsense (experimentell)", "fields": [
        ["host", "Host/IP oder URL (https://firewall:8443)"], ["port", "Port der Weboberfläche", "443"], ["key", "API-Key"],
        ["secret", "API-Secret", "", "password"]]},
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
                           f"den Zugriff vom LabVis-Host auf diesen Port?") from None
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
    return scheme, host, p or cfg.get("port") or default_port


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


def _upsert(integ, ext_id, data, adopt_ip=None, adopt_name=None):
    """Gerät dieser Anbindung anlegen/aktualisieren; vorhandene (gescannte) Geräte werden übernommen."""
    dev = db.one("SELECT * FROM devices WHERE integration_id=? AND ext_id=?", (integ["id"], ext_id))
    adopted = not dev
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
def sync_proxmox(integ):
    c = integ["config"]
    _, phost, pport = endpoint(c, 8006)
    reach(phost, pport)
    base = f"https://{phost}:{pport}/api2/json"
    hdr = {"Authorization": f"PVEAPIToken={c['token_id']}={c['token_secret']}"}

    def px(path):
        return _get(base + path, hdr)["data"]

    seen, n = set(), 0
    for node in px("/nodes"):
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
    _prune(integ, "guest/", seen)
    return f"{n} Gäste"


# ------------------------------------------------------------------ Docker
GENERIC = {"server", "app", "core", "backend", "web", "docker", "main", "latest", "frontend", "aio"}


def icon_from_image(image):
    parts = [p for p in image.split("@")[0].split(":")[0].split("/") if p]
    for p in reversed(parts):
        p = re.sub(r"^(docker-|lscr\.io|ghcr\.io)", "", p)
        if p and p not in GENERIC and "." not in p:
            return p.lower()
    return "docker"


def sync_docker(integ):
    c = integ["config"]
    url = c["url"].rstrip("/")
    pu = urllib.parse.urlparse(url)
    host = pu.hostname
    reach(host, pu.port or (443 if pu.scheme == "https" else 80))
    parent = integ.get("device_id")
    if not parent or not db.one("SELECT id FROM devices WHERE id=?", (parent,)):
        d = db.one("SELECT id FROM devices WHERE ip=?", (host,))
        parent = d["id"] if d else db.insert("devices", {"name": host, "ip": host, "type": "server", "icon": "docker",
                                                          "vlan_id": vlan_for_ip(host)})
        db.update("integrations", integ["id"], {"device_id": parent})
    seen = set()
    for ct in _get(url + "/containers/json?all=1"):
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
    return f"{len(seen)} Container"


# ------------------------------------------------------------------ SNMP
def _walk(host, community, oid):
    r = subprocess.run(["snmpwalk", "-v2c", "-c", community, "-t", "2", "-r", "1", "-OQn", host, oid],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        err = [ln for ln in (r.stderr or "").splitlines() if ln.strip() and not ln.startswith("Created directory")]
        msg = err[-1].strip() if err else "SNMP-Fehler"
        if "Timeout" in msg or "No Response" in msg:
            msg = (f"Keine SNMP-Antwort von {host}. Ist SNMP v2c am Gerät aktiv, stimmt die Community, und darf "
                   f"der LabVis-Host abfragen (Zugriffsliste am Gerät, UDP 161)?")
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


# ------------------------------------------------------------------ OPNsense (experimentell)
def sync_opnsense(integ):
    c = integ["config"]
    scheme, host, port = endpoint(c, 443)
    if not c.get("key") or not c.get("secret"):
        raise RuntimeError("API-Key und API-Secret fehlen (OPNsense: System → Zugang → Benutzer → API-Schlüssel)")
    reach(host, port)
    base = f"{scheme}://{host}:{port}/api"
    hdr = {"Authorization": "Basic " + base64.b64encode(f"{c['key'].strip()}:{c['secret'].strip()}".encode()).decode()}

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
    if not n:
        return "verbunden, aber keine VLANs angelegt (Schnittstellen → Andere Typen → VLAN)"
    return f"{n} VLANs"


# ------------------------------------------------------------------ Home Assistant
# Ein einziger Aufruf der Template-API liefert die Geräte-Registry als JSON (ohne WebSocket-Verbindung).
HA_TEMPLATE = (
    "{% set ns = namespace(out=[]) %}"
    "{% for did in states | map(attribute='entity_id') | map('device_id') | reject('none') | unique %}"
    "{% set ents = device_entities(did) %}{% set ce = device_attr(did,'primary_config_entry') %}"
    "{% set ns.out = ns.out + [{'id': did, 'name': device_attr(did,'name_by_user') or device_attr(did,'name'),"
    " 'mf': device_attr(did,'manufacturer'), 'model': device_attr(did,'model'), 'sw': device_attr(did,'sw_version'),"
    " 'area': area_name(did), 'via': device_attr(did,'via_device_id'),"
    " 'conns': device_attr(did,'connections') | list, 'idents': device_attr(did,'identifiers') | list,"
    " 'entry': device_attr(did,'entry_type'), 'integ': (config_entry_attr(ce,'domain') if ce else none),"
    " 'doms': ents | map('regex_replace','\\\\..*','') | unique | list, 'n': ents | count,"
    " 'un': ents | select('is_state','unavailable') | list | count}] %}"
    "{% endfor %}{{ ns.out | tojson }}")
HA_TYPES = [("vacuum", "vacuum"), ("camera", "camera"), ("light", "light"), ("climate", "thermostat"), ("cover", "blind"),
            ("lock", "lock"), ("media_player", "speaker"), ("switch", "plug"), ("binary_sensor", "sensor"), ("sensor", "sensor")]
HA_ICONS = {"hue": "philips-hue", "tplink": "tp-link", "smartthings": "smartthings", "roborock": "roborock", "tuya": "tuya",
            "alexa_media": "amazon-alexa", "matter": "matter", "zha": "zigbee", "mqtt": "mqtt", "esphome": "esphome",
            "shelly": "shelly", "ring": "ring", "bambu_lab": "bambu-lab", "samsungtv": "samsung", "unifi": "unifi"}


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
        devs = json.loads(r.read().decode())
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
        return (f"{len(real)} Geräte in {len(avail)} Integrationen gefunden – unter „Bearbeiten“ auswählen, "
                f"welche Integrationen übernommen werden")
    plan = ha_plan(devs, chosen)
    _, by_mac = scanner._index()
    ids, seen, new, upd, linked = {}, set(), 0, 0, 0
    for d in plan:
        ext = "ha/" + d["id"]
        name = (d.get("name") or d.get("model") or "Gerät").strip()
        own = db.one("SELECT * FROM devices WHERE integration_id=? AND ext_id=?", (integ["id"], ext))
        hit = None if own else (by_mac.get(d["mac"]) if d["mac"] else None)
        up = d["n"] == 0 or d["un"] < d["n"]
        ha_meta = {"ha": {"integration": d["integ"], "sw": d.get("sw"), "id": d["id"]}}
        if hit:                                   # vorhandenes (gescanntes) Gerät: nur anreichern
            dev = db.one("SELECT * FROM devices WHERE id=?", (hit[0],))
            auto = dev["name"] in (dev.get("ip"), (dev.get("hostname") or "").split(".")[0], dev.get("mac"))
            patch = {"meta": {**(dev["meta"] or {}), **ha_meta}}
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
                     "meta": {**(own["meta"] or {}), **ha_meta}}
            if up:
                patch["last_seen"] = db.now()
            if not own.get("room") and d.get("area"):
                patch["room"] = d["area"]
            if own["type"] in ("other", "iot") and ha_type(d):
                patch["type"] = ha_type(d)
            db.update("devices", own["id"], {k: v for k, v in patch.items() if v is not None})
            ids[d["id"]] = own["id"]
            upd += 1
        else:
            ids[d["id"]] = db.insert("devices", {
                "name": name, "type": ha_type(d) or "iot", "vendor": d.get("mf"), "model": d.get("model"), "mac": d["mac"],
                "room": d.get("area"), "status": "online" if up else "offline", "last_seen": db.now() if up else None,
                "source": "homeassistant", "integration_id": integ["id"], "ext_id": ext, "meta": ha_meta})
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
    return f"{new} neu, {upd} aktualisiert, {linked} mit vorhandenen Geräten verknüpft ({', '.join(sorted(chosen))})"


SYNC = {"proxmox": sync_proxmox, "docker": sync_docker, "snmp": sync_snmp, "opnsense": sync_opnsense,
        "homeassistant": sync_homeassistant}


def sync(integ_id):
    integ = db.one("SELECT * FROM integrations WHERE id=?", (integ_id,))
    if not integ:
        return "nicht gefunden"
    try:
        status = "ok · " + SYNC[integ["kind"]](integ)
    except Exception as e:  # noqa: BLE001 – Status wird in der Oberfläche angezeigt
        status = "Fehler: " + explain(e, KINDS[integ["kind"]]["label"])[:300]
    db.x("UPDATE integrations SET last_sync=?, last_status=? WHERE id=?", (db.now(), status, integ_id))
    return status


def due_syncs():
    interval = max(1, int(db.setting("sync_interval_min") or 15)) * 60
    for i in db.q("SELECT id, last_sync FROM integrations WHERE enabled=1"):
        if db.now() - (i.get("last_sync") or 0) >= interval:
            sync(i["id"])

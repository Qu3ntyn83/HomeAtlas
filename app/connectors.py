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
import ssl
import subprocess
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
        ["host", "Host/IP"], ["port", "Port", "443"], ["key", "API-Key"], ["secret", "API-Secret", "", "password"]]},
}
PALETTE = ["#58a6ff", "#f0883e", "#bc8cff", "#3fb950", "#e3b341", "#39c5cf", "#f85149", "#ff7b72", "#a5d6ff"]
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _get(url, headers=None, timeout=10):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return json.loads(r.read().decode())


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
    base = f"https://{c['host']}:{c.get('port') or 8006}/api2/json"
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
    host = urllib.parse.urlparse(url).hostname
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
        raise RuntimeError((r.stderr or "SNMP-Fehler").strip()[:200])
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
        if not (typ == "6" or "ethernet" in typ.lower()):
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
    w = {k: _walk(host, com, o) for k, o in oids.items()}
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
    return f"{len(ifaces)} Ports, {sum(1 for i in ifaces if i.get('neighbor'))} LLDP-Nachbarn, {made} neue Kabel"


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
    base = f"https://{c['host']}:{c.get('port') or 443}/api"
    hdr = {"Authorization": "Basic " + base64.b64encode(f"{c['key']}:{c['secret']}".encode()).decode()}

    def first(*paths):
        err = None
        for p in paths:
            try:
                r = _get(base + p, hdr)
                return r.get("rows", r) if isinstance(r, dict) else r
            except Exception as e:  # noqa: BLE001
                err = e
        raise err

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
    return f"{n} VLANs"


SYNC = {"proxmox": sync_proxmox, "docker": sync_docker, "snmp": sync_snmp, "opnsense": sync_opnsense}


def sync(integ_id):
    integ = db.one("SELECT * FROM integrations WHERE id=?", (integ_id,))
    if not integ:
        return "nicht gefunden"
    try:
        status = "ok · " + SYNC[integ["kind"]](integ)
    except Exception as e:  # noqa: BLE001 – Status wird in der Oberfläche angezeigt
        status = "Fehler: " + str(e)[:300]
    db.x("UPDATE integrations SET last_sync=?, last_status=? WHERE id=?", (db.now(), status, integ_id))
    return status


def due_syncs():
    interval = max(1, int(db.setting("sync_interval_min") or 15)) * 60
    for i in db.q("SELECT id, last_sync FROM integrations WHERE enabled=1"):
        if db.now() - (i.get("last_sync") or 0) >= interval:
            sync(i["id"])

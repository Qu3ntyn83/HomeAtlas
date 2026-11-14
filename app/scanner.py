"""Netzwerk-Scan: nmap (Hosts + Ports), HTTP-Titel, SNMP-Probe, Abgleich mit bekannten Geräten."""
import ipaddress
import os
import re
import shutil
import ssl
import subprocess
import threading
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

from . import db
from .fingerprints import HTTP_PORTS, SCAN_PORTS, TLS_PORTS, identify

LOCK = threading.Lock()
STATE = {"running": None, "phase": ""}
MAX_HOSTS = 4096
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
try:
    _CTX.set_ciphers("DEFAULT:@SECLEVEL=0")   # alte Geräte-Weboberflächen
except ssl.SSLError:
    pass


def _nmap(args, stdin=None, timeout=1800):
    base = ["nmap", "-oX", "-", "-T4"] + args
    r = subprocess.run(base, input=stdin, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0 or "<nmaprun" not in r.stdout:
        # ohne root / ohne NET_RAW: auf Connect-Scan zurückfallen
        r = subprocess.run(base + ["--unprivileged"], input=stdin, capture_output=True, text=True, timeout=timeout)
    if "<nmaprun" not in r.stdout:
        raise RuntimeError((r.stderr or "nmap lieferte keine Ausgabe").strip()[:300])
    return ET.fromstring(r.stdout)


def _hosts(root):
    out = {}
    for h in root.findall("host"):
        st = h.find("status")
        if st is None or st.get("state") != "up":
            continue
        d = {"ip": None, "mac": None, "vendor": None, "hostname": None, "ports": []}
        for a in h.findall("address"):
            if a.get("addrtype") == "ipv4":
                d["ip"] = a.get("addr")
            elif a.get("addrtype") == "mac":
                d["mac"] = a.get("addr", "").upper()
                d["vendor"] = a.get("vendor")
        hn = h.find("hostnames/hostname")
        if hn is not None:
            d["hostname"] = hn.get("name")
        for p in h.findall("ports/port"):
            s = p.find("state")
            if s is not None and s.get("state") == "open":
                d["ports"].append(int(p.get("portid")))
        if d["ip"]:
            out[d["ip"]] = d
    return out


def http_probe(ip, port):
    schemes = ["https", "http"] if port in TLS_PORTS else ["http", "https"]
    for sch in schemes:
        req = urllib.request.Request(f"{sch}://{ip}:{port}/", headers={"User-Agent": "LabVis-Scanner"})
        try:
            try:
                resp = urllib.request.urlopen(req, timeout=3, context=_CTX)
            except urllib.error.HTTPError as e:   # 401/403 liefern trotzdem Header und oft einen Titel
                resp = e
            body = resp.read(30000).decode("utf-8", "replace")
            m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
            return {"title": re.sub(r"\s+", " ", m.group(1)).strip()[:120] if m else "",
                    "server": (resp.headers.get("Server") or "")[:80], "scheme": sch}
        except Exception:
            continue
    return None


def snmp_get(ip, community, oids, timeout=1):
    if not shutil.which("snmpget"):
        return None
    try:
        r = subprocess.run(["snmpget", "-v2c", "-c", community, "-t", str(timeout), "-r", "0", "-Oqv", ip] + oids,
                           capture_output=True, text=True, timeout=timeout + 3)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0:
        return None
    return [ln.strip().strip('"') for ln in r.stdout.strip().splitlines()]


def _enrich(h, community):
    h["http"] = {}
    for p in h["ports"]:
        if p in HTTP_PORTS:
            r = http_probe(h["ip"], p)
            if r:
                h["http"][str(p)] = r
    v = snmp_get(h["ip"], community, ["1.3.6.1.2.1.1.1.0", "1.3.6.1.2.1.1.5.0"])
    h["snmp"] = {"descr": v[0], "name": v[1] if len(v) > 1 else ""} if v else {}
    if not h.get("hostname") and h["snmp"].get("name"):
        h["hostname"] = h["snmp"]["name"]
    h["guess"] = identify(h)
    return h


def discover(cidr, community="public"):
    """Scannt ein Netz und liefert angereicherte Hosts (ohne DB-Zugriff)."""
    net = ipaddress.ip_network(cidr, strict=False)
    if net.num_addresses > MAX_HOSTS:
        raise ValueError(f"Netz {cidr} ist zu groß (max. /{32 - (MAX_HOSTS - 1).bit_length()})")
    STATE["phase"] = "Hosts suchen"
    up = _hosts(_nmap(["-sn", str(net)]))
    if up:
        STATE["phase"] = f"Ports prüfen ({len(up)} Hosts)"
        ports = _hosts(_nmap(["-Pn", "-n", "--open", "-p", ",".join(map(str, SCAN_PORTS)), "-iL", "-"],
                             stdin="\n".join(up)))
        for ip, d in ports.items():
            if ip in up:
                up[ip]["ports"] = d["ports"]
                up[ip]["mac"] = up[ip]["mac"] or d["mac"]
                up[ip]["vendor"] = up[ip]["vendor"] or d["vendor"]
    STATE["phase"] = "Dienste erkennen"
    with ThreadPoolExecutor(max_workers=24) as ex:
        return list(ex.map(lambda h: _enrich(h, community), up.values()))


def apply(vlan, hosts):
    """Gleicht Scan-Ergebnisse mit Geräten ab. Unbekannte Hosts landen in der Fundliste."""
    now, new = db.now(), 0
    net = ipaddress.ip_network(vlan["subnet"], strict=False)
    seen = set()
    for h in hosts:
        dev = None
        if h.get("mac"):
            dev = db.one("SELECT * FROM devices WHERE mac=?", (h["mac"],))
        if not dev:
            dev = db.one("SELECT * FROM devices WHERE ip=?", (h["ip"],))
        if dev:
            seen.add(dev["id"])
            meta = dev["meta"] or {}
            meta["suggestions"] = h["guess"]["suggestions"]
            meta["http"] = h["http"]
            upd = {"status": "online", "last_seen": now, "ports": h["ports"], "meta": meta, "ip": h["ip"]}
            for k in ("mac", "vendor", "hostname"):
                if h.get(k) and not dev.get(k):
                    upd[k] = h[k]
            if not dev.get("vlan_id"):
                upd["vlan_id"] = vlan["id"]
            db.update("devices", dev["id"], upd)
            db.x("DELETE FROM discoveries WHERE ip=? OR (mac IS NOT NULL AND mac=?)", (h["ip"], h.get("mac")))
            continue
        row = None
        if h.get("mac"):
            row = db.one("SELECT * FROM discoveries WHERE mac=?", (h["mac"],))
        if not row:
            row = db.one("SELECT * FROM discoveries WHERE ip=?", (h["ip"],))
        vals = [h["ip"], h.get("mac"), h.get("vendor"), h.get("hostname"), vlan["id"], h["ports"], h["http"],
                h["snmp"], h["guess"], now]
        if row:
            db.x("UPDATE discoveries SET ip=?,mac=?,vendor=?,hostname=?,vlan_id=?,ports=?,http=?,snmp=?,guess=?,"
                 "last_seen=? WHERE id=?", vals + [row["id"]])
        else:
            new += 1
            db.x("INSERT INTO discoveries(ip,mac,vendor,hostname,vlan_id,ports,http,snmp,guess,last_seen,first_seen)"
                 " VALUES(?,?,?,?,?,?,?,?,?,?,?)", vals + [now])
    # bekannte Geräte in diesem Netz, die nicht geantwortet haben
    for d in db.q("SELECT id, ip, source FROM devices WHERE ip IS NOT NULL AND ip<>''"):
        try:
            inside = ipaddress.ip_address(d["ip"]) in net
        except ValueError:
            continue
        if inside and d["id"] not in seen and d["source"] in ("manual", "scan", "import"):
            db.update("devices", d["id"], {"status": "offline"})
    return new


def scan_vlan(vlan_id):
    vlan = db.one("SELECT * FROM vlans WHERE id=?", (vlan_id,))
    if not vlan or not vlan.get("subnet"):
        return
    if not LOCK.acquire(blocking=False):
        return
    sid = db.x("INSERT INTO scans(network,started,status) VALUES(?,?,?)", (vlan["subnet"], db.now(), "läuft"))
    STATE["running"] = vlan["subnet"]
    try:
        hosts = discover(vlan["subnet"], db.setting("snmp_community"))
        new = apply(vlan, hosts)
        db.x("UPDATE scans SET finished=?,hosts=?,new=?,status=? WHERE id=?", (db.now(), len(hosts), new, "ok", sid))
    except Exception as e:  # noqa: BLE001 – Fehler landen im Scan-Protokoll
        db.x("UPDATE scans SET finished=?,status=?,log=? WHERE id=?", (db.now(), "fehler", str(e)[:500], sid))
    finally:
        db.x("UPDATE vlans SET last_scan=? WHERE id=?", (db.now(), vlan_id))
        db.x("DELETE FROM scans WHERE id NOT IN (SELECT id FROM scans ORDER BY id DESC LIMIT 100)")
        STATE["running"], STATE["phase"] = None, ""
        LOCK.release()


def scan_async(vlan_id):
    threading.Thread(target=scan_vlan, args=(vlan_id,), daemon=True).start()


def due_scans():
    interval = max(5, int(db.setting("scan_interval_min") or 60)) * 60
    for v in db.q("SELECT * FROM vlans WHERE scan=1 AND subnet IS NOT NULL AND subnet<>''"):
        if db.now() - (v.get("last_scan") or 0) >= interval:
            scan_vlan(v["id"])


def privileged():
    return os.geteuid() == 0

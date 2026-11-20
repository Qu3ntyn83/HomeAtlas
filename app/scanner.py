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


def clean_name(name):
    """Platzhalter, die Geräte statt eines Namens melden, sind kein Name."""
    name = (name or "").strip()
    return "" if name.lower() in ("(none)", "none", "unknown", "localhost", "localhost.localdomain", "null", "-") else name


def _enrich(h, community):
    h["http"] = {}
    for p in h["ports"]:
        if p in HTTP_PORTS:
            r = http_probe(h["ip"], p)
            if r:
                h["http"][str(p)] = r
    v = snmp_get(h["ip"], community, ["1.3.6.1.2.1.1.1.0", "1.3.6.1.2.1.1.5.0"])
    h["snmp"] = {"descr": v[0], "name": v[1] if len(v) > 1 else ""} if v else {}
    h["hostname"] = clean_name(h.get("hostname")) or None
    if not h.get("hostname") and clean_name(h["snmp"].get("name")):
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
    # ARP der Firewall: liefert MACs auch für geroutete Netze und Geräte, die auf Ping nicht antworten
    from . import ipam
    arp = {ip: a for ip, a in ipam.arp_table().items() if ipaddress.ip_address(ip) in net}
    for ip, a in arp.items():
        h = up.setdefault(ip, {"ip": ip, "mac": None, "vendor": None, "hostname": None, "ports": []})
        if not h.get("mac"):
            h["mac"] = a["mac"].upper()
            h["vendor"] = h.get("vendor") or a.get("vendor") or None
        if not h.get("hostname") and a.get("hostname"):
            h["hostname"] = a["hostname"]
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


def _index():
    """ip/mac → (geräte_id, adress_index); index None = Hauptadresse, sonst Position in meta.addrs."""
    by_ip, by_mac = {}, {}
    for d in db.q("SELECT id, ip, mac, meta FROM devices"):
        if d.get("ip"):
            by_ip.setdefault(d["ip"], (d["id"], None))
        if d.get("mac"):
            by_mac.setdefault(d["mac"].upper(), (d["id"], None))
        for n, a in enumerate((d["meta"] or {}).get("addrs") or []):
            if a.get("ip"):
                by_ip.setdefault(a["ip"], (d["id"], n))
            if a.get("mac"):
                by_mac.setdefault(a["mac"].upper(), (d["id"], n))
    return by_ip, by_mac


def _merge_sug(old, new):
    kinds = {s["kind"] for s in old}
    return old + [s for s in new if s["kind"] not in kinds]


def apply(vlan, hosts):
    """Gleicht Scan-Ergebnisse mit Geräten ab. Unbekannte Hosts landen in der Fundliste.
    Ein Gerät kann mehrere Adressen haben (meta.addrs); jede wird einzeln wiedererkannt."""
    now, new = db.now(), 0
    net = ipaddress.ip_network(vlan["subnet"], strict=False)
    by_ip, by_mac = _index()
    seen = set()
    for h in hosts:
        hit = (by_mac.get(h["mac"]) if h.get("mac") else None) or by_ip.get(h["ip"])
        dev = db.one("SELECT * FROM devices WHERE id=?", (hit[0],)) if hit else None
        if dev:
            idx = hit[1]
            seen.add((dev["id"], idx))
            meta = dev["meta"] or {}
            upd = {"status": "online", "last_seen": now}
            if idx is None:
                meta["suggestions"] = h["guess"]["suggestions"]
                meta["http"] = h["http"]
                meta["up0"] = True
                upd.update(ports=h["ports"], ip=h["ip"])
                for k in ("mac", "vendor", "hostname"):
                    if h.get(k) and not dev.get(k):
                        upd[k] = h[k]
                if not dev.get("vlan_id"):
                    upd["vlan_id"] = vlan["id"]
            else:
                a = meta["addrs"][idx]
                a.update(ip=h["ip"], up=True, last_seen=now, vlan_id=a.get("vlan_id") or vlan["id"])
                for k in ("mac", "vendor", "hostname"):
                    if h.get(k) and not a.get(k):
                        a[k] = h[k]
                meta["suggestions"] = _merge_sug(meta.get("suggestions") or [], h["guess"]["suggestions"])
                upd["ports"] = sorted(set(dev.get("ports") or []) | set(h["ports"]))
            upd["meta"] = meta
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

    def inside(ip):
        try:
            return bool(ip) and ipaddress.ip_address(ip) in net
        except ValueError:
            return False

    # Adressen in diesem Netz, die nicht geantwortet haben; das Gerät ist online, solange eine Adresse antwortet
    for d in db.q("SELECT id, ip, status, source, meta FROM devices"):
        if d["source"] not in ("manual", "scan", "import"):
            continue
        meta, addrs, changed = d["meta"] or {}, (d["meta"] or {}).get("addrs") or [], False
        if inside(d["ip"]) and (d["id"], None) not in seen:
            meta["up0"], changed = False, True
        for n, a in enumerate(addrs):
            if inside(a.get("ip")) and (d["id"], n) not in seen:
                a["up"], changed = False, True
        if changed:
            up = (bool(d["ip"]) and meta.get("up0", d["status"] == "online")) or any(a.get("up") for a in addrs)
            db.update("devices", d["id"], {"status": "online" if up else "offline", "meta": meta})
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

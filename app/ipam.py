"""IPAM und DNS: verbindet die Dokumentation mit DNS-Einträgen, DHCP und ARP-Tabelle der OPNsense.

Gelesen wird beim Abgleich der OPNsense-Anbindung (fetch). Die Auswertung (build) läuft bei jedem Abruf der Seite gegen den
aktuellen Stand der Dokumentation. Schreiben (DNS-Einträge, DHCP-Reservierungen) nur, wenn es in der Anbindung erlaubt ist.
"""
import ipaddress
import json
import re
import urllib.error

from fastapi import APIRouter, Body, HTTPException

from . import connectors, db

router = APIRouter()
NO_DNS = {"internet", "group", "patchpanel", "shelf", "blank", "cablemgmt"}


# ------------------------------------------------------------------ Lesen
def _ip(v):
    v = (v or "").strip().split("/")[0]
    try:
        return str(ipaddress.IPv4Address(v))
    except ValueError:
        return ""


def _mac(v):
    v = (v or "").strip().lower().replace("-", ":")
    return v if re.match(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$", v) else ""


def _on(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on", "enabled")


def _range(txt):
    """Kea-Pools: „a - b“ oder Netz in CIDR, mehrere durch Zeilenumbruch oder Komma getrennt."""
    out = []
    for part in re.split(r"[\n,]+", txt or ""):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = (_ip(x) for x in part.split("-", 1))
            if a and b:
                out.append((a, b))
        else:
            try:
                n = ipaddress.IPv4Network(part, strict=False)
                out.append((str(n[0]), str(n[-1])))
            except ValueError:
                pass
    return out


def fetch(integ, cli):
    """Liest DNS, DHCP und ARP. Jeder Teil darf fehlen (Dienst nicht installiert) oder an Rechten scheitern."""
    snap = {"errors": {}, "services": {}, "dns": [], "reservations": [], "leases": [], "pools": [], "subnets": [], "arp": []}

    def part(name, fn):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            if e.code != 404:                         # 404: Dienst/Plugin nicht vorhanden – kein Fehler
                snap["errors"][name] = connectors.explain(e, name)
        except Exception as e:  # noqa: BLE001
            snap["errors"][name] = connectors.explain(e, name)
        return None

    for svc in ("unbound", "dnsmasq", "kea"):
        st = part(svc, lambda svc=svc: cli.call(f"/{svc}/service/status"))
        if isinstance(st, dict):
            snap["services"][svc] = st.get("status") or "unbekannt"

    for r in part("Unbound", lambda: cli.search("/unbound/settings/search_host_override")) or []:
        rr = (r.get("rr") or "A").split()[0].upper()
        snap["dns"].append({"src": "unbound", "uuid": r.get("uuid"), "hostname": (r.get("hostname") or "").strip(),
                            "domain": (r.get("domain") or "").strip(), "rr": rr, "value": (r.get("server") or r.get("mx") or "").strip(),
                            "enabled": _on(r.get("enabled", "1")), "desc": r.get("description") or ""})
    for r in part("Dnsmasq", lambda: cli.search("/dnsmasq/settings/search_host")) or []:
        ips = [x for x in (_ip(i) for i in re.split(r"[,\s]+", r.get("ip") or "")) if x]
        macs = [x for x in (_mac(m) for m in re.split(r"[,\s]+", r.get("hwaddr") or "")) if x]
        if r.get("host"):
            for ip in ips or [""]:
                snap["dns"].append({"src": "dnsmasq", "uuid": r.get("uuid"), "hostname": r["host"].strip(), "domain": (r.get("domain") or "").strip(),
                                    "rr": "A", "value": ip, "enabled": True, "desc": r.get("descr") or ""})
        if macs and ips:
            snap["reservations"].append({"src": "dnsmasq", "uuid": r.get("uuid"), "ip": ips[0], "mac": macs[0], "hostname": r.get("host") or "",
                                         "desc": r.get("descr") or ""})
    for r in part("Dnsmasq", lambda: cli.search("/dnsmasq/settings/search_range")) or []:
        a, b = _ip(r.get("start_addr")), _ip(r.get("end_addr"))
        if a and b:
            snap["pools"].append({"src": "dnsmasq", "start": a, "end": b})
    for r in part("Kea", lambda: cli.search("/kea/dhcpv4/search_subnet")) or []:
        snap["subnets"].append({"uuid": r.get("uuid"), "subnet": (r.get("subnet") or "").strip()})
        for a, b in _range(r.get("pools")):
            snap["pools"].append({"src": "kea", "start": a, "end": b})
    for r in part("Kea", lambda: cli.search("/kea/dhcpv4/search_reservation")) or []:
        if _ip(r.get("ip_address")):
            snap["reservations"].append({"src": "kea", "uuid": r.get("uuid"), "ip": _ip(r.get("ip_address")), "mac": _mac(r.get("hw_address")),
                                         "hostname": r.get("hostname") or "", "desc": r.get("description") or ""})
    for src, path in (("kea", "/kea/leases4/search"), ("dnsmasq", "/dnsmasq/leases/search"), ("isc", "/dhcpv4/leases/search_lease")):
        if src == "dnsmasq" and snap["services"].get("dnsmasq") not in (None, "running"):
            continue
        rows = part({"kea": "Kea", "dnsmasq": "Dnsmasq", "isc": "ISC DHCP"}[src], lambda path=path: cli.search(path)) or []
        for r in rows:
            ip = _ip(r.get("address"))
            if not ip:
                continue
            static = (r.get("lease_type") or r.get("type") or "") == "static"
            snap["leases"].append({"src": src, "ip": ip, "mac": _mac(r.get("hwaddr") or r.get("mac")), "hostname": (r.get("hostname") or "").strip(),
                                   "static": static, "active": str(r.get("state", r.get("status", "active"))) in ("0", "active", "online", "")})
            if src == "isc" and static and not any(x["ip"] == ip for x in snap["reservations"]):
                snap["reservations"].append({"src": "isc", "uuid": None, "ip": ip, "mac": _mac(r.get("mac")), "hostname": r.get("hostname") or "", "desc": ""})
    arp = part("ARP", lambda: cli.call("/diagnostics/interface/get_arp"))
    for r in arp if isinstance(arp, list) else (arp or {}).get("rows", []) if isinstance(arp, dict) else []:
        if _ip(r.get("ip")) and _mac(r.get("mac")) and not r.get("permanent") and not r.get("expired"):
            snap["arp"].append({"ip": _ip(r["ip"]), "mac": _mac(r["mac"]), "hostname": (r.get("hostname") or "").strip(),
                                "intf": r.get("intf_description") or r.get("intf") or "", "vendor": (r.get("manufacturer") or "").strip() or vendor(r["mac"])})
    # Internetzugang: Gateway-Zustand (dpinger) und WAN-Adressen
    snap["gateways"], snap["wan"] = [], []
    gws = part("Gateways", lambda: cli.call("/routes/gateway/status"))
    for g in (gws or {}).get("items", []) if isinstance(gws, dict) else []:
        if g.get("name"):
            snap["gateways"].append({k: g.get(k) for k in ("name", "address", "status", "status_translated", "delay", "stddev", "loss", "monitor")})
    info = part("Schnittstellen", lambda: cli.call("/interfaces/overview/interfaces_info"))
    rows = info.get("rows", []) if isinstance(info, dict) else info or []
    for r in rows:
        a4 = (r.get("addr4") or "").split("/")[0]
        try:
            pub = bool(a4) and ipaddress.IPv4Address(a4).is_global
        except ValueError:
            pub = False
        ident, descr = (r.get("identifier") or "").lower(), r.get("description") or ""
        if ident.startswith("wan") or "wan" in descr.lower() or pub or (r.get("gateways") or []):
            snap["wan"].append({"identifier": ident, "description": descr, "device": r.get("device") or "", "addr4": a4,
                                "addr6": (r.get("addr6") or "").split("/")[0], "gateways": r.get("gateways") or []})
    db.x("INSERT OR REPLACE INTO opn_cache(integration_id, data, fetched) VALUES(?,?,?)", (integ["id"], json.dumps(snap), db.now()))
    learned = apply_arp()
    isp = apply_isp()
    a = [x for x in (f"{sum(1 for d in snap['dns'] if d['rr'] in ('A', 'AAAA'))} DNS-Einträge" if snap["dns"] else "",
                     f"{len(snap['reservations'])} Reservierungen" if snap["reservations"] else "",
                     f"{len(snap['leases'])} Leases" if snap["leases"] else "", f"ARP {len(snap['arp'])}" if snap["arp"] else "") if x]
    if learned:
        a.append(learned)
    if isp:
        a.append(isp)
    if snap["errors"]:
        a.append("⚠ " + "; ".join(sorted(set(snap["errors"].values())))[:160])
    return " · ".join(a)


# ------------------------------------------------------------------ ARP der Firewall: MAC-Adressen auch aus anderen Netzen
_OUI = None


def vendor(mac):
    """Hersteller aus den ersten drei Bytes der MAC (Liste von nmap); lokal verwaltete (zufällige) MACs haben keinen."""
    global _OUI
    mac = _mac(mac)
    if not mac or int(mac[1], 16) & 2:
        return ""
    if _OUI is None:
        _OUI = {}
        try:
            with open("/usr/share/nmap/nmap-mac-prefixes", encoding="utf-8", errors="replace") as f:
                for ln in f:
                    if len(ln) > 7 and ln[6] == " " and ln[0] != "#":
                        _OUI[ln[:6].upper()] = ln[7:].strip()
        except OSError:
            pass
    return _OUI.get(mac.replace(":", "")[:6].upper(), "")


def gateways():
    """Gateways aller OPNsense-Anbindungen mit Zustand und passender WAN-Schnittstelle."""
    out = []
    for row in db.q("SELECT data, fetched FROM opn_cache ORDER BY fetched"):
        snap = json.loads(row["data"])
        wans = snap.get("wan") or []
        for g in snap.get("gateways") or []:
            key = g["name"].split("_")[0].lower()           # WAN_DHCP → wan, WAN2_PPPOE → wan2
            w = next((x for x in wans if g["name"] in (x.get("gateways") or [])), None) or \
                next((x for x in wans if key in (x["identifier"], x["description"].lower())), None) or (wans[0] if len(wans) == 1 else None)
            out.append({**g, "wan": w, "at": row["fetched"]})
    return out


def _num(v):
    m = re.search(r"[\d.]+", str(v or ""))
    return float(m.group(0)) if m else None


def apply_isp():
    """Zustand der Gateways an die Internet-Geräte schreiben (Status, Latenz, Verlust, WAN-Adresse)."""
    from . import types
    gws = {g["name"]: g for g in gateways()}
    if not gws:
        return ""
    nets = [d for d in db.q("SELECT id, type, status, meta FROM devices") if types.base(d["type"]) == "internet"]
    if len(nets) == 1 and len(gws) == 1 and not ((nets[0]["meta"] or {}).get("isp") or {}).get("gateway"):
        m = nets[0]["meta"] or {}
        m["isp"] = {**(m.get("isp") or {}), "gateway": next(iter(gws))}   # eindeutig: eine Leitung, ein Gateway
        nets[0]["meta"] = m
    n = 0
    for d in nets:
        meta = d["meta"] or {}
        g = gws.get((meta.get("isp") or {}).get("gateway") or "")
        if not g:
            continue
        st = (g.get("status") or "").lower()
        w = g.get("wan") or {}
        ip4 = w.get("addr4") or ""
        try:
            a = ipaddress.IPv4Address(ip4) if ip4 else None
        except ValueError:
            a = None
        meta["isp_live"] = {"status": st or "unknown", "text": g.get("status_translated") or "", "delay": _num(g.get("delay")), "loss": _num(g.get("loss")),
                            "address": g.get("address") or "", "monitor": g.get("monitor") or "", "wan_ip": ip4, "wan_ip6": w.get("addr6") or "",
                            "wan_if": w.get("description") or w.get("identifier") or "",
                            "nat": bool(a and a.is_private and a not in ipaddress.IPv4Network("100.64.0.0/10")),
                            "cgnat": bool(a and a in ipaddress.IPv4Network("100.64.0.0/10")), "at": g.get("at")}
        status = "offline" if st in ("down", "force_down") else "online" if st in ("none", "loss", "delay", "delay+loss", "") else d["status"]
        db.update("devices", d["id"], {"meta": meta, "status": status, **({"last_seen": db.now()} if status == "online" else {})})
        n += 1
    return f"Internet: {n} Leitung{'en' if n != 1 else ''}" if n else ""


def arp_table():
    """Zusammengeführte ARP-Tabellen aller OPNsense-Anbindungen: ip → Eintrag."""
    out = {}
    for row in db.q("SELECT data FROM opn_cache ORDER BY fetched"):
        for a in json.loads(row["data"]).get("arp") or []:
            out[a["ip"]] = a
    return out


def apply_arp():
    """Ergänzt fehlende MAC-Adressen (und Hersteller) an Geräten, Zusatzadressen und Funden aus der ARP-Tabelle.
    Ein Scan sieht MACs nur im eigenen Netz; die Firewall kennt sie aus allen Netzen, die sie routet."""
    arp = arp_table()
    if not arp:
        return ""
    known = {(_mac(d["mac"])) for d in db.q("SELECT mac FROM devices WHERE mac IS NOT NULL AND mac<>''")}
    dev_n = disc_n = 0
    devs = db.q("SELECT id, ip, mac, vendor, meta FROM devices")
    ip_count = {}
    for d in devs:
        if _ip(d["ip"]):
            ip_count[_ip(d["ip"])] = ip_count.get(_ip(d["ip"]), 0) + 1
    for d in devs:
        upd, meta = {}, d["meta"] or {}
        a = arp.get(_ip(d["ip"]))
        if a and not _mac(d["mac"]) and a["mac"] not in known and ip_count.get(_ip(d["ip"])) == 1:   # bei doppelter IP nicht raten
            upd["mac"] = a["mac"].upper()
            known.add(a["mac"])
            if not d["vendor"] and a.get("vendor"):
                upd["vendor"] = a["vendor"]
            meta["mac_src"] = "arp"
        changed = False
        for x in meta.get("addrs") or []:
            a = arp.get(_ip(x.get("ip")))
            if a and not _mac(x.get("mac")) and a["mac"] not in known:
                x["mac"], changed = a["mac"].upper(), True
                known.add(a["mac"])
        if upd or changed:
            upd["meta"] = meta
            db.update("devices", d["id"], upd)
            dev_n += 1
    for r in db.q("SELECT id, ip, mac, vendor FROM discoveries WHERE mac IS NULL OR mac=''"):
        a = arp.get(_ip(r["ip"]))
        if a:
            db.x("UPDATE discoveries SET mac=?, vendor=COALESCE(NULLIF(vendor,''), ?) WHERE id=?", (a["mac"].upper(), a.get("vendor") or None, r["id"]))
            disc_n += 1
    parts = [f"{dev_n} Geräte" if dev_n else "", f"{disc_n} Funde" if disc_n else ""]
    return ("MAC aus ARP ergänzt: " + ", ".join(p for p in parts if p)) if dev_n or disc_n else ""


# ------------------------------------------------------------------ Auswerten
def slug(name):
    s = (name or "").strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9-]+", "-", s.split(".")[0]).strip("-")
    return s[:63]


def _source():
    i = db.one("SELECT * FROM integrations WHERE kind='opnsense' ORDER BY enabled DESC, id LIMIT 1")
    if not i:
        return None, None
    row = db.one("SELECT * FROM opn_cache WHERE integration_id=?", (i["id"],))
    return i, ({**json.loads(row["data"]), "fetched": row["fetched"]} if row else None)


def _writable(integ):
    return bool(integ) and str((integ.get("config") or {}).get("write") or "").lower() in ("1", "true", "on", "yes")


def build():
    integ, snap = _source()
    snap = snap or {"errors": {}, "services": {}, "dns": [], "reservations": [], "leases": [], "pools": [], "subnets": [], "arp": []}
    devs = db.q("SELECT id, name, hostname, type, ip, mac, meta, vlan_id, status FROM devices")
    by_ip = {}
    for d in devs:
        if d["type"] in NO_DNS:
            continue
        if _ip(d["ip"]):
            by_ip.setdefault(_ip(d["ip"]), []).append({"id": d["id"], "name": d["name"], "mac": _mac(d["mac"]), "primary": True})
        for a in (d.get("meta") or {}).get("addrs") or []:
            if _ip(a.get("ip")):
                by_ip.setdefault(_ip(a["ip"]), []).append({"id": d["id"], "name": d["name"], "mac": _mac(a.get("mac")), "primary": False,
                                                           "label": a.get("label") or ""})
    res = {r["ip"]: r for r in snap["reservations"]}
    leases = {}
    for le in sorted(snap["leases"], key=lambda x: not x["active"]):
        leases.setdefault(le["ip"], le)
    arp = {a["ip"]: a for a in snap["arp"]}
    dns_by_ip = {}
    for r in snap["dns"]:
        if r["rr"] == "A" and r["value"]:
            dns_by_ip.setdefault(r["value"], []).append(".".join(x for x in (r["hostname"], r["domain"]) if x))
    pools = [(int(ipaddress.IPv4Address(p["start"])), int(ipaddress.IPv4Address(p["end"])), p["src"]) for p in snap["pools"]]
    in_pool = lambda n: any(a <= n <= b for a, b, _ in pools)   # noqa: E731

    # Gerät mit bekannter MAC antwortet laut ARP unter einer anderen Adresse (DHCP hat neu vergeben, Gerät umgezogen)
    mac_dev = {}
    for d in devs:
        if _mac(d["mac"]) and d["type"] not in NO_DNS:
            mac_dev.setdefault(_mac(d["mac"]), d)
    moved = {}
    for ip, a in arp.items():
        d = mac_dev.get(a["mac"])
        if d and _ip(d["ip"]) and _ip(d["ip"]) != ip and (arp.get(_ip(d["ip"])) or {}).get("mac") != a["mac"] \
                and not any(x["id"] == d["id"] for x in by_ip.get(ip, [])):
            moved[ip] = {"id": d["id"], "name": d["name"], "old": _ip(d["ip"])}
    all_nets = []
    subnets = []
    for v in db.q("SELECT id, vid, name, subnet, gateway, color FROM vlans WHERE subnet IS NOT NULL AND subnet<>'' ORDER BY vid"):
        try:
            net = ipaddress.IPv4Network(v["subnet"], strict=False)
        except ValueError:
            continue
        all_nets.append(net)
        first, last = int(net.network_address), int(net.broadcast_address)
        gw = _ip(v["gateway"])
        cells, conflicts = {}, []
        ips = {ip for ip in set(by_ip) | set(res) | set(leases) | set(arp) | set(dns_by_ip) if ipaddress.IPv4Address(ip) in net}
        if gw:
            ips.add(gw)
        for ip in sorted(ips, key=lambda x: int(ipaddress.IPv4Address(x))):
            n = int(ipaddress.IPv4Address(ip))
            ds, r, le, a = by_ip.get(ip, []), res.get(ip), leases.get(ip), arp.get(ip)
            c = {"ip": ip, "off": n - first, "devs": [{k: x[k] for k in ("id", "name", "primary")} | ({"label": x["label"]} if x.get("label") else {}) for x in ds],
                 "res": r, "lease": le, "arp": a, "dns": dns_by_ip.get(ip, []), "gw": ip == gw, "pool": in_pool(n), "issues": []}
            macs = {x["mac"] for x in ds if x["mac"]}
            names = ", ".join(sorted({x["name"] for x in ds}))
            if len({x["id"] for x in ds}) > 1:
                c["issues"].append(("dup", f"Mehrere Geräte mit derselben Adresse: {names}"))
            if r and r["mac"] and macs and r["mac"] not in macs:
                c["issues"].append(("res_mac", f"Reservierung gilt für {r['mac']}, dokumentiert ist {', '.join(sorted(macs))}"))
            if a and macs and a["mac"] not in macs and not (r and r["mac"] == a["mac"]):
                c["issues"].append(("arp_mac", f"Im Netz antwortet {a['mac']}, dokumentiert ist {', '.join(sorted(macs))} – Adresskonflikt?"))
            if ds and c["pool"] and not r and not (le and le["mac"] in macs):
                c["issues"].append(("pool", "Feste Adresse im DHCP-Bereich ohne Reservierung – DHCP kann sie an ein anderes Gerät vergeben"))
            if not ds and not c["gw"] and ((le and le["active"]) or a or r):
                c["undoc"] = True
            if ip in moved:
                m = moved[ip]
                c["moved"] = m
                c["issues"].append(("moved", f"Laut ARP ist das {m['name']} – dokumentiert mit {m['old']}"))
            for k, msg in c["issues"]:
                conflicts.append({"ip": ip, "kind": k, "text": msg})
            cells[ip] = c
        used = {ip for ip, c in cells.items() if c["devs"] or c["res"] or (c["lease"] and c["lease"]["active"]) or c["arp"] or c["gw"]}
        hosts = max(0, last - first - 1) if net.prefixlen < 31 else last - first + 1
        pool_n = sum(max(0, min(b, last - 1) - max(a, first + 1) + 1) for a, b, _ in pools)
        nxt = None
        for n in range(first + 1, min(last, first + 65536)):
            ip = str(ipaddress.IPv4Address(n))
            if ip not in used and ip not in cells and not in_pool(n):
                nxt = ip
                break
        subnets.append({"vlan_id": v["id"], "vid": v["vid"], "name": v["name"], "color": v["color"], "subnet": str(net), "first": str(net.network_address),
                        "size": last - first + 1, "hosts": hosts, "gateway": gw, "used": len(used), "documented": sum(1 for c in cells.values() if c["devs"]),
                        "undoc": sum(1 for c in cells.values() if c.get("undoc")), "pool_size": pool_n, "next_free": nxt,
                        "pools": [{"start": str(ipaddress.IPv4Address(max(a, first))), "end": str(ipaddress.IPv4Address(min(b, last))), "src": s}
                                  for a, b, s in pools if b >= first and a <= last],
                        "cells": list(cells.values()), "conflicts": conflicts})

    # Adressen außerhalb aller dokumentierten Netze (Hinweis auf fehlende Netze), je /24 zusammengefasst
    outside = {}
    for ip in set(arp) | {le["ip"] for le in snap["leases"] if le["active"]} | set(res):
        a4 = ipaddress.IPv4Address(ip)
        if a4.is_loopback or a4.is_link_local or any(a4 in n for n in all_nets):
            continue
        key = str(ipaddress.IPv4Network(f"{ip}/24", strict=False))
        o = outside.setdefault(key, {"subnet": key, "count": 0, "examples": [], "intf": ""})
        o["count"] += 1
        a = arp.get(ip) or {}
        o["intf"] = o["intf"] or a.get("intf") or ""
        if len(o["examples"]) < 4:
            o["examples"].append(ip)

    # DNS: Einträge gegen die Dokumentation
    name_of = {}
    for d in devs:
        for nm in {slug(d["hostname"]), slug(d["name"])} - {""}:
            name_of.setdefault(nm, []).append(d)
    fq = {}
    for r in snap["dns"]:
        fq.setdefault((r["hostname"].lower(), r["domain"].lower()), set()).add(r["value"])
    records = []
    for r in snap["dns"]:
        e = {**r, "fqdn": ".".join(x for x in (r["hostname"], r["domain"]) if x), "devs": [], "status": "other", "suggest": None}
        if r["rr"] == "A" and r["value"]:
            at = by_ip.get(r["value"], [])
            e["devs"] = [{"id": x["id"], "name": x["name"]} for x in at]
            same = [d for d in name_of.get(slug(r["hostname"]), []) if _ip(d["ip"])]
            if len(fq[(r["hostname"].lower(), r["domain"].lower())]) > 1:
                e["status"] = "dup"
            elif at:
                e["status"] = "ok"
            elif same and not any(_ip(d["ip"]) == r["value"] for d in same):
                e["status"], e["suggest"] = "moved", {"ip": _ip(same[0]["ip"]), "id": same[0]["id"], "name": same[0]["name"]}
            else:
                e["status"] = "orphan"
            if not r["enabled"]:
                e["status"] = "off"
        records.append(e)
    covered = {r["value"] for r in snap["dns"] if r["rr"] == "A" and r["enabled"]}
    lease_name = {le["ip"]: le["hostname"] for le in snap["leases"] if le["hostname"]}
    domains = [r["domain"] for r in snap["dns"] if r["domain"]]
    domain = db.setting("dns_domain") or (max(set(domains), key=domains.count) if domains else "")
    missing = []
    for d in sorted(devs, key=lambda x: (x["name"] or "").lower()):
        ip = _ip(d["ip"])
        if not ip or d["type"] in NO_DNS or ip in covered:
            continue
        missing.append({"id": d["id"], "name": d["name"], "ip": ip, "suggest": slug(d["hostname"]) or slug(d["name"]), "dhcp_name": lease_name.get(ip, ""),
                        "mac": _mac(d["mac"]) or (arp.get(ip) or {}).get("mac", "") or (leases.get(ip) or {}).get("mac", "")})
    svc = snap["services"]
    dns_target = "unbound" if svc.get("unbound") == "running" else "dnsmasq" if svc.get("dnsmasq") == "running" else \
        "unbound" if any(r["src"] == "unbound" for r in snap["dns"]) else "dnsmasq" if any(r["src"] == "dnsmasq" for r in snap["dns"]) else None
    dhcp_target = "kea" if svc.get("kea") == "running" else "dnsmasq" if svc.get("dnsmasq") == "running" else None
    return {"source": {"id": integ["id"], "name": integ["name"] or "OPNsense", "status": integ["last_status"]} if integ else None,
            "fetched": snap.get("fetched"), "errors": snap["errors"], "services": svc, "write": _writable(integ),
            "dns_target": dns_target, "dhcp_target": dhcp_target, "domain": domain,
            "counts": {"dns": len(snap["dns"]), "reservations": len(snap["reservations"]), "leases": len(snap["leases"]), "arp": len(snap["arp"])},
            "subnets": subnets, "records": records, "missing": missing, "outside": sorted(outside.values(), key=lambda o: -o["count"])}


# ------------------------------------------------------------------ Schreiben
def _client():
    integ, snap = _source()
    if not integ:
        raise HTTPException(400, "Keine OPNsense-Anbindung eingerichtet")
    if not _writable(integ):
        raise HTTPException(403, "Änderungen sind in der OPNsense-Anbindung nicht erlaubt (Haken „Änderungen … erlauben“)")
    try:
        return integ, snap or {}, connectors.OpnClient(integ["config"])
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from None


def _check(r, what):
    if isinstance(r, dict) and r.get("result") in ("saved", "deleted", "ok"):
        return r
    val = (r or {}).get("validations") if isinstance(r, dict) else None
    detail = "; ".join(f"{k.split('.')[-1]}: {v}" for k, v in (val or {}).items()) or json.dumps(r)[:200]
    raise HTTPException(400, f"OPNsense hat {what} abgelehnt – {detail}")


def _do(fn, what):
    try:
        return fn()
    except urllib.error.HTTPError as e:
        raise HTTPException(502, connectors.explain(e, "OPNsense") + f" ({what})") from None
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, connectors.explain(e, "OPNsense") + f" ({what})") from None


def _hostname(h):
    h = (h or "").strip().lower()
    if not re.match(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", h):
        raise HTTPException(400, f"„{h}“ ist kein gültiger Hostname (a–z, 0–9, Bindestrich)")
    return h


def _refresh(integ, cli):
    try:
        st = fetch(integ, cli)
        db.x("UPDATE integrations SET last_sync=?, last_status=? WHERE id=?", (db.now(), "ok · " + st, integ["id"]))
    except Exception:  # noqa: BLE001 – die Änderung ist durch; der Stand kommt beim nächsten Abgleich
        pass
    return build()


@router.get("/api/ipam")
def ipam_view():
    return build()


@router.post("/api/ipam/refresh")
def ipam_refresh():
    integ, _ = _source()
    if not integ:
        raise HTTPException(400, "Keine OPNsense-Anbindung eingerichtet")
    status = connectors.sync(integ["id"])
    out = build()
    out["sync_status"] = status
    return out


@router.post("/api/ipam/dns")
def ipam_dns(data: dict = Body(...)):
    """op: add (items: [{hostname, domain, ip, description}]) · set (uuid, src, ip) · del (uuid, src)."""
    integ, snap, cli = _client()
    op = data.get("op")
    view = build()
    target = data.get("src") or view["dns_target"]
    if target not in ("unbound", "dnsmasq"):
        raise HTTPException(400, "Auf der OPNsense läuft weder Unbound noch Dnsmasq als DNS")
    touched = set()
    if op == "add":
        items = data.get("items") or []
        if not items:
            raise HTTPException(400, "Keine Einträge angegeben")
        for it in items:
            h, d, ip = _hostname(it.get("hostname")), (it.get("domain") or "").strip().lower(), _ip(it.get("ip"))
            if not ip:
                raise HTTPException(400, f"Ungültige IP-Adresse für {h}")
            if any(r["hostname"].lower() == h and r["domain"].lower() == d and r["src"] == target for r in snap.get("dns", [])):
                raise HTTPException(400, f"{h}.{d} gibt es schon – stattdessen die Adresse ändern")
            desc = (it.get("description") or "LabVis")[:255]
            body = {"host": {"enabled": "1", "hostname": h, "domain": d, "rr": "A", "server": ip, "description": desc}} if target == "unbound" else \
                {"host": {"host": h, "domain": d, "ip": ip, "descr": desc}}
            path = "/unbound/settings/add_host_override" if target == "unbound" else "/dnsmasq/settings/add_host"
            _check(_do(lambda: cli.call(path, body), "DNS-Eintrag anlegen"), f"den Eintrag {h}.{d}")
        touched.add(target)
    elif op in ("set", "del"):
        uuid = re.sub(r"[^0-9a-fA-F-]", "", data.get("uuid") or "")
        rec = next((r for r in snap.get("dns", []) if r["uuid"] == uuid), None)
        if not uuid or not rec:
            raise HTTPException(404, "Eintrag nicht gefunden – bitte neu einlesen")
        target = rec["src"]
        if op == "set":
            ip = _ip(data.get("ip"))
            if not ip:
                raise HTTPException(400, "Ungültige IP-Adresse")
            body = {"host": {"server": ip}} if target == "unbound" else {"host": {"ip": ip}}
            path = f"/unbound/settings/set_host_override/{uuid}" if target == "unbound" else f"/dnsmasq/settings/set_host/{uuid}"
        else:
            body, path = {}, (f"/unbound/settings/del_host_override/{uuid}" if target == "unbound" else f"/dnsmasq/settings/del_host/{uuid}")
        _check(_do(lambda: cli.call(path, body), "DNS-Eintrag ändern"), "die Änderung")
        touched.add(target)
    else:
        raise HTTPException(400, "Unbekannte Aktion")
    for svc in touched:
        _do(lambda svc=svc: cli.call(f"/{svc}/service/reconfigure", {}), "Dienst neu laden")
    return _refresh(integ, cli)


@router.post("/api/ipam/dhcp")
def ipam_dhcp(data: dict = Body(...)):
    """op: add (ip, mac, hostname, description) · del (uuid, src)."""
    integ, snap, cli = _client()
    op = data.get("op")
    if op == "add":
        ip, mac, h = _ip(data.get("ip")), _mac(data.get("mac")), _hostname(data.get("hostname"))
        if not ip or not mac:
            raise HTTPException(400, "Für eine Reservierung braucht es IP- und MAC-Adresse")
        if any(r["ip"] == ip for r in snap.get("reservations", [])):
            raise HTTPException(400, f"Für {ip} gibt es schon eine Reservierung")
        if any(r["mac"] == mac for r in snap.get("reservations", [])):
            raise HTTPException(400, f"Für {mac} gibt es schon eine Reservierung")
        target = build()["dhcp_target"]
        desc = (data.get("description") or "LabVis")[:255]
        if target == "kea":
            sub = next((s for s in snap.get("subnets", []) if s["subnet"] and ipaddress.IPv4Address(ip) in ipaddress.IPv4Network(s["subnet"], strict=False)), None)
            if not sub:
                raise HTTPException(400, f"Kea hat kein Subnetz, das {ip} enthält")
            body = {"reservation": {"subnet": sub["uuid"], "ip_address": ip, "hw_address": mac, "hostname": h, "description": desc}}
            path = "/kea/dhcpv4/add_reservation"
        elif target == "dnsmasq":
            body = {"host": {"host": h, "domain": (data.get("domain") or "").strip().lower(), "ip": ip, "hwaddr": mac, "descr": desc}}
            path = "/dnsmasq/settings/add_host"
        else:
            raise HTTPException(400, "Kein DHCP-Dienst mit API gefunden: Reservierungen lassen sich nur mit Kea oder Dnsmasq anlegen "
                                     "(ISC DHCP bietet dafür keine Schnittstelle)")
        _check(_do(lambda: cli.call(path, body), "Reservierung anlegen"), f"die Reservierung für {ip}")
    elif op == "del":
        uuid = re.sub(r"[^0-9a-fA-F-]", "", data.get("uuid") or "")
        rec = next((r for r in snap.get("reservations", []) if r["uuid"] and r["uuid"] == uuid), None)
        if not rec:
            raise HTTPException(404, "Reservierung nicht gefunden – bitte neu einlesen")
        target = rec["src"]
        path = f"/kea/dhcpv4/del_reservation/{uuid}" if target == "kea" else f"/dnsmasq/settings/del_host/{uuid}"
        _check(_do(lambda: cli.call(path, {}), "Reservierung löschen"), "das Löschen")
    else:
        raise HTTPException(400, "Unbekannte Aktion")
    _do(lambda: cli.call(f"/{target}/service/reconfigure", {}), "Dienst neu laden")
    return _refresh(integ, cli)

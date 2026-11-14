"""Import einer inventory.yaml im Format von Goblinmine/homelab-diagram."""
import ipaddress

import yaml

from . import db


def _ip(raw, subnet):
    """'.49' → mit dem Präfix des Subnetzes ergänzen; '10.0.10.30 / .31' → erste Adresse."""
    if not raw:
        return None
    raw = str(raw).split("/")[0].strip()
    if raw.startswith(".") and subnet:
        base = str(ipaddress.ip_network(subnet, strict=False).network_address).rsplit(".", 1)[0]
        return base + raw
    return raw


def import_inventory(text):
    inv = yaml.safe_load(text)
    if not isinstance(inv, dict) or "vlans" not in inv:
        raise ValueError("Keine inventory.yaml im homelab-diagram-Format")
    domain = inv.get("meta", {}).get("domain", "example.com")
    if inv.get("meta", {}).get("title"):
        db.x("INSERT OR REPLACE INTO settings(key,value) VALUES('title',?)", (inv["meta"]["title"],))
    vl, subnet = {}, {}
    for v in inv["vlans"]:
        key = str(v["key"])
        vl[key] = db.insert("vlans", {"vid": int(key) if key.isdigit() else None, "name": v["name"],
                                      "subnet": v.get("subnet"), "color": v.get("color"), "note": v.get("note")})
        subnet[key] = v.get("subnet")
    byname = {}

    def dev(d, typ, vlan=None, parent=None, **extra):
        icons = d.get("icons") or ([d["icon"]] if d.get("icon") else [])
        host = d.get("host")
        data = {"name": d["name"], "type": typ, "model": d.get("model"), "os": d.get("os"),
                "ip": _ip(d.get("ip"), subnet.get(str(vlan))), "vlan_id": vl.get(str(vlan)), "parent_id": parent,
                "icon": icons[0] if icons else None, "note": d.get("note"), "source": "import",
                "hostname": f"{host}.{domain}" if host else (f"{d['internal']}.internal" if d.get("internal") else None),
                "url": f"https://{host}.{domain}" if host else None,
                "meta": {k: d[k] for k in ("hw", "pools") if d.get(k)}}
        data["meta"] = {**data["meta"], **extra.pop("meta", {})}
        data.update(extra)
        i = db.insert("devices", data)
        byname[d["name"].lower()] = i
        return i

    net = db.insert("devices", {"name": "Internet", "type": "internet", "icon": "type-internet", "source": "import",
                                "note": " · ".join(f"{k} {v}" for k, v in inv.get("internet", {}).get("speed", {}).items())})
    fb = dev(inv["fritzbox"], "router", "wan", icon="fritzbox") if inv.get("fritzbox") else None
    ops = inv.get("opnsense")
    fw = None
    if ops:
        fw = dev(ops, "firewall", "99", icon="opnsense")
        for s in ops.get("services", []):
            dev(s, "service", None, fw)
    sw = inv.get("switch")
    swid = None
    if sw:
        ifaces = [{"idx": n + 1, "name": p["name"], "up": p.get("to") not in (None, "free"), "speed": "10G" if "sfp" in p["name"] else "1G",
                   "pvid": p.get("untagged"), "tagged": p.get("tagged", []), "neighbor": p.get("to")} for n, p in enumerate(sw["ports"])]
        swid = dev(sw, "switch", "99", icon="mikrotik", meta={"ifaces": ifaces})
    for d in inv.get("devices", {}).values():
        dev(d, {"workstation": "workstation", "access point": "ap", "coordinator": "iot"}.get(d.get("type"), "other"),
            d.get("vlan"))
    t = inv.get("terra")
    if t:
        tid = dev(t, "hypervisor", "10", icon="proxmox")
        for g in t.get("other_guests", {}).values():
            dev(g, "vm" if g.get("kind") == "VM" else "container", g.get("vlan"), tid)
        for grp in t.get("dmz_groups", []):
            for g in grp["guests"]:
                g = {**g, "ip": g.get("ip") or f".{g['id']}"}
                gid = dev(g, "container", "20", tid, meta={"group": grp["name"], "vmid": g["id"], "docker": g.get("docker")})
                for a in g.get("apps", []):
                    dev(a, "app", "20", gid, ip=None)
    # Kabel
    if fb:
        db.insert("links", {"a_id": net, "b_id": fb, "speed": "1G", "vlan_id": vl.get("wan"), "note": "Kabel"})
        if fw:
            db.insert("links", {"a_id": fb, "b_id": fw, "speed": "1G", "vlan_id": vl.get("wan"), "note": "exposed host"})
    if sw and swid:
        done = set()
        for p in sw["ports"]:
            other = byname.get(str(p.get("to", "")).lower())
            if not other or (other, p["name"][:3]) in done:
                continue
            done.add((other, p["name"][:3]))
            fast = "sfp" in p["name"]
            db.insert("links", {"a_id": swid, "b_id": other, "a_port": p["name"], "trunk": 1 if p.get("tagged") else 0,
                                "vlan_id": vl.get(str(p.get("untagged"))), "speed": "10G" if fast else ("2.5G" if other == fw else "1G"),
                                "note": "LACP" if other == fw else None})
    return {"vlans": len(vl), "devices": db.one("SELECT count(*) c FROM devices")["c"]}

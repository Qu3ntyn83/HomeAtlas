"""LabVis – interaktive Homelab-Dokumentation: Topologie, Racks, Netzwerke, Scanner, Anbindungen."""
import hashlib
import os
import re
import threading
import time
import urllib.request
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import auth, connectors, db, importer, monitor, scanner

STATIC = Path(__file__).parent / "static"
ICON_CACHE = db.DATA / "icons"
ICON_SOURCES = ["https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/{}.svg",
                "https://raw.githubusercontent.com/homarr-labs/dashboard-icons/main/svg/{}.svg"]
_icon_miss = {}
VERSION = "0.14.1"


def _build_id():
    """Kurzer Fingerabdruck des ausgelieferten Codes – ändert sich mit jedem Update und dient als Cache-Schlüssel."""
    h = hashlib.sha1()
    for f in sorted(Path(__file__).parent.rglob("*")):
        if f.is_file() and f.suffix in (".py", ".js", ".css", ".html"):
            h.update(f.read_bytes())
    return h.hexdigest()[:8]


BUILD = _build_id()


class FreshStatic(StaticFiles):
    """Skripte und Styles immer beim Server gegenprüfen lassen, damit nach einem Update nichts Altes im Browser hängt."""
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        if path.endswith((".js", ".css", ".html")):
            resp.headers["Cache-Control"] = "no-cache"
        return resp


def _page(name):
    html = (STATIC / name).read_text(encoding="utf-8")
    for asset in ("/static/style.css", "/static/app.js"):
        html = html.replace(asset, f"{asset}?v={BUILD}")
    return Response(html.replace("__VERSION__", f"{VERSION} · Build {BUILD}"), media_type="text/html",
                    headers={"Cache-Control": "no-store"})


TABLES = ("vlans", "racks", "devices", "links", "integrations", "wlans")
MASK = "••••••••"
SECRET_FIELDS = {f[0] for k in connectors.KINDS.values() for f in k["fields"] if len(f) > 3 and f[3] == "password"}

app = FastAPI(title="LabVis", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.middleware("http")(auth.middleware)
app.include_router(auth.router)
app.include_router(monitor.router)


def _scheduler():
    while True:
        time.sleep(30)
        try:
            connectors.due_syncs()
            scanner.due_scans()
        except Exception as e:  # noqa: BLE001
            print("scheduler:", e, flush=True)


@app.on_event("startup")
def startup():
    db.init()
    auth.bootstrap()
    monitor.init()
    ICON_CACHE.mkdir(parents=True, exist_ok=True)
    if not os.environ.get("LABVIS_NO_SCHEDULER"):
        threading.Thread(target=_scheduler, daemon=True).start()
        monitor.start()


def _mask(i):
    i = dict(i)
    i["config"] = {k: (MASK if k in SECRET_FIELDS and v else v) for k, v in (i.get("config") or {}).items()}
    return i


@app.get("/api/state")
def state(request: Request):
    return {
        "version": VERSION,
        "build": BUILD,
        "user": request.state.user["username"],
        "role": request.state.user["role"],
        "settings": {k: v for k, v in db.settings().items() if k != "notify_url" or request.state.user["role"] == "admin"},
        "vlans": db.q("SELECT * FROM vlans ORDER BY vid IS NULL, vid, id"),
        "racks": db.q("SELECT * FROM racks ORDER BY id"),
        "devices": db.q("SELECT * FROM devices ORDER BY id"),
        "links": db.q("SELECT * FROM links ORDER BY id"),
        "wlans": db.q("SELECT * FROM wlans ORDER BY ssid COLLATE NOCASE"),
        "checks": monitor.light(),
        "discoveries": db.q("SELECT * FROM discoveries ORDER BY state='ignored', last_seen DESC"),
        "integrations": [_mask(i) for i in db.q("SELECT * FROM integrations ORDER BY id")],
        "scans": db.q("SELECT * FROM scans ORDER BY id DESC LIMIT 15"),
        "scanner": {**scanner.STATE, "privileged": scanner.privileged()},
        "kinds": connectors.KINDS,
        "now": db.now(),
    }


def _clean(table, data):
    data = {k: (None if v == "" else v) for k, v in data.items() if k in db.COLUMNS[table]}
    for k in ("vid", "units", "vlan_id", "parent_id", "rack_id", "rack_u", "rack_height", "a_id", "b_id", "device_id", "wlan_id"):
        if data.get(k) is not None:
            data[k] = int(data[k])
    return data


@app.post("/api/{table}")
def create(table: str, data: dict = Body(...)):
    if table not in TABLES:
        raise HTTPException(404)
    data = _clean(table, data)
    if table == "integrations":
        key = lambda c: ((c.get("host") or c.get("url") or "").strip().lower(), str(c.get("port") or ""))   # noqa: E731
        if key(data.get("config") or {})[0] and any(i["kind"] == data.get("kind") and key(i["config"] or {}) == key(data["config"])
                                                 for i in db.q("SELECT kind, config FROM integrations")):
            raise HTTPException(400, "Für diese Adresse gibt es schon eine Anbindung dieser Art")
    if table == "links" and data.get("a_id") == data.get("b_id"):
        raise HTTPException(400, "Ein Gerät kann nicht mit sich selbst verbunden werden")
    return {"id": db.insert(table, data)}


@app.put("/api/{table}/{rid}")
def change(table: str, rid: int, data: dict = Body(...)):
    if table not in TABLES:
        raise HTTPException(404)
    data = _clean(table, data)
    if table == "integrations" and "config" in data:
        old = (db.one("SELECT config FROM integrations WHERE id=?", (rid,)) or {}).get("config", {})
        data["config"] = {k: (old.get(k) if v == MASK else v) for k, v in data["config"].items()}
        data["config"].update({k: v for k, v in old.items() if k.startswith("_") and k not in data["config"]})
    if table == "devices" and data.get("parent_id"):
        cur, hops = data["parent_id"], 0
        while cur and hops < 20:
            if cur == rid:
                raise HTTPException(400, "Ein Gerät kann nicht in sich selbst liegen")
            cur = (db.one("SELECT parent_id FROM devices WHERE id=?", (cur,)) or {}).get("parent_id")
            hops += 1
    if table == "devices" and "meta" in data:
        old = (db.one("SELECT meta FROM devices WHERE id=?", (rid,)) or {}).get("meta", {})
        data["meta"] = {**old, **(data["meta"] or {})}
    db.update(table, rid, data)
    return {"ok": True}


@app.delete("/api/{table}/{rid}")
def remove(table: str, rid: int):
    if table == "devices":
        db.delete_device(rid)
    elif table == "vlans":
        db.x("UPDATE devices SET vlan_id=NULL WHERE vlan_id=?", (rid,))
        db.x("UPDATE links SET vlan_id=NULL WHERE vlan_id=?", (rid,))
        db.x("UPDATE wlans SET vlan_id=NULL WHERE vlan_id=?", (rid,))
        db.x("DELETE FROM discoveries WHERE vlan_id=?", (rid,))
        db.x("DELETE FROM vlans WHERE id=?", (rid,))
    elif table == "wlans":
        db.x("UPDATE links SET wlan_id=NULL WHERE wlan_id=?", (rid,))
        db.x("DELETE FROM wlans WHERE id=?", (rid,))
    elif table == "racks":
        db.x("UPDATE devices SET rack_id=NULL, rack_u=NULL WHERE rack_id=?", (rid,))
        db.x("DELETE FROM racks WHERE id=?", (rid,))
    elif table == "integrations":
        db.x("UPDATE devices SET integration_id=NULL, ext_id=NULL WHERE integration_id=?", (rid,))
        db.x("DELETE FROM integrations WHERE id=?", (rid,))
    elif table in ("links", "discoveries"):
        db.x(f"DELETE FROM {table} WHERE id=?", (rid,))
    else:
        raise HTTPException(404)
    return {"ok": True}


@app.post("/api/positions/save")
def positions(items: list = Body(...)):
    for i in items:
        db.x("UPDATE devices SET x=?, y=? WHERE id=?", (float(i["x"]), float(i["y"]), int(i["id"])))
    return {"ok": True}


@app.post("/api/settings/save")
def save_settings(data: dict = Body(...)):
    for k, v in data.items():
        if k in db.DEFAULTS:
            db.x("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, str(v)))
    return {"ok": True}


# ---------------------------------------------------------------- Scanner
@app.post("/api/vlans/{vid}/scan")
def scan(vid: int):
    if scanner.STATE["running"]:
        raise HTTPException(409, "Es läuft bereits ein Scan")
    scanner.scan_async(vid)
    return {"ok": True}


def _approve(d):
    g = d["guess"] or {}
    name = scanner.clean_name(d.get("hostname")).split(".")[0] or d["ip"]
    return db.insert("devices", {
        "name": name, "type": g.get("type") or "other", "icon": g.get("icon"), "os": g.get("os"),
        "model": g.get("model"), "url": g.get("url"), "ip": d["ip"], "mac": d.get("mac"), "vendor": d.get("vendor"),
        "hostname": d.get("hostname"), "vlan_id": d.get("vlan_id"), "ports": d.get("ports") or [],
        "status": "online", "last_seen": d.get("last_seen"), "source": "scan",
        "meta": {"suggestions": g.get("suggestions", []), "http": d.get("http") or {}}})


@app.post("/api/discoveries/{did}/{action}")
def discovery(did: str, action: str):
    rows = db.q("SELECT * FROM discoveries WHERE state='pending'") if did == "all" else \
        db.q("SELECT * FROM discoveries WHERE id=?", (int(did),))
    ids = []
    for d in rows:
        if action == "approve":
            ids.append(_approve(d))
            db.x("DELETE FROM discoveries WHERE id=?", (d["id"],))
        elif action == "ignore":
            db.x("UPDATE discoveries SET state='ignored' WHERE id=?", (d["id"],))
        elif action == "restore":
            db.x("UPDATE discoveries SET state='pending' WHERE id=?", (d["id"],))
        else:
            raise HTTPException(400)
    return {"ids": ids}


# ---------------------------------------------------------------- Mehrere Adressen / Zusammenführen
def _dev(did):
    d = db.one("SELECT * FROM devices WHERE id=?", (did,))
    if not d:
        raise HTTPException(404, "Gerät nicht gefunden")
    return d


def _add_addr(dev, addr):
    """Hängt eine weitere Adresse (NIC) an ein Gerät. Hat es noch keine Hauptadresse, wird sie zur Hauptadresse."""
    addr = {k: v for k, v in addr.items() if v not in (None, "")}
    if addr.get("mac"):
        addr["mac"] = addr["mac"].upper()
    if not addr.get("ip") and not addr.get("mac"):
        return
    if addr.get("ip") and not addr.get("vlan_id"):
        addr["vlan_id"] = connectors.vlan_for_ip(addr["ip"])
    meta = dev["meta"] or {}
    known = [(dev.get("ip"), dev.get("mac"))] + [(a.get("ip"), a.get("mac")) for a in meta.get("addrs") or []]
    if any((addr.get("ip") and addr.get("ip") == i) or (addr.get("mac") and addr.get("mac") == m) for i, m in known):
        raise HTTPException(400, "Diese Adresse hat das Gerät schon")
    if not dev.get("ip") and not dev.get("mac"):
        upd = {k: addr.get(k) for k in ("ip", "mac", "vendor", "hostname", "vlan_id") if addr.get(k) and not dev.get(k)}
        db.update("devices", dev["id"], upd)
        dev.update(upd)
        return
    meta.setdefault("addrs", []).append(addr)
    db.update("devices", dev["id"], {"meta": meta})
    dev["meta"] = meta


@app.post("/api/devices/{did}/addrs")
def add_addr(did: int, data: dict = Body(...)):
    if not data.get("ip") and not data.get("mac"):
        raise HTTPException(400, "IP oder MAC angeben")
    _add_addr(_dev(did), {k: data.get(k) for k in ("ip", "mac", "label", "note")} |
              {"vlan_id": int(data["vlan_id"]) if data.get("vlan_id") else None})
    return {"ok": True}


def _addr(dev, idx):
    addrs = (dev["meta"] or {}).get("addrs") or []
    if not 0 <= idx < len(addrs):
        raise HTTPException(404, "Adresse nicht gefunden")
    return addrs[idx]


@app.put("/api/devices/{did}/addrs/{idx}")
def edit_addr(did: int, idx: int, data: dict = Body(...)):
    """Bezeichnung, Notiz, IP, MAC und Netzwerk einer weiteren Adresse ändern."""
    dev = _dev(did)
    a = _addr(dev, idx)
    for k in ("label", "note", "ip", "mac"):
        if k in data:
            v = (data[k] or "").strip()
            a[k] = v.upper() if k == "mac" else v
            if not a[k]:
                a.pop(k)
    if "vlan_id" in data:
        a["vlan_id"] = int(data["vlan_id"]) if data["vlan_id"] else (connectors.vlan_for_ip(a.get("ip")) if a.get("ip") else None)
    if not a.get("ip") and not a.get("mac"):
        raise HTTPException(400, "IP oder MAC angeben")
    db.update("devices", did, {"meta": dev["meta"]})
    return {"ok": True}


@app.post("/api/devices/{did}/addrs/{idx}/primary")
def make_primary(did: int, idx: int):
    """Tauscht eine weitere Adresse mit der Hauptadresse. Bezeichnung und Notiz wandern jeweils mit."""
    dev = _dev(did)
    meta = dev["meta"] or {}
    a = _addr(dev, idx)
    old = {"ip": dev.get("ip"), "mac": dev.get("mac"), "vendor": dev.get("vendor"), "vlan_id": dev.get("vlan_id"),
           "label": meta.get("primary_label"), "note": meta.get("primary_note"),
           "up": meta.get("up0", dev["status"] == "online" if dev["status"] != "unknown" else None),
           "last_seen": dev.get("last_seen")}
    upd = {"ip": a.get("ip"), "mac": a.get("mac"), "vendor": a.get("vendor") or dev.get("vendor"),
           "vlan_id": a.get("vlan_id") or (connectors.vlan_for_ip(a.get("ip")) if a.get("ip") else dev.get("vlan_id"))}
    if a.get("hostname"):                         # der Hostname gehört zur Adresse und tauscht mit
        old["hostname"] = dev.get("hostname")
        upd["hostname"] = a["hostname"]
    meta["primary_label"], meta["primary_note"] = a.get("label"), a.get("note")
    if a.get("up") is not None:
        meta["up0"] = bool(a["up"])
    else:
        meta.pop("up0", None)
    old = {k: v for k, v in old.items() if v not in (None, "")}
    if old.get("ip") or old.get("mac"):
        meta["addrs"][idx] = old
    else:
        meta["addrs"].pop(idx)
    upd["meta"] = {k: v for k, v in meta.items() if v is not None}
    with db.conn() as c:                          # ip/mac dürfen dabei auch leer werden, deshalb direkt statt über update()
        c.execute("UPDATE devices SET ip=?, mac=?, vendor=?, vlan_id=?, hostname=?, meta=? WHERE id=?",
                  (upd["ip"], upd["mac"], upd["vendor"], upd["vlan_id"], upd.get("hostname", dev.get("hostname")),
                   db._enc(upd["meta"]), did))
    return {"ok": True}


@app.delete("/api/devices/{did}/addrs/{idx}")
def del_addr(did: int, idx: int):
    dev = _dev(did)
    meta = dev["meta"] or {}
    if not 0 <= idx < len(meta.get("addrs") or []):
        raise HTTPException(404, "Adresse nicht gefunden")
    meta["addrs"].pop(idx)
    db.update("devices", did, {"meta": meta})
    return {"ok": True}


@app.post("/api/devices/{did}/attach/{disc}")
def attach(did: int, disc: int):
    """Einen Fund als weitere Adresse an ein vorhandenes Gerät hängen."""
    dev = _dev(did)
    d = db.one("SELECT * FROM discoveries WHERE id=?", (disc,))
    if not d:
        raise HTTPException(404, "Fund nicht gefunden")
    _add_addr(dev, {"ip": d["ip"], "mac": d.get("mac"), "vendor": d.get("vendor"), "hostname": d.get("hostname"),
                    "vlan_id": d.get("vlan_id"), "up": True, "last_seen": d.get("last_seen")})
    dev = _dev(did)
    meta = dev["meta"] or {}
    meta["suggestions"] = scanner._merge_sug(meta.get("suggestions") or [], (d["guess"] or {}).get("suggestions", []))
    db.update("devices", did, {"meta": meta, "ports": sorted(set(dev.get("ports") or []) | set(d.get("ports") or [])),
                               "status": "online", "last_seen": d.get("last_seen")})
    db.x("DELETE FROM discoveries WHERE id=?", (disc,))
    return {"ok": True}


@app.post("/api/devices/{did}/merge")
def merge(did: int, data: dict = Body(...)):
    """Führt ein zweites Gerät in dieses über: Adressen, Kabel, Kinder und Anbindungen wandern mit."""
    oid = int(data.get("other_id") or 0)
    if oid == did:
        raise HTTPException(400, "Zwei verschiedene Geräte wählen")
    t, o = _dev(did), _dev(oid)
    for start, other in ((t, oid), (o, did)):          # keines darf im anderen enthalten sein
        cur, hops = start.get("parent_id"), 0
        while cur and hops < 20:
            if cur == other:
                raise HTTPException(400, "Ein Gerät lässt sich nicht mit seinem Host oder Gast zusammenführen")
            cur = (db.one("SELECT parent_id FROM devices WHERE id=?", (cur,)) or {}).get("parent_id")
            hops += 1
    om = o["meta"] or {}
    if o.get("ip") or o.get("mac"):
        _add_addr(t, {"ip": o.get("ip"), "mac": o.get("mac"), "vendor": o.get("vendor"), "hostname": o.get("hostname"),
                      "vlan_id": o.get("vlan_id"), "label": o["name"], "up": o["status"] == "online",
                      "last_seen": o.get("last_seen")})
    for a in om.get("addrs") or []:
        try:
            _add_addr(t, a)
        except HTTPException:
            pass
    t = _dev(did)
    meta = t["meta"] or {}
    meta["suggestions"] = scanner._merge_sug(meta.get("suggestions") or [], om.get("suggestions") or [])
    for k in ("hw", "pools", "ifaces", "http"):
        if om.get(k) and not meta.get(k):
            meta[k] = om[k]
    upd = {k: o[k] for k in ("model", "os", "vendor", "hostname", "url", "icon", "note", "vlan_id", "rack_id", "rack_u",
                             "integration_id", "ext_id") if o.get(k) and not t.get(k)}
    if "rack_id" in upd:
        upd["rack_height"] = o.get("rack_height") or 1
    if "integration_id" not in upd:
        upd.pop("ext_id", None)
    upd.update(meta=meta, ports=sorted(set(t.get("ports") or []) | set(o.get("ports") or [])))
    if o["status"] == "online":
        upd.update(status="online", last_seen=max(t.get("last_seen") or 0, o.get("last_seen") or 0))
    db.update("devices", did, upd)
    db.x("UPDATE links SET a_id=? WHERE a_id=?", (did, oid))
    db.x("UPDATE links SET b_id=? WHERE b_id=?", (did, oid))
    db.x("DELETE FROM links WHERE a_id=b_id")
    db.x("UPDATE devices SET parent_id=? WHERE parent_id=?", (did, oid))
    db.x("UPDATE integrations SET device_id=? WHERE device_id=?", (did, oid))
    db.x("DELETE FROM devices WHERE id=?", (oid,))
    return {"ok": True}


# ---------------------------------------------------------------- Anbindungen
@app.post("/api/integrations/{iid}/sync")
def sync(iid: int):
    return {"status": connectors.sync(iid)}


# ---------------------------------------------------------------- Import / Export
@app.post("/api/import/inventory")
async def import_inventory(request: Request):
    try:
        return importer.import_inventory((await request.body()).decode())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e)) from e


@app.get("/api/export")
def export():
    data = {t: db.q(f"SELECT * FROM {t}") for t in TABLES}
    data["settings"] = db.settings()
    data["checks"] = db.q("SELECT id, " + ", ".join(monitor.FIELDS) + ", source FROM checks")
    return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="labvis-export.json"'})


@app.post("/api/restore/all")
def restore(data: dict = Body(...)):
    if not all(t in data for t in TABLES if t != "wlans"):   # ältere Exporte kennen noch keine WLANs
        raise HTTPException(400, "Kein LabVis-Export")
    with db.conn() as c:
        for t in TABLES:
            c.execute(f"DELETE FROM {t}")
            for row in data.get(t, []):
                cols = [k for k in row if k == "id" or k in db.COLUMNS[t]]
                c.execute(f"INSERT INTO {t}({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                          [db._enc(row[k]) for k in cols])
        c.execute("DELETE FROM discoveries")
        for t in ("checks", "check_results", "check_hours", "check_events"):     # Verlauf gehört zur alten Installation
            c.execute(f"DELETE FROM {t}")
        for row in data.get("checks", []):
            cols = [k for k in row if k in ("id", "source", *monitor.FIELDS)]
            c.execute(f"INSERT INTO checks({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [row[k] for k in cols])
    save_settings(data.get("settings", {}))
    return {"ok": True}


# ---------------------------------------------------------------- Icons
@app.get("/api/icon/{name}")
def icon(name: str):
    name = re.sub(r"[^a-z0-9-]", "", name.lower())[:60] or "type-other"
    hdr = {"Cache-Control": "public, max-age=86400", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"}
    for f in (STATIC / "icons" / f"{name}.svg", ICON_CACHE / f"{name}.svg"):
        if f.exists():
            return FileResponse(f, media_type="image/svg+xml", headers=hdr)
    if time.time() - _icon_miss.get(name, 0) > 6 * 3600:
        for src in ICON_SOURCES:
            try:
                req = urllib.request.Request(src.format(name), headers={"User-Agent": "LabVis"})
                body = urllib.request.urlopen(req, timeout=6).read()
                if b"<svg" in body[:2000]:
                    (ICON_CACHE / f"{name}.svg").write_bytes(body)
                    return Response(body, media_type="image/svg+xml", headers=hdr)
            except Exception:
                continue
        _icon_miss[name] = time.time()
    return FileResponse(STATIC / "icons" / "type-other.svg", media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=600"})


@app.get("/login")
def login_page(request: Request):
    return auth.login_page(request, _page)


@app.get("/healthz")
def healthz():
    return {"ok": True, "version": VERSION, "build": BUILD}


@app.get("/")
def index():
    return _page("index.html")


app.mount("/static", FreshStatic(directory=STATIC), name="static")

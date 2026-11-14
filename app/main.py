"""LabVis – interaktive Homelab-Dokumentation: Topologie, Racks, Netzwerke, Scanner, Anbindungen."""
import os
import re
import threading
import time
import urllib.request
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import auth, connectors, db, importer, scanner

STATIC = Path(__file__).parent / "static"
ICON_CACHE = db.DATA / "icons"
ICON_SOURCES = ["https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/{}.svg",
                "https://raw.githubusercontent.com/homarr-labs/dashboard-icons/main/svg/{}.svg"]
_icon_miss = {}
TABLES = ("vlans", "racks", "devices", "links", "integrations")
MASK = "••••••••"
SECRET_FIELDS = {f[0] for k in connectors.KINDS.values() for f in k["fields"] if len(f) > 3 and f[3] == "password"}

app = FastAPI(title="LabVis", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.middleware("http")(auth.middleware)
app.include_router(auth.router)


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
    ICON_CACHE.mkdir(parents=True, exist_ok=True)
    if not os.environ.get("LABVIS_NO_SCHEDULER"):
        threading.Thread(target=_scheduler, daemon=True).start()


def _mask(i):
    i = dict(i)
    i["config"] = {k: (MASK if k in SECRET_FIELDS and v else v) for k, v in (i.get("config") or {}).items()}
    return i


@app.get("/api/state")
def state(request: Request):
    return {
        "user": request.state.user["username"],
        "role": request.state.user["role"],
        "settings": db.settings(),
        "vlans": db.q("SELECT * FROM vlans ORDER BY vid IS NULL, vid, id"),
        "racks": db.q("SELECT * FROM racks ORDER BY id"),
        "devices": db.q("SELECT * FROM devices ORDER BY id"),
        "links": db.q("SELECT * FROM links ORDER BY id"),
        "discoveries": db.q("SELECT * FROM discoveries ORDER BY state='ignored', last_seen DESC"),
        "integrations": [_mask(i) for i in db.q("SELECT * FROM integrations ORDER BY id")],
        "scans": db.q("SELECT * FROM scans ORDER BY id DESC LIMIT 15"),
        "scanner": {**scanner.STATE, "privileged": scanner.privileged()},
        "kinds": connectors.KINDS,
        "now": db.now(),
    }


def _clean(table, data):
    data = {k: (None if v == "" else v) for k, v in data.items() if k in db.COLUMNS[table]}
    for k in ("vid", "units", "vlan_id", "parent_id", "rack_id", "rack_u", "rack_height", "a_id", "b_id", "device_id"):
        if data.get(k) is not None:
            data[k] = int(data[k])
    return data


@app.post("/api/{table}")
def create(table: str, data: dict = Body(...)):
    if table not in TABLES:
        raise HTTPException(404)
    data = _clean(table, data)
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
        db.x("DELETE FROM discoveries WHERE vlan_id=?", (rid,))
        db.x("DELETE FROM vlans WHERE id=?", (rid,))
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
    name = (d.get("hostname") or "").split(".")[0] or d["ip"]
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
    return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="labvis-export.json"'})


@app.post("/api/restore/all")
def restore(data: dict = Body(...)):
    if not all(t in data for t in TABLES):
        raise HTTPException(400, "Kein LabVis-Export")
    with db.conn() as c:
        for t in TABLES:
            c.execute(f"DELETE FROM {t}")
            for row in data[t]:
                cols = [k for k in row if k == "id" or k in db.COLUMNS[t]]
                c.execute(f"INSERT INTO {t}({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                          [db._enc(row[k]) for k in cols])
        c.execute("DELETE FROM discoveries")
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
    return auth.login_page(request, STATIC)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")

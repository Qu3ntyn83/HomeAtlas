"""Gerätetypen und eigene Icons.

Die eingebauten Typen stehen hier; Anpassungen (Bezeichnung, Icon, Bereich, Erkennung, ausblenden) und eigene Typen liegen in der
Tabelle types. Ein eigener Typ verhält sich wie ein eingebauter (base) – das bestimmt z. B., ob er ins Rack passt oder als Client gilt.
Hochgeladene Icons liegen unter DATA/uploads/icons und heißen in HomeAtlas „up-<name>“.
"""
import base64
import json
import re
import time

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response

from . import db

router = APIRouter()
UPLOADS = db.DATA / "uploads" / "icons"
AREAS = {"network": "Netzwerk", "servers": "Server", "storage": "Speicher", "apps": "Dienste", "smarthome": "Smarthome",
         "clients": "Endgeräte", "other": "Sonstiges"}
# key, Bezeichnung, Bereich, Erkennung (Hersteller enthält / Hostname enthält)
BUILTIN = [
    ("internet", "Internet", "network"), ("router", "Router", "network"), ("firewall", "Firewall", "network"), ("switch", "Switch", "network"),
    ("ap", "Access Point", "network"), ("hypervisor", "Hypervisor", "servers"), ("server", "Server", "servers"), ("nas", "NAS", "storage"),
    ("workstation", "Workstation", "servers"), ("client", "Client", "clients"), ("smartphone", "Smartphone", "clients"),
    ("tablet", "Tablet", "clients"), ("iot", "IoT", "smarthome"), ("printer", "Drucker", "other"), ("vm", "VM", "servers"),
    ("container", "Container", "apps"), ("app", "App", "apps"), ("service", "Dienst", "apps"), ("other", "Gerät", "other"),
    ("light", "Lampe", "smarthome"), ("plug", "Steckdose", "smarthome"), ("sensor", "Sensor", "smarthome"),
    ("thermostat", "Thermostat", "smarthome"), ("blind", "Rollladen", "smarthome"), ("lock", "Türschloss", "smarthome"),
    ("vacuum", "Saugroboter", "smarthome"), ("camera", "Kamera", "smarthome"), ("speaker", "Lautsprecher", "smarthome"),
    ("tv", "TV / Medien", "smarthome"), ("group", "Bereich", "other"), ("patchpanel", "Patchpanel", "other"),
    ("shelf", "Rackboden", "other"), ("blank", "Blende", "other"), ("cablemgmt", "Kabelführung", "other")]
RULES = {"smartphone": {"hostname": ["iphone", "android", "galaxy-s", "pixel-", "redmi", "oneplus"], "vendor": []},
         "tablet": {"hostname": ["ipad", "galaxy-tab", "tab-s", "fire-tablet"], "vendor": []}}
# Typen mit Sonderrolle: als Vorlage für eigene Typen nicht wählbar
SPECIAL = {"internet", "group", "patchpanel", "shelf", "blank", "cablemgmt", "app", "service", "container", "vm"}
_cache = {"t": 0, "v": None}


def _norm_rules(r):
    r = r if isinstance(r, dict) else {}
    out = {}
    for k in ("vendor", "hostname"):
        v = r.get(k) or []
        if isinstance(v, str):
            v = v.split(",")
        out[k] = [x.strip().lower() for x in v if x and x.strip()][:30]
    return out


def all_types():
    if _cache["v"] is not None and time.time() - _cache["t"] < 5:
        return _cache["v"]
    rows = {r["key"]: r for r in db.q("SELECT * FROM types")}
    out = []
    for n, (k, label, area) in enumerate(BUILTIN):
        r = rows.pop(k, None) or {}
        out.append({"key": k, "label": r.get("label") or label, "icon": r.get("icon") or "", "area": r.get("area") or area, "base": k,
                    "rules": _norm_rules(r.get("rules") if r.get("rules") is not None else RULES.get(k)), "hidden": bool(r.get("hidden")),
                    "custom": False, "changed": bool(r), "default_label": label, "sort": n, "special": k in SPECIAL})
    for k, r in rows.items():
        out.append({"key": k, "label": r.get("label") or k, "icon": r.get("icon") or "", "area": r.get("area") or "other", "base": r.get("base") or "other",
                    "rules": _norm_rules(r.get("rules")), "hidden": bool(r.get("hidden")), "custom": True, "changed": True, "sort": 1000 + (r.get("sort") or 0),
                    "special": False})
    _cache.update(t=time.time(), v=out)
    return out


def _forget():
    _cache.update(t=0, v=None)


def get(key):
    return next((t for t in all_types() if t["key"] == key), None)


def base(key):
    t = get(key)
    return t["base"] if t else key


def area(key):
    t = get(key)
    return t["area"] if t else "other"


def detect(h):
    """Typ aus den Erkennungsregeln (eigene Typen zuerst): Hersteller oder Hostname enthält eines der Stichwörter."""
    vendor, host = (h.get("vendor") or "").lower(), (h.get("hostname") or "").lower()
    for t in sorted(all_types(), key=lambda x: not x["custom"]):
        r = t["rules"]
        if (vendor and any(w in vendor for w in r["vendor"])) or (host and any(w in host for w in r["hostname"])):
            return t["key"]
    return None


def _slug(s, n=40):
    s = (s or "").strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:n]


def _clean(data, custom):
    out = {}
    if "label" in data:
        out["label"] = (data.get("label") or "").strip()[:40]
        if not out["label"]:
            raise HTTPException(400, "Bezeichnung fehlt")
    if "icon" in data:
        out["icon"] = re.sub(r"[^a-z0-9-]", "", (data.get("icon") or "").lower())[:60]
    if "area" in data:
        if data["area"] not in AREAS:
            raise HTTPException(400, "Unbekannter Bereich")
        out["area"] = data["area"]
    if "rules" in data:
        out["rules"] = _norm_rules(data["rules"])
    if "hidden" in data:
        out["hidden"] = 1 if data["hidden"] in (1, True, "1", "on") else 0
    if custom and "base" in data:
        if data["base"] not in {k for k, *_ in BUILTIN} - SPECIAL:
            raise HTTPException(400, "Als Vorlage nur ein normaler Gerätetyp")
        out["base"] = data["base"]
    return out


def _save(key, vals):
    row = db.one("SELECT * FROM types WHERE key=?", (key,))
    cols = {k: (json.dumps(v) if k == "rules" else v) for k, v in vals.items()}
    if row:
        if cols:
            db.x(f"UPDATE types SET {', '.join(k + '=?' for k in cols)} WHERE key=?", (*cols.values(), key))
    else:
        cols["key"] = key
        db.x(f"INSERT INTO types({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})", tuple(cols.values()))
    _forget()


@router.get("/api/types")
def list_types():
    used = {r["type"]: r["n"] for r in db.q("SELECT type, COUNT(*) AS n FROM devices GROUP BY type")}
    return {"types": [{**t, "used": used.get(t["key"], 0)} for t in all_types()], "areas": AREAS, "icons": list_icons()}


@router.post("/api/types")
def add_type(data: dict = Body(...)):
    vals = _clean({**data, "label": data.get("label")}, True)
    key = _slug(data.get("key") or vals["label"], 24)
    if not key:
        raise HTTPException(400, "Bezeichnung braucht Buchstaben oder Ziffern")
    if get(key) or key in {k for k, *_ in BUILTIN}:
        key = f"{key}-{int(time.time()) % 10000}"
    vals.setdefault("base", "other")
    vals.setdefault("area", area(vals["base"]))
    _save(key, vals)
    return {"key": key}


@router.put("/api/types/{key}")
def edit_type(key: str, data: dict = Body(...)):
    t = get(key)
    if not t:
        raise HTTPException(404, "Typ nicht gefunden")
    _save(key, _clean(data, t["custom"]))
    return {"ok": True}


@router.delete("/api/types/{key}")
def del_type(key: str, move_to: str = ""):
    """Eingebaute Typen: Anpassungen zurücksetzen. Eigene: löschen; Geräte dieses Typs bekommen move_to oder die Vorlage."""
    t = get(key)
    if not t:
        raise HTTPException(404, "Typ nicht gefunden")
    if t["custom"]:
        target = move_to if move_to and get(move_to) and move_to != key else t["base"]
        db.x("UPDATE devices SET type=? WHERE type=?", (target, key))
    db.x("DELETE FROM types WHERE key=?", (key,))
    _forget()
    return {"ok": True}


# ------------------------------------------------------------------ eigene Icons
MAX_ICON = 512 * 1024
KINDS = {"svg": "image/svg+xml", "png": "image/png", "webp": "image/webp", "jpg": "image/jpeg"}


def _clean_svg(raw):
    """Nur Zeichnung, kein Code: Skripte, Ereignis-Attribute, eingebettete Fremdinhalte und externe Verweise fliegen raus."""
    s = raw.decode("utf-8", errors="replace")
    if "<svg" not in s[:4000].lower():
        raise HTTPException(400, "Keine SVG-Datei")
    s = re.sub(r"<\?xml[^>]*\?>|<!DOCTYPE[^>]*>|<!--.*?-->", "", s, flags=re.S | re.I)
    s = re.sub(r"<(script|foreignObject|iframe|object|embed|audio|video|handler|listener)\b.*?(</\1\s*>|/>)", "", s, flags=re.S | re.I)
    s = re.sub(r"<(script|foreignObject|iframe|object|embed)\b[^>]*>", "", s, flags=re.I)
    s = re.sub(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", s, flags=re.I)
    s = re.sub(r"\s+(xlink:)?href\s*=\s*(\"(?!#|data:image/)[^\"]*\"|'(?!#|data:image/)[^']*')", "", s, flags=re.I)
    s = re.sub(r"javascript:|@import|expression\(", "", s, flags=re.I)
    if not re.search(r"\bviewBox=", s[:2000]) and re.search(r"<svg[^>]*\bwidth=\"(\d+)", s):
        w, h = re.search(r"<svg[^>]*\bwidth=\"(\d+)", s).group(1), (re.search(r"<svg[^>]*\bheight=\"(\d+)", s) or re.search(r"(\d+)", "24")).group(1)
        s = re.sub(r"<svg\b", f'<svg viewBox="0 0 {w} {h}"', s, count=1)
    return s.strip().encode()


def list_icons():
    if not UPLOADS.exists():
        return []
    used = {}
    for r in db.q("SELECT icon, COUNT(*) AS n FROM devices WHERE icon LIKE 'up-%' GROUP BY icon"):
        used[r["icon"]] = r["n"]
    for t in all_types():
        if t["icon"].startswith("up-"):
            used[t["icon"]] = used.get(t["icon"], 0) + 1
    out = []
    for f in sorted(UPLOADS.iterdir()):
        if f.suffix[1:] in KINDS:
            name = "up-" + f.stem
            st = f.stat()
            out.append({"name": name, "label": f.stem.replace("-", " "), "kind": f.suffix[1:], "size": st.st_size, "v": int(st.st_mtime), "used": used.get(name, 0)})
    return out


def icon_file(name):
    if not name.startswith("up-"):
        return None
    stem = name[3:]
    for ext in KINDS:
        f = UPLOADS / f"{stem}.{ext}"
        if f.exists():
            return f, KINDS[ext]
    return None


@router.post("/api/icons")
def upload_icon(data: dict = Body(...)):
    name = _slug(data.get("name"), 40)
    if not name:
        raise HTTPException(400, "Name fehlt")
    try:
        raw = base64.b64decode((data.get("data") or "").split(",")[-1], validate=True)
    except ValueError:
        raise HTTPException(400, "Datei konnte nicht gelesen werden") from None
    if not raw or len(raw) > MAX_ICON:
        raise HTTPException(400, f"Datei leer oder größer als {MAX_ICON // 1024} KB")
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        kind = "png"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        kind = "webp"
    elif raw[:3] == b"\xff\xd8\xff":
        kind = "jpg"
    else:
        kind, raw = "svg", _clean_svg(raw)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    if icon_file("up-" + name) and not data.get("replace"):
        raise HTTPException(409, f"Ein Icon „{name}“ gibt es schon")
    for ext in KINDS:
        (UPLOADS / f"{name}.{ext}").unlink(missing_ok=True)
    (UPLOADS / f"{name}.{kind}").write_bytes(raw)
    return {"name": "up-" + name, "kind": kind}


@router.delete("/api/icons/{name}")
def delete_icon(name: str):
    hit = icon_file(re.sub(r"[^a-z0-9-]", "", name.lower()))
    if not hit:
        raise HTTPException(404, "Icon nicht gefunden")
    hit[0].unlink()
    db.x("UPDATE devices SET icon=NULL WHERE icon=?", (name,))
    db.x("UPDATE types SET icon=NULL WHERE icon=?", (name,))
    _forget()
    return {"ok": True}


def serve(name, hdr):
    hit = icon_file(name)
    if not hit:
        return None
    return Response(hit[0].read_bytes(), media_type=hit[1], headers={**hdr, "Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})

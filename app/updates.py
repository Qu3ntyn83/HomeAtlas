"""Firmware- und Update-Stände der Hardware.

Die Anbindungen melden, was die Geräte selbst über verfügbare Updates wissen (UniFi, OPNsense, Proxmox, Synology,
Home Assistant mit seinen update.*-Entitäten). Gespeichert wird je Gerät in meta.updates eine Liste:
    {"key": "unifi:firmware", "source": "unifi", "title": "Firmware", "installed": "6.6.77", "latest": "6.7.10",
     "available": true, "count": null, "url": null, "checked": 1764150000}
Für jedes neu verfügbare Update geht einmal eine Benachrichtigung raus (Ereignis „update“). Eine Version lässt sich
überspringen; sie meldet sich erst wieder, wenn eine noch neuere erscheint.
"""
from fastapi import APIRouter, Body, HTTPException

from . import db

router = APIRouter(prefix="/api/updates")


def _area(dev):
    from . import monitor
    return monitor.area_of(dev)


def record(dev_id, source, items):
    """Ersetzt die Einträge einer Quelle am Gerät und meldet neu verfügbare Updates. Gibt die Zahl offener zurück."""
    dev = db.one("SELECT * FROM devices WHERE id=?", (dev_id,))
    if not dev:
        return 0
    meta = dict(dev.get("meta") or {})
    now = db.now()
    clean = []
    for it in items:
        if not it.get("key"):
            continue
        clean.append({"key": it["key"], "source": source, "title": it.get("title") or "Update",
                      "installed": str(it.get("installed") or "") or None, "latest": str(it.get("latest") or "") or None,
                      "available": bool(it.get("available")), "count": it.get("count"), "url": it.get("url"), "checked": now})
    keep = [u for u in meta.get("updates") or [] if u.get("source") != source]
    meta["updates"] = keep + clean
    seen, skip = dict(meta.get("update_seen") or {}), meta.get("update_skip") or {}
    events = []
    for u in clean:
        mark = u["latest"] or str(u["count"] or "") or "1"
        if not u["available"]:
            seen.pop(u["key"], None)
            continue
        if seen.get(u["key"]) == mark or skip.get(u["key"]) == mark:
            continue
        seen[u["key"]] = mark
        ver = f"{u['installed']} → {u['latest']}" if u["installed"] and u["latest"] else (u["latest"] or
                                                                                         (f"{u['count']} Pakete" if u["count"] else ""))
        events.append({"text": f"⬆️ {dev['name']}: {u['title']} {ver}".strip(), "area": _area(dev), "event": "update"})
    meta["update_seen"] = seen
    db.update("devices", dev_id, {"meta": meta})
    if events:                                        # über die Sammelstelle der Überwachung: mehrere Updates → eine Nachricht
        from . import monitor
        for ev in events:
            monitor.queue(ev["text"], ev["area"], "update")
    return sum(1 for u in clean if u["available"] and skip.get(u["key"]) != (u["latest"] or str(u["count"] or "") or "1"))


def pending(dev):
    """Offene Updates eines Geräts (übersprungene Versionen ausgenommen)."""
    meta = (dev or {}).get("meta") or {}
    skip = meta.get("update_skip") or {}
    return [u for u in meta.get("updates") or [] if u.get("available")
            and skip.get(u["key"]) != (u.get("latest") or str(u.get("count") or "") or "1")]


@router.post("/{dev_id}/skip")
def skip(dev_id: int, d: dict = Body(...)):
    """Version überspringen ({key, latest}) oder mit {key, undo: true} zurücknehmen."""
    dev = db.one("SELECT * FROM devices WHERE id=?", (dev_id,))
    if not dev:
        raise HTTPException(404, "Gerät nicht gefunden")
    meta = dict(dev.get("meta") or {})
    sk = dict(meta.get("update_skip") or {})
    key = str(d.get("key") or "")
    if not key:
        raise HTTPException(400, "key fehlt")
    if d.get("undo"):
        sk.pop(key, None)
    else:
        u = next((x for x in meta.get("updates") or [] if x.get("key") == key), None)
        if not u:
            raise HTTPException(404, "Update nicht gefunden")
        sk[key] = u.get("latest") or str(u.get("count") or "") or "1"
    meta["update_skip"] = sk
    db.update("devices", dev_id, {"meta": meta})
    return {"ok": True}

"""Read-only infrastructure analytics."""
from collections import defaultdict, deque
from fastapi import APIRouter, HTTPException
from . import db

router = APIRouter(prefix="/api/insights", tags=["insights"])

def dashboard(devices, discoveries):
    ips = defaultdict(list)
    statuses = defaultdict(int)
    for d in devices:
        statuses[d.get("status") or "unknown"] += 1
        if d.get("ip"):
            ips[d["ip"].strip()].append(d["id"])
    return {"devices": len(devices), "statuses": dict(statuses),
            "pending_discoveries": sum(d.get("state") == "pending" for d in discoveries),
            "duplicate_ips": [{"ip": ip, "device_ids": ids} for ip, ids in sorted(ips.items()) if len(ids) > 1]}

def impact(device_id, devices, links):
    by_id = {d["id"]: d for d in devices}
    if device_id not in by_id:
        raise HTTPException(404, "Device not found")
    children = defaultdict(list)
    for d in devices:
        if d.get("parent_id") in by_id and by_id[d["parent_id"]].get("type") != "group":
            children[d["parent_id"]].append(d["id"])
    seen = {device_id}
    queue = deque([device_id])
    while queue:
        for child in children[queue.popleft()]:
            if child not in seen:
                seen.add(child)
                queue.append(child)
    neighbors = set()
    for link in links:
        a, b = link["a_id"], link["b_id"]
        if a in seen and b in by_id:
            neighbors.add(b)
        if b in seen and a in by_id:
            neighbors.add(a)
    return {"device_id": device_id, "contained_device_ids": sorted(seen - {device_id}),
            "possible_network_impact_ids": sorted(neighbors - seen),
            "basis": "Containment and direct links; not a verified service dependency graph"}

@router.get("/dashboard")
def get_dashboard():
    with db.conn() as c:
        c.execute("BEGIN")
        devices = [dict(r) for r in c.execute("SELECT id, ip, status FROM devices")]
        discoveries = [dict(r) for r in c.execute("SELECT state FROM discoveries")]
    return dashboard(devices, discoveries)

@router.get("/impact/{device_id}")
def get_impact(device_id: int):
    with db.conn() as c:
        c.execute("BEGIN")
        devices = [dict(r) for r in c.execute("SELECT id, parent_id, type FROM devices")]
        links = [dict(r) for r in c.execute("SELECT a_id, b_id FROM links")]
    return impact(device_id, devices, links)


@router.get("/history")
def get_history(limit: int = 100, before_id: int | None = None):
    import json
    limit = max(1, min(limit, 500))
    rows = db.q("SELECT * FROM infrastructure_history WHERE (? IS NULL OR id < ?) ORDER BY id DESC LIMIT ?", (before_id, before_id, limit))
    for row in rows:
        for field in ("before_value", "after_value"):
            row[field] = json.loads(row[field]) if row[field] is not None else None
    return {"events": rows, "next_before_id": rows[-1]["id"] if len(rows) == limit else None}

"""Überwachung: aus der Dokumentation erzeugte Checks (Ping, TCP-Port, HTTP), Verlauf, Probleme, Benachrichtigung.

Aufbau der Übersicht nach dem Vorbild von Overlook (github.com/bnlqn/overlook): was ist kaputt, wie geht es jedem
Bereich, was ist diese Woche passiert. Anders als Overlook führt LabVis die Checks selbst aus.
"""
import os
import socket
import ssl
import struct
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response

from . import db, types

router = APIRouter(prefix="/api/monitor")
THRESHOLD = 2            # Fehlschläge in Folge, ab denen ein Check als Problem gilt
PASSIVE = {"patchpanel", "shelf", "blank", "cablemgmt", "group", "internet"}
AREAS = {"network": "Netzwerk", "servers": "Server", "storage": "Speicher", "apps": "Dienste", "smarthome": "Smarthome",
         "clients": "Endgeräte", "other": "Sonstiges"}
TYPE_AREA = {"router": "network", "firewall": "network", "switch": "network", "ap": "network",
             "hypervisor": "servers", "server": "servers", "vm": "servers", "workstation": "servers",
             "nas": "storage", "container": "apps", "app": "apps", "service": "apps",
             "iot": "smarthome", "light": "smarthome", "plug": "smarthome", "sensor": "smarthome", "thermostat": "smarthome",
             "blind": "smarthome", "lock": "smarthome", "vacuum": "smarthome", "camera": "smarthome", "speaker": "smarthome",
             "tv": "smarthome"}
# Ports, für die sich ein eigener Check lohnt
PORT_NAMES = {22: "SSH", 53: "DNS", 445: "SMB", 2049: "NFS", 3306: "MariaDB/MySQL", 5432: "PostgreSQL", 3389: "RDP",
              8006: "Proxmox", 8007: "Proxmox Backup", 8123: "Home Assistant", 5001: "DSM", 9443: "Portainer",
              32400: "Plex", 8096: "Emby/Jellyfin", 1883: "MQTT", 631: "IPP", 9100: "Druckdienst", 443: "HTTPS", 80: "HTTP"}
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=_CTX))
_seq = [0]

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks(
  id INTEGER PRIMARY KEY, device_id INTEGER, name TEXT, kind TEXT NOT NULL, target TEXT NOT NULL, port INTEGER,
  interval_s INTEGER DEFAULT 60, enabled INTEGER DEFAULT 1, status TEXT DEFAULT 'unknown', since REAL, last_run REAL,
  last_ms REAL, last_error TEXT, fails INTEGER DEFAULT 0, source TEXT DEFAULT 'manual', ever_up INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS check_results(id INTEGER PRIMARY KEY, check_id INTEGER, ts REAL, ok INTEGER, ms REAL);
CREATE INDEX IF NOT EXISTS ix_results ON check_results(check_id, ts);
CREATE TABLE IF NOT EXISTS check_hours(
  check_id INTEGER, hour REAL, ok_n INTEGER DEFAULT 0, fail_n INTEGER DEFAULT 0, PRIMARY KEY(check_id, hour));
CREATE TABLE IF NOT EXISTS check_events(id INTEGER PRIMARY KEY, ts REAL, check_id INTEGER, device_id INTEGER, kind TEXT, text TEXT);
"""
FIELDS = ["device_id", "name", "kind", "target", "port", "interval_s", "enabled"]


def init():
    with db.conn() as c:
        c.executescript(SCHEMA)


# ------------------------------------------------------------------ Prüfarten
def _checksum(data):
    s = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    s = (s >> 16) + (s & 0xFFFF)
    s += s >> 16
    return ~s & 0xFFFF


def ping(host, timeout=2.0):
    """ICMP-Echo ohne externes Programm. Braucht NET_RAW (Docker-Standard im Host-Netz) oder erlaubte Ping-Sockets."""
    addr = socket.gethostbyname(host)
    _seq[0] = (_seq[0] + 1) % 65000
    ident, seq = os.getpid() & 0xFFFF, _seq[0]
    payload = struct.pack("!d", time.time()) + b"labvis-ping-0123"
    head = struct.pack("!BBHHH", 8, 0, 0, ident, seq)
    packet = struct.pack("!BBHHH", 8, 0, _checksum(head + payload), ident, seq) + payload
    last = None
    for kind in (socket.SOCK_RAW, socket.SOCK_DGRAM):
        try:
            s = socket.socket(socket.AF_INET, kind, socket.IPPROTO_ICMP)
        except (PermissionError, OSError) as e:
            last = e
            continue
        with s:
            s.settimeout(timeout)
            t0 = time.time()
            s.sendto(packet, (addr, 0))
            while time.time() - t0 < timeout:
                try:
                    data, peer = s.recvfrom(1024)
                except socket.timeout:
                    break
                body = data[20:] if kind == socket.SOCK_RAW else data
                if peer[0] == addr and len(body) >= 8 and body[0] == 0 and struct.unpack("!H", body[6:8])[0] == seq:
                    return (time.time() - t0) * 1000
            raise TimeoutError("keine Antwort auf Ping")
    raise RuntimeError(f"Ping nicht möglich ({last}) – dem Container fehlt NET_RAW")


def run_check(c):
    """Führt einen Check aus → (ok, millisekunden, fehlertext)."""
    t0 = time.time()
    try:
        if c["kind"] == "ping":
            return True, ping(c["target"]), None
        if c["kind"] == "tcp":
            socket.create_connection((c["target"], int(c["port"])), timeout=4).close()
        elif c["kind"] == "http":
            req = urllib.request.Request(c["target"], headers={"User-Agent": "LabVis-Monitor"})
            try:
                _OPENER.open(req, timeout=8).close()
            except urllib.error.HTTPError as e:      # 401/403/404: der Dienst antwortet, also läuft er
                if e.code >= 500:
                    return False, (time.time() - t0) * 1000, f"HTTP {e.code}"
        else:
            return False, 0, "unbekannte Prüfart"
        return True, (time.time() - t0) * 1000, None
    except (socket.timeout, TimeoutError):
        return False, None, "keine Antwort (Zeitüberschreitung)"
    except ConnectionRefusedError:
        return False, None, "Verbindung abgelehnt – Dienst läuft nicht"
    except socket.gaierror:
        return False, None, "Name lässt sich nicht auflösen"
    except urllib.error.URLError as e:
        r = e.reason
        return False, None, ("Name lässt sich nicht auflösen" if isinstance(r, socket.gaierror) else
                             "keine Antwort (Zeitüberschreitung)" if "timed out" in str(r) else
                             "Verbindung abgelehnt – Dienst läuft nicht" if isinstance(r, ConnectionRefusedError) else str(r)[:120])
    except Exception as e:  # noqa: BLE001 – der Text landet am Check
        return False, None, str(e)[:120]


# ------------------------------------------------------------------ Ergebnis verbuchen
def label(c):
    dev = db.one("SELECT name FROM devices WHERE id=?", (c.get("device_id") or 0,))
    return f"{dev['name']}: {c['name']}" if dev else c["name"]


_outbox, _outbox_lock = [], threading.Lock()


def queue(text):
    """Meldungen sammeln: fällt ein Switch aus, kommt eine Nachricht statt dreißig."""
    with _outbox_lock:
        _outbox.append((time.time(), text))


def flush(force=False):
    with _outbox_lock:
        if not _outbox or (not force and time.time() - _outbox[0][0] < 12):
            return
        lines = [t for _, t in _outbox]
        _outbox.clear()
    notify(lines[0] if len(lines) == 1 else f"LabVis: {len(lines)} Meldungen\n" + "\n".join(lines[:15]) +
           (f"\n… und {len(lines) - 15} weitere" if len(lines) > 15 else ""))


def notify(text):
    """Schickt die Meldung an die hinterlegte Adresse (ntfy-Thema oder beliebiger Webhook, der Text per POST annimmt)."""
    url = (db.setting("notify_url") or "").strip()
    if not url:
        return
    try:
        req = urllib.request.Request(url, data=text.encode(), method="POST",
                                     headers={"Content-Type": "text/plain; charset=utf-8", "Title": "LabVis"})
        urllib.request.urlopen(req, timeout=8).close()
    except Exception as e:  # noqa: BLE001
        print("notify:", e, flush=True)


def record(c, ok, ms, err):
    now = db.now()
    db.x("INSERT INTO check_results(check_id,ts,ok,ms) VALUES(?,?,?,?)", (c["id"], now, 1 if ok else 0, ms))
    db.x("INSERT INTO check_hours(check_id,hour,ok_n,fail_n) VALUES(?,?,?,?) ON CONFLICT(check_id,hour) DO UPDATE SET "
         "ok_n=ok_n+excluded.ok_n, fail_n=fail_n+excluded.fail_n", (c["id"], now // 3600 * 3600, int(ok), int(not ok)))
    fails = 0 if ok else (c.get("fails") or 0) + 1
    status, since, event, ever = c["status"], c.get("since"), None, c.get("ever_up") or 0
    if ok and status != "up":
        event = "up" if status == "down" and ever else None     # nur melden, wenn vorher ein Ausfall gemeldet wurde
        status, since, ever = "up", now, 1
    elif not ok and fails >= THRESHOLD and status != "down":
        # ein Check, der noch nie funktioniert hat, ist kein Ausfall, sondern ein falsches Ziel: kein Ereignis, keine Meldung
        status, since, event = "down", now, ("down" if ever else None)
    # nach einem ersten Fehlschlag schon nach 15 Sekunden erneut prüfen, statt ein ganzes Intervall zu warten
    last_run = now if ok or fails >= THRESHOLD else now - max(15, c.get("interval_s") or 60) + 15
    db.x("UPDATE checks SET status=?, since=?, last_run=?, last_ms=?, last_error=?, fails=?, ever_up=? WHERE id=?",
         (status, since, last_run, ms, None if ok else err, fails, ever, c["id"]))
    if c["kind"] == "ping" and c.get("device_id") and status in ("up", "down") and ever:
        # der Ping-Check ist aktueller als der stündliche Scan: Gerätestatus mitführen
        if ok:
            db.x("UPDATE devices SET status='online', last_seen=? WHERE id=?", (now, c["device_id"]))
        elif status == "down":
            db.x("UPDATE devices SET status='offline' WHERE id=?", (c["device_id"],))
    if event:
        text = f"{label(c)} – {'wieder erreichbar' if event == 'up' else 'ausgefallen' + (': ' + err if err else '')}"
        db.x("INSERT INTO check_events(ts,check_id,device_id,kind,text) VALUES(?,?,?,?,?)",
             (now, c["id"], c.get("device_id"), event, text))
        queue(("✅ " if event == "up" else "🔴 ") + text)


def execute(check_id):
    c = db.one("SELECT * FROM checks WHERE id=?", (check_id,))
    if c:
        record(c, *run_check(c))


def _loop():
    pool, last_prune = ThreadPoolExecutor(max_workers=16), 0
    running = set()

    def job(cid):
        try:
            execute(cid)
        finally:
            running.discard(cid)

    while True:
        time.sleep(5)
        try:
            now = db.now()
            for c in db.q("SELECT id, last_run, interval_s FROM checks WHERE enabled=1"):
                if c["id"] not in running and now - (c["last_run"] or 0) >= max(15, c["interval_s"] or 60):
                    running.add(c["id"])
                    pool.submit(job, c["id"])
            flush()
            if now - last_prune > 600:
                last_prune = now
                db.x("DELETE FROM check_results WHERE ts<?", (now - 12 * 3600,))
                db.x("DELETE FROM check_hours WHERE hour<?", (now - 8 * 86400,))
                db.x("DELETE FROM check_events WHERE ts<?", (now - 30 * 86400,))
        except Exception as e:  # noqa: BLE001
            print("monitor:", e, flush=True)


def start():
    threading.Thread(target=_loop, daemon=True).start()


# ------------------------------------------------------------------ Checks aus der Dokumentation
def area_of(dev, kind=None):
    a = types.area((dev or {}).get("type"))
    a = a if a in AREAS else "other"
    if kind == "http" and a not in ("network", "storage"):
        return "apps"
    return a


def plan(devices, groups):
    """Leitet aus den dokumentierten Geräten die sinnvollen Checks ab. groups: gewählte Bereiche (AREAS-Schlüssel)."""
    out = []
    for d in devices:
        if d["type"] in PASSIVE or types.base(d["type"]) in ("client", "smartphone", "tablet"):
            continue
        area = TYPE_AREA.get(d["type"], "other")
        if area not in groups:
            continue
        ip, ports = d.get("ip"), set(d.get("ports") or [])
        if ip:
            out.append({"device_id": d["id"], "kind": "ping", "target": ip, "port": None, "name": "Ping"})
            if 443 in ports:
                ports.discard(80)
            # Port eines veröffentlichten Containers ist über die URL abgedeckt
            for p in sorted(ports & set(PORT_NAMES)):
                if area in ("network", "servers", "storage") or p not in (80, 443):
                    out.append({"device_id": d["id"], "kind": "tcp", "target": ip, "port": p, "name": f"{PORT_NAMES[p]} (Port {p})"})
        url = d.get("url") or ""
        if url.startswith(("http://", "https://")) and (area == "apps" or not ip):
            out.append({"device_id": d["id"], "kind": "http", "target": url, "port": None, "name": "Weboberfläche"})
    return out


def generate(groups):
    made = 0
    have = {(c["device_id"], c["kind"], c["target"], c["port"]) for c in db.q("SELECT device_id,kind,target,port FROM checks")}
    for c in plan(db.q("SELECT * FROM devices"), set(groups)):
        key = (c["device_id"], c["kind"], c["target"], c["port"])
        if key not in have:
            have.add(key)
            db.x("INSERT INTO checks(device_id,name,kind,target,port,source) VALUES(?,?,?,?,?,'auto')",
                 (c["device_id"], c["name"], c["kind"], c["target"], c["port"]))
            made += 1
    return made


# ------------------------------------------------------------------ API
def light():
    """Schlanke Liste für den allgemeinen Zustand (Gerätepanel, Zähler im Reiter)."""
    return db.q("SELECT id, device_id, name, kind, target, port, status, enabled, since, last_error, last_ms, interval_s, ever_up FROM checks")


@router.get("/overview")
def overview():
    now = db.now()
    devs = {d["id"]: d for d in db.q("SELECT id, name, type, room FROM devices")}
    recent = {}
    for r in db.q("SELECT check_id, ok FROM check_results WHERE ts>? ORDER BY ts", (now - 12 * 3600,)):
        recent.setdefault(r["check_id"], []).append(r["ok"])
    up24, up7 = {}, {}
    for r in db.q("SELECT check_id, hour, ok_n, fail_n FROM check_hours WHERE hour>?", (now - 7 * 86400,)):
        for store, limit in ((up24, 86400), (up7, 7 * 86400)):
            if r["hour"] > now - limit:
                a = store.setdefault(r["check_id"], [0, 0])
                a[0] += r["ok_n"]
                a[1] += r["ok_n"] + r["fail_n"]
    checks = []
    for c in db.q("SELECT * FROM checks ORDER BY id"):
        d = devs.get(c["device_id"])
        pct = lambda s: round(100 * s[c["id"]][0] / s[c["id"]][1], 2) if s.get(c["id"], [0, 0])[1] else None   # noqa: E731
        checks.append({**c, "device": d["name"] if d else None, "area": area_of(d, c["kind"]),
                       "last30": recent.get(c["id"], [])[-30:], "up24": pct(up24), "up7": pct(up7)})
    return {"checks": checks, "areas": AREAS, "threshold": THRESHOLD,
            "events": db.q("SELECT * FROM check_events WHERE ts>? ORDER BY ts DESC LIMIT 200", (now - 7 * 86400,)),
            "notify": bool((db.setting("notify_url") or "").strip()), "now": now}


@router.get("/plan")
def preview():
    """Was „aus der Dokumentation erzeugen“ je Bereich anlegen würde."""
    have = {(c["device_id"], c["kind"], c["target"], c["port"]) for c in db.q("SELECT device_id,kind,target,port FROM checks")}
    devs = {d["id"]: d for d in db.q("SELECT * FROM devices")}
    counts = {k: 0 for k in AREAS}
    for c in plan(list(devs.values()), set(AREAS)):
        if (c["device_id"], c["kind"], c["target"], c["port"]) not in have:
            counts[TYPE_AREA.get(devs[c["device_id"]]["type"], "other")] += 1
    return {"new": counts, "areas": AREAS}


@router.post("/generate")
def gen(data: dict = Body(...)):
    groups = [g for g in (data.get("areas") or []) if g in AREAS]
    if not groups:
        raise HTTPException(400, "Mindestens einen Bereich wählen")
    return {"created": generate(groups)}


def _clean(data):
    d = {k: data[k] for k in FIELDS if k in data}
    for k in ("device_id", "port", "interval_s", "enabled"):
        if k in d:
            d[k] = int(d[k]) if d[k] not in (None, "") else None
    if "kind" in d and d["kind"] not in ("ping", "tcp", "http"):
        raise HTTPException(400, "Unbekannte Prüfart")
    return d


def _validate(c):
    if not (c.get("target") or "").strip():
        raise HTTPException(400, "Ziel fehlt")
    if c["kind"] == "tcp" and not c.get("port"):
        raise HTTPException(400, "Port fehlt")
    if c["kind"] == "http" and not c["target"].startswith(("http://", "https://")):
        raise HTTPException(400, "Die Adresse muss mit http:// oder https:// beginnen")


@router.post("/checks")
def create(data: dict = Body(...)):
    d = _clean(data)
    d.setdefault("kind", "ping")
    _validate(d)
    d["name"] = d.get("name") or {"ping": "Ping", "tcp": f"Port {d.get('port')}", "http": "Weboberfläche"}[d["kind"]]
    d["interval_s"] = max(15, d.get("interval_s") or 60)
    cols = list(d)
    cid = db.x(f"INSERT INTO checks({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [d[k] for k in cols])
    threading.Thread(target=execute, args=(cid,), daemon=True).start()
    return {"id": cid}


@router.put("/checks/{cid}")
def change(cid: int, data: dict = Body(...)):
    old = db.one("SELECT * FROM checks WHERE id=?", (cid,))
    if not old:
        raise HTTPException(404, "Check nicht gefunden")
    d = _clean(data)
    _validate({**old, **d})
    if "interval_s" in d:
        d["interval_s"] = max(15, d["interval_s"] or 60)
    if any(k in d and d[k] != old[k] for k in ("kind", "target", "port")):
        d.update(status="unknown", fails=0, since=None, ever_up=0)
    if d:
        db.x(f"UPDATE checks SET {','.join(k + '=?' for k in d)} WHERE id=?", list(d.values()) + [cid])
    return {"ok": True}


def drop(where, params):
    ids = [c["id"] for c in db.q(f"SELECT id FROM checks WHERE {where}", params)]
    for i in ids:
        for t in ("check_results", "check_hours", "check_events"):
            db.x(f"DELETE FROM {t} WHERE check_id=?", (i,))
        db.x("DELETE FROM checks WHERE id=?", (i,))
    return len(ids)


@router.delete("/checks/{cid}")
def remove(cid: int):
    drop("id=?", (cid,))
    return {"ok": True}


@router.post("/checks/{cid}/run")
def run_now(cid: int):
    execute(cid)
    return db.one("SELECT id, status, last_ms, last_error FROM checks WHERE id=?", (cid,)) or {}


@router.delete("/never")
def remove_never():
    """Räumt Checks ab, die seit ihrer Anlage noch nie erreichbar waren (falsches Ziel, Dienst gibt es nicht)."""
    return {"removed": drop("status='down' AND ever_up=0", ())}


@router.post("/test-notify")
def test_notify():
    if not (db.setting("notify_url") or "").strip():
        raise HTTPException(400, "Keine Adresse für Benachrichtigungen hinterlegt")
    notify("🔔 LabVis: Testmeldung – Benachrichtigungen funktionieren")
    return {"ok": True}


@router.get("/gatus.yaml")
def gatus():
    """Die Checks als Gatus-Konfiguration – für alle, die Gatus als Prüfmaschine (und Overlook als Übersicht) nutzen."""
    devs = {d["id"]: d for d in db.q("SELECT id, name, type FROM devices")}
    q = lambda s: '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'   # noqa: E731
    out = ["# Erzeugt von LabVis aus der Dokumentation", "endpoints:"]
    for c in db.q("SELECT * FROM checks WHERE enabled=1 ORDER BY device_id, id"):
        d = devs.get(c["device_id"])
        url = {"ping": f"icmp://{c['target']}", "tcp": f"tcp://{c['target']}:{c['port']}", "http": c["target"]}[c["kind"]]
        cond = '"[STATUS] < 500"' if c["kind"] == "http" else '"[CONNECTED] == true"'
        out += [f"  - name: {q((d['name'] + ' – ' if d else '') + c['name'])}", f"    group: {q(AREAS[area_of(d, c['kind'])])}",
                f"    url: {q(url)}", f"    interval: {max(15, c['interval_s'] or 60)}s"] + \
               (["    client:", "      insecure: true"] if url.startswith("https://") else []) + ["    conditions:", f"      - {cond}"]
    return Response("\n".join(out) + "\n", media_type="text/yaml",
                    headers={"Content-Disposition": 'attachment; filename="gatus-endpoints.yaml"'})

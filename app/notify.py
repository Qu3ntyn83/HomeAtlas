"""Benachrichtigungen: mehrere Ziele (ntfy, Gotify, Telegram, Discord, Slack/Mattermost, Webhook, E-Mail),
je Ziel Filter nach Bereich und Ereignis sowie Ruhezeiten mit Zusammenfassung danach."""
import json
import smtplib
import ssl
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from email.message import EmailMessage

from fastapi import APIRouter, Body, HTTPException

from . import db

MASK = "••••••••"
# Art → Felder [Name, Bezeichnung, Vorgabe, Feldart]; Feldart "password" wird nie im Klartext ausgeliefert
KINDS = {
    "ntfy": {"label": "ntfy", "fields": [["url", "Themen-Adresse (https://ntfy.sh/mein-thema)", "", "password"],
                                          ["token", "Zugriffstoken (optional)", "", "password"]]},
    "gotify": {"label": "Gotify", "fields": [["url", "Adresse des Servers (https://gotify.lan)"], ["token", "App-Token", "", "password"]]},
    "telegram": {"label": "Telegram", "fields": [["token", "Bot-Token (von @BotFather)", "", "password"], ["chat_id", "Chat-ID"]]},
    "discord": {"label": "Discord", "fields": [["url", "Webhook-Adresse", "", "password"]]},
    "slack": {"label": "Slack / Mattermost / Rocket.Chat", "fields": [["url", "Incoming-Webhook-Adresse", "", "password"]]},
    "webhook": {"label": "Webhook", "fields": [["url", "Adresse (POST)", "", "password"],
                                                ["format", "Format", "text", [["text", "Text"], ["json", "JSON (title, message, events)"]]]]},
    "email": {"label": "E-Mail (SMTP)", "fields": [["host", "SMTP-Server"], ["port", "Port", "587"],
                                                    ["tls", "Verschlüsselung", "starttls", [["starttls", "STARTTLS"], ["ssl", "SSL/TLS"], ["none", "keine"]]],
                                                    ["user", "Benutzer (optional)"], ["password", "Passwort", "", "password"],
                                                    ["sender", "Absender"], ["to", "Empfänger (mehrere mit Komma)"]]},
}
SECRETS = {f[0] for k in KINDS.values() for f in k["fields"] if len(f) > 3 and f[3] == "password"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS notifiers(
  id INTEGER PRIMARY KEY, name TEXT, kind TEXT NOT NULL, config TEXT DEFAULT '{}', enabled INTEGER DEFAULT 1,
  areas TEXT DEFAULT '[]', events TEXT DEFAULT 'both', quiet_from TEXT, quiet_to TEXT, quiet_areas TEXT DEFAULT '[]',
  digest INTEGER DEFAULT 1, last_status TEXT, last_sent REAL, updates INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS notify_held(id INTEGER PRIMARY KEY, notifier_id INTEGER, ts REAL, text TEXT);
"""
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OPENER = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_CTX))
_lock = threading.Lock()
router = APIRouter(prefix="/api/notifiers")


def init():
    with db.conn() as c:
        c.executescript(SCHEMA)
        if "updates" not in [r[1] for r in c.execute("PRAGMA table_info(notifiers)")]:   # ab 0.29: Hinweise auf Updates
            c.execute("ALTER TABLE notifiers ADD COLUMN updates INTEGER DEFAULT 1")
    old = (db.setting("notify_url") or "").strip()          # bisherige einzelne Adresse übernehmen
    if old and not db.one("SELECT id FROM notifiers"):
        kind = "ntfy" if "ntfy" in old else "webhook"
        db.x("INSERT INTO notifiers(name,kind,config) VALUES(?,?,?)", ("Benachrichtigung", kind, json.dumps({"url": old})))
        db.x("UPDATE settings SET value='' WHERE key='notify_url'")


def _j(v, empty):
    if isinstance(v, (dict, list)):                   # db.q wandelt bekannte JSON-Spalten schon um
        return v
    try:
        return json.loads(v) if v else empty
    except ValueError:
        return empty


def _row(r):
    r = dict(r)
    r["config"] = _j(r.get("config"), {})
    r["areas"], r["quiet_areas"] = _j(r.get("areas"), []), _j(r.get("quiet_areas"), [])
    return r


def all_notifiers(enabled_only=False):
    return [_row(r) for r in db.q("SELECT * FROM notifiers" + (" WHERE enabled=1" if enabled_only else "") + " ORDER BY id")]


# ------------------------------------------------------------------ Regeln
def _minutes(hhmm):
    try:
        h, m = (hhmm or "").strip().split(":")
        return int(h) * 60 + int(m)
    except ValueError:
        return None


def quiet_now(n, at=None):
    """Liegt der Zeitpunkt in der Ruhezeit des Ziels? Über Mitternacht (22:00–07:00) wird richtig gerechnet."""
    a, b = _minutes(n.get("quiet_from")), _minutes(n.get("quiet_to"))
    if a is None or b is None or a == b:
        return False
    t = datetime.fromtimestamp(at or time.time())
    m = t.hour * 60 + t.minute
    return a <= m < b if a < b else (m >= a or m < b)


def wants(n, ev):
    if n.get("areas") and ev.get("area") not in n["areas"]:
        return False
    if ev.get("event") == "update":
        return n.get("updates", 1) not in (0, "0", False)
    return n.get("events") in (None, "", "both") or n["events"] == ev.get("event")


def held_by_quiet(n, ev, at=None):
    return quiet_now(n, at) and (not n.get("quiet_areas") or ev.get("area") in n["quiet_areas"])


# ------------------------------------------------------------------ Versand
def _post(url, data, headers, timeout=10):
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    with _OPENER.open(req, timeout=timeout) as r:
        r.read()


def send(n, title, text, high=False):
    c, k = n.get("config") or {}, n["kind"]
    if k == "ntfy":
        h = {"Title": title.encode("utf-8").decode("latin-1", "ignore") or "HomeAtlas", "Priority": "high" if high else "default",
             "Tags": "rotating_light" if high else "white_check_mark", "Content-Type": "text/plain; charset=utf-8"}
        if c.get("token"):
            h["Authorization"] = "Bearer " + c["token"]
        _post(c["url"], text.encode(), h)
    elif k == "gotify":
        _post(c["url"].rstrip("/") + "/message?token=" + urllib.parse.quote(c.get("token") or ""),
              json.dumps({"title": title, "message": text, "priority": 8 if high else 4}).encode(), {"Content-Type": "application/json"})
    elif k == "telegram":
        _post(f"https://api.telegram.org/bot{c.get('token')}/sendMessage",
              json.dumps({"chat_id": c.get("chat_id"), "text": f"{title}\n{text}"[:4000]}).encode(), {"Content-Type": "application/json"})
    elif k == "discord":
        _post(c["url"], json.dumps({"content": f"**{title}**\n{text}"[:1900]}).encode(), {"Content-Type": "application/json"})
    elif k == "slack":
        _post(c["url"], json.dumps({"text": f"*{title}*\n{text}"}).encode(), {"Content-Type": "application/json"})
    elif k == "webhook":
        if c.get("format") == "json":
            _post(c["url"], json.dumps({"title": title, "message": text, "high": high}).encode(), {"Content-Type": "application/json"})
        else:
            _post(c["url"], text.encode(), {"Content-Type": "text/plain; charset=utf-8", "Title": "HomeAtlas"})
    elif k == "email":
        msg = EmailMessage()
        msg["Subject"], msg["From"] = title, c.get("sender") or c.get("user")
        msg["To"] = ", ".join(a.strip() for a in (c.get("to") or "").split(",") if a.strip())
        msg.set_content(text)
        port, mode = int(c.get("port") or 587), c.get("tls") or "starttls"
        cls = smtplib.SMTP_SSL if mode == "ssl" else smtplib.SMTP
        kw = {"context": _CTX} if mode == "ssl" else {}
        with cls(c["host"], port, timeout=15, **kw) as s:
            if mode == "starttls":
                s.starttls(context=_CTX)
            if c.get("user"):
                s.login(c["user"], c.get("password") or "")
            s.send_message(msg)
    else:
        raise ValueError("unbekannte Art " + k)


def _deliver(n, title, text, high):
    try:
        send(n, title, text, high)
        db.x("UPDATE notifiers SET last_status=?, last_sent=? WHERE id=?", ("ok", db.now(), n["id"]))
        return None
    except Exception as e:  # noqa: BLE001 – Fehler wird am Ziel angezeigt
        err = f"{type(e).__name__}: {e}"[:300]
        db.x("UPDATE notifiers SET last_status=? WHERE id=?", ("Fehler: " + err, n["id"]))
        print("notify:", n.get("name") or n["kind"], err, flush=True)
        return err


def _compose(lines):
    if len(lines) == 1:
        return "HomeAtlas", lines[0]
    return f"HomeAtlas: {len(lines)} Meldungen", "\n".join(lines[:20]) + (f"\n… und {len(lines) - 20} weitere" if len(lines) > 20 else "")


def dispatch(events, at=None):
    """Ereignisse ({text, area, event}) an alle passenden Ziele; in der Ruhezeit zurückhalten oder verwerfen."""
    with _lock:
        for n in all_notifiers(enabled_only=True):
            out = []
            for ev in events:
                if not wants(n, ev):
                    continue
                if held_by_quiet(n, ev, at):
                    if n.get("digest"):
                        db.x("INSERT INTO notify_held(notifier_id,ts,text) VALUES(?,?,?)", (n["id"], at or db.now(), ev["text"]))
                    continue
                out.append(ev)
            if out:
                title, text = _compose([e["text"] for e in out])
                _deliver(n, title, text, any(e.get("event") == "down" for e in out))


def tick(at=None):
    """Nach der Ruhezeit: Zurückgehaltenes gesammelt schicken."""
    with _lock:
        for n in all_notifiers(enabled_only=True):
            if quiet_now(n, at):
                continue
            held = db.q("SELECT id, ts, text FROM notify_held WHERE notifier_id=? ORDER BY ts", (n["id"],))
            if not held:
                continue
            lines = [f"{datetime.fromtimestamp(h['ts']):%H:%M} {h['text']}" for h in held]
            title = f"HomeAtlas: {len(held)} {'Meldung' if len(held) == 1 else 'Meldungen'} aus der Ruhezeit"
            text = "\n".join(lines[:30]) + (f"\n… und {len(lines) - 30} weitere" if len(lines) > 30 else "")
            if _deliver(n, title, text, any("🔴" in h["text"] for h in held)) is None:
                db.x("DELETE FROM notify_held WHERE notifier_id=? AND id<=?", (n["id"], held[-1]["id"]))
        db.x("DELETE FROM notify_held WHERE ts<?", ((at or db.now()) - 7 * 86400,))


# ------------------------------------------------------------------ API (nur Admin, siehe auth.ADMIN_ONLY)
def _public(n):
    n = dict(n)
    n["config"] = {k: (MASK if k in SECRETS and v else v) for k, v in (n.get("config") or {}).items()}
    n["held"] = (db.one("SELECT count(*) n FROM notify_held WHERE notifier_id=?", (n["id"],)) or {}).get("n", 0)
    n["quiet"] = quiet_now(n)
    return n


def _clean(d, old=None):
    kind = d.get("kind") or (old or {}).get("kind")
    if kind not in KINDS:
        raise HTTPException(400, "Unbekannte Art")
    cfg = {k: v for k, v in (d.get("config") or {}).items() if k in {f[0] for f in KINDS[kind]["fields"]}}
    oldc = (old or {}).get("config") or {}
    cfg = {k: (oldc.get(k) if v == MASK else (v.strip() if isinstance(v, str) else v)) for k, v in cfg.items()}
    need = {"ntfy": ["url"], "gotify": ["url", "token"], "telegram": ["token", "chat_id"], "discord": ["url"], "slack": ["url"],
            "webhook": ["url"], "email": ["host", "to"]}[kind]
    miss = [f[1] for f in KINDS[kind]["fields"] if f[0] in need and not cfg.get(f[0])]
    if miss:
        raise HTTPException(400, "Fehlt: " + ", ".join(miss))
    for q in ("quiet_from", "quiet_to"):
        if d.get(q) and _minutes(d[q]) is None:
            raise HTTPException(400, "Ruhezeit bitte als HH:MM angeben")
    return {"name": (d.get("name") or "").strip() or KINDS[kind]["label"], "kind": kind, "config": json.dumps(cfg),
            "enabled": 1 if d.get("enabled", 1) not in (0, "0", False) else 0,
            "areas": json.dumps([a for a in d.get("areas") or [] if a]), "events": d.get("events") if d.get("events") in ("both", "down", "up") else "both",
            "quiet_from": (d.get("quiet_from") or "").strip() or None, "quiet_to": (d.get("quiet_to") or "").strip() or None,
            "quiet_areas": json.dumps([a for a in d.get("quiet_areas") or [] if a]), "digest": 1 if d.get("digest", 1) not in (0, "0", False) else 0,
            "updates": 1 if d.get("updates", 1) not in (0, "0", False) else 0}


@router.get("")
def list_all():
    return {"notifiers": [_public(n) for n in all_notifiers()], "kinds": KINDS}


@router.post("")
def create(d: dict = Body(...)):
    row = _clean(d)
    cols = list(row)
    nid = db.x(f"INSERT INTO notifiers({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [row[k] for k in cols])
    return {"id": nid}


@router.put("/{nid}")
def update(nid: int, d: dict = Body(...)):
    old = db.one("SELECT * FROM notifiers WHERE id=?", (nid,))
    if not old:
        raise HTTPException(404, "Nicht gefunden")
    row = _clean(d, _row(old))
    db.x(f"UPDATE notifiers SET {','.join(k + '=?' for k in row)} WHERE id=?", [*row.values(), nid])
    return {"ok": True}


@router.delete("/{nid}")
def delete(nid: int):
    db.x("DELETE FROM notify_held WHERE notifier_id=?", (nid,))
    db.x("DELETE FROM notifiers WHERE id=?", (nid,))
    return {"ok": True}


@router.post("/{nid}/test")
def test(nid: int):
    n = db.one("SELECT * FROM notifiers WHERE id=?", (nid,))
    if not n:
        raise HTTPException(404, "Nicht gefunden")
    err = _deliver(_row(n), "HomeAtlas", "🔔 Testmeldung – dieses Ziel funktioniert", False)
    if err:
        raise HTTPException(502, "Senden fehlgeschlagen: " + err)
    return {"ok": True}

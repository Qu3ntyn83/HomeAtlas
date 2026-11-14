"""SQLite-Speicher für LabVis. Eine Verbindung pro Aufruf, WAL-Modus."""
import json
import os
import sqlite3
import time
from pathlib import Path

DATA = Path(os.environ.get("LABVIS_DATA", "/data"))
DB = DATA / "labvis.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS vlans(
  id INTEGER PRIMARY KEY, vid INTEGER, name TEXT NOT NULL, subnet TEXT, gateway TEXT,
  color TEXT DEFAULT '#58a6ff', note TEXT, scan INTEGER DEFAULT 0, last_scan REAL);
CREATE TABLE IF NOT EXISTS racks(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, units INTEGER DEFAULT 24, location TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS devices(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT DEFAULT 'other', model TEXT, os TEXT,
  ip TEXT, mac TEXT, vendor TEXT, hostname TEXT, url TEXT, icon TEXT, note TEXT,
  vlan_id INTEGER, parent_id INTEGER, x REAL, y REAL,
  status TEXT DEFAULT 'unknown', last_seen REAL,
  rack_id INTEGER, rack_u INTEGER, rack_height INTEGER DEFAULT 1, room TEXT,
  source TEXT DEFAULT 'manual', ext_id TEXT, integration_id INTEGER,
  ports TEXT DEFAULT '[]', meta TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS links(
  id INTEGER PRIMARY KEY, a_id INTEGER NOT NULL, b_id INTEGER NOT NULL, a_port TEXT, b_port TEXT,
  speed TEXT DEFAULT '1G', vlan_id INTEGER, trunk INTEGER DEFAULT 0, kind TEXT DEFAULT 'cable',
  note TEXT, source TEXT DEFAULT 'manual');
CREATE TABLE IF NOT EXISTS discoveries(
  id INTEGER PRIMARY KEY, ip TEXT, mac TEXT, vendor TEXT, hostname TEXT, vlan_id INTEGER,
  ports TEXT DEFAULT '[]', http TEXT DEFAULT '{}', snmp TEXT DEFAULT '{}', guess TEXT DEFAULT '{}',
  first_seen REAL, last_seen REAL, state TEXT DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS integrations(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, name TEXT, device_id INTEGER, config TEXT DEFAULT '{}',
  enabled INTEGER DEFAULT 1, last_sync REAL, last_status TEXT);
CREATE TABLE IF NOT EXISTS scans(
  id INTEGER PRIMARY KEY, network TEXT, started REAL, finished REAL, hosts INTEGER DEFAULT 0,
  new INTEGER DEFAULT 0, status TEXT, log TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS wlans(
  id INTEGER PRIMARY KEY, ssid TEXT NOT NULL, vlan_id INTEGER, band TEXT, security TEXT, note TEXT, aps TEXT DEFAULT '[]');
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, pw TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'admin', created REAL, last_login REAL);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created REAL, expires REAL, ua TEXT);
"""

JSON_COLS = {"ports", "meta", "http", "snmp", "guess", "config", "aps"}
LIST_COLS = {"ports", "aps"}
COLUMNS = {
    "vlans": ["vid", "name", "subnet", "gateway", "color", "note", "scan"],
    "racks": ["name", "units", "location", "note"],
    "devices": ["name", "type", "model", "os", "ip", "mac", "vendor", "hostname", "url", "icon", "note", "room",
                "vlan_id", "parent_id", "x", "y", "status", "last_seen", "rack_id", "rack_u", "rack_height",
                "source", "ext_id", "integration_id", "ports", "meta"],
    "links": ["a_id", "b_id", "a_port", "b_port", "speed", "vlan_id", "trunk", "kind", "note", "source", "wlan_id"],
    "wlans": ["ssid", "vlan_id", "band", "security", "note", "aps"],
    "integrations": ["kind", "name", "device_id", "config", "enabled"],
}
DEFAULTS = {"scan_interval_min": "60", "sync_interval_min": "15", "snmp_community": "public",
            "title": "LabVis"}


def conn():
    DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    return c


def init():
    with conn() as c:
        c.executescript(SCHEMA)
        if 'wlan_id' not in [r[1] for r in c.execute("PRAGMA table_info(links)")]:
            c.execute("ALTER TABLE links ADD COLUMN wlan_id INTEGER")
        if 'room' not in [r[1] for r in c.execute("PRAGMA table_info(devices)")]:
            c.execute("ALTER TABLE devices ADD COLUMN room TEXT")
        if 'role' not in [r[1] for r in c.execute("PRAGMA table_info(users)")]:
            c.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'admin'")
        for k, v in DEFAULTS.items():
            c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))


def _dec(row):
    d = dict(row)
    for k in JSON_COLS & d.keys():
        try:
            d[k] = json.loads(d[k]) if d[k] else ([] if k in LIST_COLS else {})
        except (TypeError, ValueError):
            d[k] = [] if k in LIST_COLS else {}
    return d


def _enc(v):
    return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v


def q(sql, params=()):
    with conn() as c:
        return [_dec(r) for r in c.execute(sql, params).fetchall()]


def one(sql, params=()):
    r = q(sql, params)
    return r[0] if r else None


def x(sql, params=()):
    with conn() as c:
        return c.execute(sql, tuple(_enc(p) for p in params)).lastrowid


def insert(table, data):
    cols = [k for k in data if k in COLUMNS.get(table, data.keys())] if table in COLUMNS else list(data)
    sql = f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))})"
    return x(sql, [data[k] for k in cols])


def update(table, rid, data):
    cols = [k for k in data if table not in COLUMNS or k in COLUMNS[table]]
    if not cols:
        return
    x(f"UPDATE {table} SET {','.join(k + '=?' for k in cols)} WHERE id=?", [data[k] for k in cols] + [rid])


def setting(key, default=None):
    r = one("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else DEFAULTS.get(key, default)


def settings():
    return {r["key"]: r["value"] for r in q("SELECT * FROM settings")}


def delete_device(did):
    """Löscht ein Gerät samt Kindern und Verbindungen. Ein Bereich (Typ group) gibt seine Geräte nur frei."""
    me = one("SELECT type FROM devices WHERE id=?", (did,))
    if me and me["type"] == "group":
        x("UPDATE devices SET parent_id=NULL, x=NULL, y=NULL WHERE parent_id=?", (did,))
    for ch in q("SELECT id FROM devices WHERE parent_id=?", (did,)):
        delete_device(ch["id"])
    x("DELETE FROM links WHERE a_id=? OR b_id=?", (did, did))
    x("UPDATE integrations SET device_id=NULL WHERE device_id=?", (did,))
    for w in q("SELECT id, aps FROM wlans"):
        if did in (w["aps"] or []):
            update("wlans", w["id"], {"aps": [a for a in w["aps"] if a != did]})
    x("DELETE FROM devices WHERE id=?", (did,))


def now():
    return time.time()

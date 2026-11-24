"""Automatische Sicherungen: Datenbank und hochgeladene Icons als .tar.gz in /data/backups.

- täglich zur eingestellten Stunde (Standard 3 Uhr), dazu vor jeder Wiederherstellung und vor jedem Update
- die Datenbank wird mit der SQLite-Backup-API kopiert, also konsistent auch bei laufendem Betrieb
- es bleiben die letzten N Sicherungen (Standard 14)

Zurückspielen (Container gestoppt):  rm -f data/homeatlas.db-wal data/homeatlas.db-shm
                                     tar -xzf data/backups/<datei> -C data
Von Hand im Container:               python -m app.backup [anlass]
"""
import io
import re
import sqlite3
import sys
import tarfile
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from . import db

DIR = db.DATA / "backups"
NAME = re.compile(r"^homeatlas-\d{8}-\d{6}(-[a-z]+)?\.tar\.gz$")
REASONS = {"auto", "manuell", "restore", "update"}
_lock = threading.Lock()
router = APIRouter(prefix="/api/backups")


def _keep():
    try:
        return max(1, min(365, int(db.setting("backup_keep") or 14)))
    except ValueError:
        return 14


def snapshot(reason="manuell"):
    """Legt eine Sicherung an und räumt alte auf. Gibt den Dateinamen zurück."""
    reason = reason if reason in REASONS else "manuell"
    with _lock:
        DIR.mkdir(parents=True, exist_ok=True)
        name = f"homeatlas-{datetime.now():%Y%m%d-%H%M%S}-{reason}.tar.gz"
        target, tmp = DIR / name, DIR / (name + ".part")
        with tempfile.TemporaryDirectory(dir=DIR) as td:
            copy = Path(td) / "homeatlas.db"
            src, dst = sqlite3.connect(db.DB, timeout=30), sqlite3.connect(copy)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
            with tarfile.open(tmp, "w:gz") as tar:
                tar.add(copy, arcname="homeatlas.db")
                icons = db.DATA / "uploads"
                if icons.is_dir():
                    tar.add(icons, arcname="uploads")
                info = tarfile.TarInfo("LIESMICH.txt")
                text = (f"HomeAtlas-Sicherung vom {datetime.now():%d.%m.%Y %H:%M} ({reason})\n"
                        "Zurückspielen: Container stoppen, dann im Projektordner\n"
                        "  rm -f data/homeatlas.db-wal data/homeatlas.db-shm\n"
                        "  tar -xzf data/backups/<diese Datei> -C data\n"
                        "und den Container wieder starten.\n").encode()
                info.size, info.mtime = len(text), int(time.time())
                tar.addfile(info, io.BytesIO(text))
        tmp.rename(target)
        prune()
        db.x("INSERT OR REPLACE INTO settings(key,value) VALUES('backup_last',?)", (str(db.now()),))
        return name


def prune():
    files = sorted(DIR.glob("homeatlas-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files[_keep():]:
        p.unlink(missing_ok=True)
    for p in DIR.glob("*.part"):                      # Reste abgebrochener Sicherungen
        if time.time() - p.stat().st_mtime > 3600:
            p.unlink(missing_ok=True)


def listing():
    if not DIR.is_dir():
        return []
    out = []
    for p in sorted(DIR.glob("homeatlas-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True):
        st = p.stat()
        m = re.search(r"-([a-z]+)\.tar\.gz$", p.name)
        out.append({"name": p.name, "size": st.st_size, "time": st.st_mtime, "reason": m.group(1) if m else "auto"})
    return out


def due(now=None):
    """Tägliche Sicherung fällig? Ab der eingestellten Stunde, wenn heute noch keine automatische lief."""
    if (db.setting("backup_enabled") or "1") != "1":
        return False
    now = datetime.fromtimestamp(now or time.time())
    try:
        hour = int(db.setting("backup_hour") or 3)
    except ValueError:
        hour = 3
    if now.hour < hour:
        return False
    today = now.strftime("%Y%m%d")
    return not any(b["name"].startswith(f"homeatlas-{today}-") and b["reason"] == "auto" for b in listing())


def loop():
    time.sleep(60)                                    # Start nicht mit einer Sicherung ausbremsen
    while True:
        try:
            if due():
                print("backup:", snapshot("auto"), flush=True)
        except Exception as e:  # noqa: BLE001 – der Takt darf nie abbrechen
            print("backup:", e, flush=True)
        time.sleep(300)


def _path(name):
    if not NAME.match(name or ""):
        raise HTTPException(400, "Ungültiger Dateiname")
    p = DIR / name
    if not p.is_file():
        raise HTTPException(404, "Sicherung nicht gefunden")
    return p


@router.get("")
def list_backups():
    files = listing()
    return {"backups": files, "keep": _keep(), "dir": str(DIR), "total": sum(f["size"] for f in files)}


@router.post("")
def create_backup():
    try:
        return {"name": snapshot("manuell")}
    except (OSError, sqlite3.Error) as e:
        raise HTTPException(500, f"Sicherung fehlgeschlagen: {e}") from e


@router.get("/{name}")
def download(name: str):
    return FileResponse(_path(name), filename=name, media_type="application/gzip")


@router.delete("/{name}")
def delete(name: str):
    _path(name).unlink()
    return {"ok": True}


if __name__ == "__main__":
    print(snapshot(sys.argv[1] if len(sys.argv) > 1 else "manuell"))

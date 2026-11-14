"""Anmeldung: Benutzerkonten (scrypt-Hash), Sitzungen per HttpOnly-Cookie, Login-Bremse.

Rechte:  read  – alles ansehen
         write – zusätzlich dokumentieren, scannen, Anbindungen pflegen
         admin – zusätzlich Benutzer, Systemeinstellungen, Export/Wiederherstellen
"""
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlparse

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from . import db

COOKIE = "labvis_session"
TTL = 30 * 86400
MIN_LEN = 10
PUBLIC = {"/healthz", "/login", "/api/auth/status", "/api/auth/login", "/api/auth/setup"}
ROLES = ("read", "write", "admin")
SELF_SERVICE = {"/api/auth/logout", "/api/auth/password"}          # darf jedes Konto
ADMIN_ONLY = ("/api/auth/users", "/api/export", "/api/restore", "/api/settings/save")
_fails = {}          # ip -> [anzahl, gesperrt_bis]
router = APIRouter(prefix="/api/auth")


def hash_pw(pw, salt=None):
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_pw(pw, stored):
    try:
        _, salt, _ = stored.split("$")
        return hmac.compare_digest(hash_pw(pw, bytes.fromhex(salt)), stored)
    except (ValueError, AttributeError):
        return False


_DUMMY = hash_pw(secrets.token_hex(8))   # gleicher Rechenaufwand bei unbekanntem Benutzer


def _th(token):
    return hashlib.sha256(token.encode()).hexdigest()


def has_users():
    return db.one("SELECT count(*) c FROM users")["c"] > 0


def bootstrap():
    """Erstes Konto aus der Umgebung anlegen (LABVIS_USER / LABVIS_PASSWORD), falls noch keines existiert."""
    pw = os.environ.get("LABVIS_PASSWORD", "")
    if pw and not has_users():
        db.x("INSERT INTO users(username,pw,role,created) VALUES(?,?,'admin',?)",
             (os.environ.get("LABVIS_USER") or "admin", hash_pw(pw), db.now()))
    db.x("DELETE FROM sessions WHERE expires<?", (db.now(),))


def current_user(request):
    tok = request.cookies.get(COOKIE)
    if not tok:
        return None
    return db.one("SELECT u.id, u.username, u.role FROM sessions s JOIN users u ON u.id=s.user_id "
                  "WHERE s.token_hash=? AND s.expires>?", (_th(tok), db.now()))


def _secure(request):
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"


def _start_session(request, user_id):
    tok = secrets.token_urlsafe(32)
    db.x("INSERT INTO sessions(token_hash,user_id,created,expires,ua) VALUES(?,?,?,?,?)",
         (_th(tok), user_id, db.now(), db.now() + TTL, (request.headers.get("user-agent") or "")[:200]))
    db.x("UPDATE users SET last_login=? WHERE id=?", (db.now(), user_id))
    resp = JSONResponse({"ok": True})
    resp.set_cookie(COOKIE, tok, max_age=TTL, httponly=True, samesite="strict", secure=_secure(request), path="/")
    return resp


def _valid(username, password):
    username = (username or "").strip()
    if not 2 <= len(username) <= 40:
        raise HTTPException(400, "Benutzername: 2 bis 40 Zeichen")
    if len(password or "") < MIN_LEN:
        raise HTTPException(400, f"Das Passwort braucht mindestens {MIN_LEN} Zeichen")
    return username


async def middleware(request: Request, call_next):
    path = request.url.path
    # Schreibzugriffe nur von der eigenen Seite (zusätzlich zum SameSite-Cookie)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "Fremde Herkunft abgelehnt"}, 403)
    if path in PUBLIC or path.startswith("/static/"):
        return await call_next(request)
    user = current_user(request)
    if not user:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Nicht angemeldet"}, 401)
        return RedirectResponse("/login", 303)
    if path not in SELF_SERVICE:
        if user["role"] == "read" and request.method not in ("GET", "HEAD", "OPTIONS"):
            return JSONResponse({"detail": "Dieses Konto hat nur Leserechte"}, 403)
        if user["role"] != "admin" and path.startswith(ADMIN_ONLY):
            return JSONResponse({"detail": "Dafür sind Admin-Rechte nötig"}, 403)
    request.state.user = user
    return await call_next(request)


@router.get("/status")
def status(request: Request):
    u = current_user(request)
    return {"setup": not has_users(), "user": u["username"] if u else None,
            "role": u["role"] if u else None, "min_len": MIN_LEN}


@router.post("/setup")
def setup(request: Request, data: dict = Body(...)):
    if has_users():
        raise HTTPException(403, "Die Einrichtung ist bereits abgeschlossen")
    name = _valid(data.get("username"), data.get("password"))
    uid = db.x("INSERT INTO users(username,pw,role,created) VALUES(?,?,'admin',?)", (name, hash_pw(data["password"]), db.now()))
    return _start_session(request, uid)


@router.post("/login")
def login(request: Request, data: dict = Body(...)):
    ip = request.client.host if request.client else "?"
    n, until = _fails.get(ip, [0, 0])
    if until > time.time():
        raise HTTPException(429, f"Zu viele Fehlversuche – bitte {int(until - time.time()) + 1} Sekunden warten")
    u = db.one("SELECT * FROM users WHERE username=?", ((data.get("username") or "").strip(),))
    ok = check_pw(data.get("password") or "", u["pw"] if u else _DUMMY) and bool(u)
    if not ok:
        n += 1
        _fails[ip] = [n, time.time() + min(900, 30 * 2 ** (n - 5)) if n >= 5 else 0]
        raise HTTPException(401, "Benutzername oder Passwort stimmt nicht")
    _fails.pop(ip, None)
    return _start_session(request, u["id"])


@router.post("/logout")
def logout(request: Request):
    tok = request.cookies.get(COOKIE)
    if tok:
        db.x("DELETE FROM sessions WHERE token_hash=?", (_th(tok),))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@router.post("/password")
def password(request: Request, data: dict = Body(...)):
    me = db.one("SELECT * FROM users WHERE id=?", (request.state.user["id"],))
    if not check_pw(data.get("current") or "", me["pw"]):
        raise HTTPException(400, "Das aktuelle Passwort stimmt nicht")
    _valid(me["username"], data.get("new"))
    db.x("UPDATE users SET pw=? WHERE id=?", (hash_pw(data["new"]), me["id"]))
    # alle anderen Sitzungen dieses Kontos beenden
    db.x("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (me["id"], _th(request.cookies.get(COOKIE, ""))))
    return {"ok": True}


@router.get("/users")
def users(request: Request):
    rows = db.q("SELECT id, username, role, created, last_login FROM users ORDER BY id")
    return {"users": rows, "me": request.state.user["id"]}


def _role(data, default=None):
    role = data.get("role") or default
    if role not in ROLES:
        raise HTTPException(400, "Unbekanntes Recht")
    return role


def _last_admin(uid):
    u = db.one("SELECT role FROM users WHERE id=?", (uid,))
    return bool(u) and u["role"] == "admin" and db.one("SELECT count(*) c FROM users WHERE role='admin'")["c"] <= 1


@router.post("/users")
def add_user(data: dict = Body(...)):
    name = _valid(data.get("username"), data.get("password"))
    if db.one("SELECT id FROM users WHERE username=?", (name,)):
        raise HTTPException(400, "Diesen Benutzernamen gibt es schon")
    return {"id": db.x("INSERT INTO users(username,pw,role,created) VALUES(?,?,?,?)",
                       (name, hash_pw(data["password"]), _role(data, "read"), db.now()))}


@router.put("/users/{uid}")
def change_user(uid: int, request: Request, data: dict = Body(...)):
    u = db.one("SELECT * FROM users WHERE id=?", (uid,))
    if not u:
        raise HTTPException(404, "Benutzer nicht gefunden")
    if data.get("role") and data["role"] != u["role"]:
        if uid == request.state.user["id"]:
            raise HTTPException(400, "Das eigene Recht lässt sich nicht ändern")
        if _role(data) != "admin" and _last_admin(uid):
            raise HTTPException(400, "Es muss mindestens ein Admin-Konto bleiben")
        db.x("UPDATE users SET role=? WHERE id=?", (data["role"], uid))
    if data.get("password"):
        _valid(u["username"], data["password"])
        db.x("UPDATE users SET pw=? WHERE id=?", (hash_pw(data["password"]), uid))
        if uid != request.state.user["id"]:
            db.x("DELETE FROM sessions WHERE user_id=?", (uid,))
    return {"ok": True}


@router.delete("/users/{uid}")
def del_user(uid: int, request: Request):
    if uid == request.state.user["id"]:
        raise HTTPException(400, "Das eigene Konto lässt sich nicht löschen")
    if _last_admin(uid):
        raise HTTPException(400, "Es muss mindestens ein Admin-Konto bleiben")
    db.x("DELETE FROM sessions WHERE user_id=?", (uid,))
    db.x("DELETE FROM users WHERE id=?", (uid,))
    return {"ok": True}


def login_page(request: Request, render):
    if current_user(request):
        return RedirectResponse("/", 303)
    return render("login.html")

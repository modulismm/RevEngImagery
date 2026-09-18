"""Imagery (self-hosted) -- Flask application.

A replacement for the Base44-hosted "Imagery": an image plus sound zones that
play as the cursor moves over them. The audio behaviour is reproduced exactly
from the original; see ../docs/schema.md.

Roles: a `user` sees their own canvases; an `admin` sees every canvas from every
account, which is the "total view of all galleries" the deployment needs.
"""
import functools
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time

from flask import (Flask, g, jsonify, request, send_file, send_from_directory,
                   make_response)

from . import auth, db, files

UPLOAD_DIR = os.environ.get("IMAGERY_UPLOADS", "/data/uploads")
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
COOKIE = "imagery_session"
MAX_BODY = 26 * 1024 * 1024


def create_app():
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = MAX_BODY
    app.secret_key = _secret_key()

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(db.DB_PATH) or ".", exist_ok=True)
    with db.connect() as conn:
        db.migrate(conn)
        auth.purge_expired(conn)
        _seed_admin(conn)

    _register(app)
    return app


def _secret_key():
    """Persist a key so sessions survive a restart. Generated on first boot."""
    path = os.environ.get("IMAGERY_SECRET_FILE", "/data/secret_key")
    env = os.environ.get("IMAGERY_SECRET_KEY")
    if env:
        return env.encode()
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        key = secrets.token_bytes(32)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600), "wb") as fh:
            fh.write(key)
        return key


def _seed_admin(conn):
    """Create the first admin from the environment, once, if no user exists.

    Every gunicorn worker runs this at boot, so the check and the insert race
    against each other. `BEGIN IMMEDIATE` takes the write lock up front, which
    serialises the workers, and the IntegrityError guard covers the case where
    another process committed between our connection opening and the lock.
    """
    name = os.environ.get("IMAGERY_ADMIN", "admin")
    phrase = os.environ.get("IMAGERY_ADMIN_PASSPHRASE")
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM user LIMIT 1").fetchone():
            conn.rollback()
            return
        uid, token = auth.create_user(conn, name, name, role="admin", passphrase=phrase)
    except sqlite3.IntegrityError:
        conn.rollback()
        return
    except sqlite3.OperationalError:
        # Another worker holds the write lock and is seeding right now.
        conn.rollback()
        return
    if token:
        print(f"\n  First run: open /setup/{token} to choose a passphrase for '{name}'.\n",
              flush=True)


# --------------------------------------------------------------------------- #
# Request plumbing
# --------------------------------------------------------------------------- #

def _conn():
    if "conn" not in g:
        g.conn = db.connect()
    return g.conn


def _csrf_for(token: str) -> str:
    from flask import current_app
    return hmac.new(current_app.secret_key, token.encode(), hashlib.sha256).hexdigest()[:32]


def _client_ip() -> str:
    # Behind nginx-proxy-manager, the real address is the last hop in X-Forwarded-For.
    fwd = request.headers.get("X-Forwarded-For", "")
    return (fwd.split(",")[-1].strip() if fwd else request.remote_addr) or "?"


def current_user():
    if "user" not in g:
        g.user = auth.user_for_session(_conn(), request.cookies.get(COOKIE, ""))
    return g.user


def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        if not current_user():
            return jsonify(error="Please sign in again."), 401
        return fn(*a, **kw)
    return wrapper


def admin_required(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        if not auth.is_admin(current_user()):
            return jsonify(error="That area is for administrators."), 403
        return fn(*a, **kw)
    return wrapper


def _register(app):

    @app.teardown_appcontext
    def _close(_exc):
        conn = g.pop("conn", None)
        if conn:
            conn.close()

    @app.before_request
    def _csrf_guard():
        """Mutating requests must carry the session-derived CSRF token.

        Combined with SameSite=Lax cookies this is belt and braces: a cross-site
        form cannot set a custom header, and a cross-site fetch cannot read the
        token.
        """
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        if request.path.startswith(("/api/login", "/api/setup")):
            return None
        token = request.cookies.get(COOKIE, "")
        if not token or not hmac.compare_digest(
                request.headers.get("X-CSRF-Token", ""), _csrf_for(token)):
            return jsonify(error="Your session expired. Please sign in again."), 403
        return None

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
            "script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; base-uri 'none'; form-action 'self'; "
            "frame-ancestors 'self'")
        return resp

    # ----------------------------------------------------------------- auth --
    @app.post("/api/login")
    def login():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        phrase = data.get("passphrase") or ""
        trusted = bool(data.get("trusted", True))
        conn, ip = _conn(), _client_ip()

        delay = auth.throttle_delay(auth.failed_recently(conn, name, ip))
        if delay:
            time.sleep(min(delay, 3.0))
            if delay >= auth._MAX_DELAY:
                return jsonify(error="Too many tries just now. Please wait a minute, "
                                     "then try again."), 429

        row = conn.execute("SELECT * FROM user WHERE name = ? COLLATE NOCASE",
                           (name,)).fetchone()
        ok = bool(row) and auth.verify_passphrase(phrase, row["pass_hash"])
        auth.record_attempt(conn, name, ip, ok)
        if not ok:
            # Same message either way: never reveal whether the name exists.
            return jsonify(error="That name and passphrase do not match. "
                                 "Check for a stray capital letter or space."), 401

        token, expires = auth.create_session(conn, row["id"], trusted,
                                             request.headers.get("User-Agent", ""))
        resp = make_response(jsonify(user=_user_json(row), csrf=_csrf_for(token)))
        _set_cookie(resp, token, expires)
        return resp

    @app.post("/api/logout")
    def logout():
        auth.destroy_session(_conn(), request.cookies.get(COOKIE, ""))
        resp = make_response(jsonify(ok=True))
        resp.delete_cookie(COOKIE, path="/", samesite="Lax")
        return resp

    @app.get("/api/me")
    def me():
        user = current_user()
        if not user:
            return jsonify(user=None)
        return jsonify(user=_user_json(user),
                       csrf=_csrf_for(request.cookies.get(COOKIE, "")))

    @app.post("/api/setup/<token>")
    def setup(token):
        """Complete first-time sign-in from a one-time link."""
        conn = _conn()
        row = conn.execute("SELECT * FROM user WHERE setup_token = ?", (token,)).fetchone()
        if not row:
            return jsonify(error="That link has already been used, or is not valid."), 404
        phrase = (request.get_json(silent=True) or {}).get("passphrase") or ""
        problem = auth.passphrase_problem(phrase, row["name"])
        if problem:
            return jsonify(error=problem), 400
        auth.set_passphrase(conn, row["id"], phrase)
        stoken, expires = auth.create_session(conn, row["id"], True,
                                              request.headers.get("User-Agent", ""))
        resp = make_response(jsonify(user=_user_json(row), csrf=_csrf_for(stoken)))
        _set_cookie(resp, stoken, expires)
        return resp

    @app.post("/api/passphrase")
    @login_required
    def change_passphrase():
        data = request.get_json(silent=True) or {}
        user = current_user()
        if not auth.verify_passphrase(data.get("current") or "", user["pass_hash"]):
            return jsonify(error="That is not your current passphrase."), 403
        new = data.get("passphrase") or ""
        problem = auth.passphrase_problem(new, user["name"])
        if problem:
            return jsonify(error=problem), 400
        auth.set_passphrase(_conn(), user["id"], new)
        resp = make_response(jsonify(ok=True, signed_out=True))
        resp.delete_cookie(COOKIE, path="/", samesite="Lax")
        return resp

    # -------------------------------------------------------------- canvases --
    @app.get("/api/canvases")
    @login_required
    def list_canvases():
        """Own canvases, or every canvas when an admin asks for all."""
        user, conn = current_user(), _conn()
        want_all = request.args.get("all") == "1" and auth.is_admin(user)
        if want_all:
            rows = conn.execute(
                "SELECT c.*, u.display_name AS owner_name FROM canvas c "
                "JOIN user u ON u.id = c.owner_id ORDER BY c.updated_at DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT c.*, u.display_name AS owner_name FROM canvas c "
                "JOIN user u ON u.id = c.owner_id "
                "WHERE c.owner_id = ? ORDER BY c.updated_at DESC", (user["id"],)).fetchall()
        return jsonify(canvases=[_canvas_json(r) for r in rows], scope="all" if want_all else "mine")

    @app.get("/api/canvases/<cid>")
    def get_canvas(cid):
        row = _canvas_or_none(cid)
        if row is None:
            return jsonify(error="That canvas was not found."), 404
        return jsonify(canvas=_canvas_json(row, full=True))

    @app.post("/api/canvases")
    @login_required
    def create_canvas():
        data = request.get_json(silent=True) or {}
        user, conn = current_user(), _conn()
        cid = db.new_id()
        conn.execute(
            "INSERT INTO canvas (id, owner_id, name, description, image_path, zones, "
            "published, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (cid, user["id"], (data.get("name") or "Untitled").strip()[:120],
             (data.get("description") or "")[:2000], data.get("image_path"),
             json.dumps(_clean_zones(data.get("zones") or [])),
             1 if data.get("published") else 0, db.now(), db.now()))
        conn.commit()
        return jsonify(canvas=_canvas_json(_canvas_or_none(cid), full=True)), 201

    @app.put("/api/canvases/<cid>")
    @login_required
    def update_canvas(cid):
        row, conn = _canvas_or_none(cid), _conn()
        if row is None:
            return jsonify(error="That canvas was not found."), 404
        if not _may_edit(row):
            return jsonify(error="That canvas belongs to someone else."), 403
        data = request.get_json(silent=True) or {}
        conn.execute(
            "UPDATE canvas SET name=?, description=?, image_path=?, zones=?, "
            "published=?, room_id=?, updated_at=? WHERE id=?",
            ((data.get("name") or row["name"]).strip()[:120],
             (data.get("description") if data.get("description") is not None
              else row["description"] or "")[:2000],
             data.get("image_path") if data.get("image_path") is not None else row["image_path"],
             json.dumps(_clean_zones(data.get("zones")
                                     if data.get("zones") is not None
                                     else json.loads(row["zones"]))),
             1 if data.get("published", row["published"]) else 0,
             data.get("room_id", row["room_id"]), db.now(), cid))
        conn.commit()
        return jsonify(canvas=_canvas_json(_canvas_or_none(cid), full=True))

    @app.delete("/api/canvases/<cid>")
    @login_required
    def delete_canvas(cid):
        row = _canvas_or_none(cid)
        if row is None:
            return jsonify(error="That canvas was not found."), 404
        if not _may_edit(row):
            return jsonify(error="That canvas belongs to someone else."), 403
        _conn().execute("DELETE FROM canvas WHERE id = ?", (cid,))
        _conn().commit()
        return jsonify(ok=True)

    # ---------------------------------------------------------------- upload --
    @app.post("/api/upload/<kind>")
    @login_required
    def upload(kind):
        if kind not in ("image", "audio"):
            return jsonify(error="Unknown upload type."), 400
        blob = request.files.get("file")
        if not blob:
            return jsonify(error="No file was sent."), 400
        try:
            rel, mime = files.store(blob.read(), kind, UPLOAD_DIR)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        return jsonify(path=rel, mime=mime, url=f"/media/{rel}"), 201

    @app.get("/media/<path:rel>")
    def media(rel):
        target = files.safe_join(UPLOAD_DIR, rel)
        if not target:
            return jsonify(error="Not found."), 404
        return send_file(target, conditional=True, max_age=31536000)

    # ----------------------------------------------------------------- admin --
    @app.get("/api/users")
    @admin_required
    def list_users():
        rows = _conn().execute(
            "SELECT u.*, (SELECT COUNT(*) FROM canvas c WHERE c.owner_id = u.id) AS canvases "
            "FROM user u ORDER BY u.created_at").fetchall()
        return jsonify(users=[_user_json(r, admin_view=True) for r in rows])

    @app.post("/api/users")
    @admin_required
    def add_user():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        problem = auth.name_problem(name)
        if problem:
            return jsonify(error=problem), 400
        conn = _conn()
        if conn.execute("SELECT 1 FROM user WHERE name = ? COLLATE NOCASE", (name,)).fetchone():
            return jsonify(error="Someone already uses that name."), 409
        role = "admin" if data.get("role") == "admin" else "user"
        try:
            _uid, token = auth.create_user(conn, name, data.get("display_name") or name, role)
        except sqlite3.IntegrityError:
            # Lost a race against a concurrent request using the same name.
            return jsonify(error="Someone already uses that name."), 409
        return jsonify(setup_url=f"/setup/{token}", name=name, role=role), 201

    # ------------------------------------------------------------ static app --
    @app.get("/")
    @app.get("/setup/<path:_t>")
    @app.get("/canvas/<path:_t>")
    @app.get("/gallery")
    def index(_t=None):
        resp = send_from_directory(STATIC_DIR, "index.html")
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp

    @app.get("/static/<path:rel>")
    def static_files(rel):
        # max_age=0 means "revalidate", not "re-download": Flask still sends an
        # ETag, so an unchanged file answers 304. A long max_age here meant a
        # deploy could stay invisible for an hour, which is worse than the
        # handful of conditional requests this costs.
        resp = send_from_directory(STATIC_DIR, rel, max_age=0, conditional=True)
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp

    @app.get("/healthz")
    def healthz():
        return jsonify(ok=True)

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify(error="That file is too large."), 413


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _set_cookie(resp, token, expires):
    resp.set_cookie(
        COOKIE, token, httponly=True, samesite="Lax",
        secure=os.environ.get("IMAGERY_SECURE_COOKIE", "1") == "1",
        expires=expires, path="/")


def _user_json(row, admin_view=False):
    out = {"id": row["id"], "name": row["name"],
           "display_name": row["display_name"], "role": row["role"]}
    if admin_view:
        out["canvases"] = row["canvases"] if "canvases" in row.keys() else 0
        out["created_at"] = row["created_at"]
        out["last_seen_at"] = row["last_seen_at"]
        out["needs_setup"] = row["pass_hash"] is None
    return out


def _canvas_json(row, full=False):
    out = {"id": row["id"], "name": row["name"], "description": row["description"],
           "image_url": f"/media/{row['image_path']}" if row["image_path"] else None,
           "image_path": row["image_path"], "published": bool(row["published"]),
           "room_id": row["room_id"], "owner_id": row["owner_id"],
           "owner_name": row["owner_name"] if "owner_name" in row.keys() else None,
           "created_at": row["created_at"], "updated_at": row["updated_at"]}
    zones = json.loads(row["zones"] or "[]")
    out["sound_count"] = len(zones)
    if full:
        out["zones"] = zones
    return out


_ZONE_NUM = {"x": (0.0, 100.0), "y": (0.0, 100.0), "radius": (20.0, 100000.0),
             "volume": (0.0, 1.0), "startTime": (0.0, 86400.0), "endTime": (0.0, 86400.0)}
_FX_NUM = {"reverbLevel": (0.0, 100.0), "pitch": (-12.0, 12.0),
           "lowFreq": (-40.0, 40.0), "midFreq": (-40.0, 40.0), "highFreq": (-40.0, 40.0)}


def _clean_zones(zones):
    """Clamp everything the client sends. The zone shape matches the original app."""
    out = []
    for z in (zones or [])[:200]:
        if not isinstance(z, dict):
            continue
        kind = "generated" if z.get("type") == "generated" else "custom"
        clean = {"id": str(z.get("id") or db.new_id())[:64],
                 "sound_name": str(z.get("sound_name") or "")[:120],
                 "type": kind,
                 # A generated zone is synthesised in the browser from its name,
                 # so it carries no media of its own.
                 "url": None if kind == "generated" else _clean_media_url(z.get("url"))}
        for key, (lo, hi) in _ZONE_NUM.items():
            clean[key] = _clamp(z.get(key), lo, hi, 0.0 if key != "radius" else 200.0)
        fx = z.get("effects") if isinstance(z.get("effects"), dict) else {}
        clean["effects"] = {k: _clamp(fx.get(k), lo, hi, 0.0) for k, (lo, hi) in _FX_NUM.items()}
        clean["effects"]["isReversed"] = bool(fx.get("isReversed"))
        out.append(clean)
    return out


# Uploads live under /media/; the shipped sound bank is a static asset.
_ALLOWED_URL_PREFIXES = ("/media/", "/static/sounds/")


def _clean_media_url(url):
    """Keep only same-origin references, so a zone cannot point at another host.

    Rejects protocol-relative ("//evil.example/x") and traversal forms as well as
    absolute URLs -- anything that is not one of our own two prefixes.
    """
    if not isinstance(url, str):
        return None
    if ".." in url or url.startswith("//"):
        return None
    if not any(url.startswith(prefix) for prefix in _ALLOWED_URL_PREFIXES):
        return None
    return url[:300]


def _clamp(value, lo, hi, default):
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def _canvas_or_none(cid):
    return _conn().execute(
        "SELECT c.*, u.display_name AS owner_name FROM canvas c "
        "JOIN user u ON u.id = c.owner_id WHERE c.id = ?", (cid,)).fetchone()


def _may_edit(row):
    user = current_user()
    return bool(user) and (row["owner_id"] == user["id"] or auth.is_admin(user))


app = create_app() if os.environ.get("IMAGERY_EAGER") else None

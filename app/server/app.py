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
GALLERY_COOKIE = "imagery_gallery"
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


def gallery_token():
    """The browser's gallery-access token, minted on first use."""
    if "gallery_token" not in g:
        g.gallery_token = request.cookies.get(GALLERY_COOKIE) or secrets.token_urlsafe(24)
        g.gallery_token_is_new = GALLERY_COOKIE not in request.cookies
    return g.gallery_token


def may_view_canvas(row):
    """Owner, admin, or a browser that has entered this gallery's PIN."""
    user = current_user()
    if user and (row["owner_id"] == user["id"] or auth.is_admin(user)):
        return True
    if row["room_id"]:
        if user and user["group_id"] == row["room_id"]:
            return True                      # a member of that group
        return auth.has_gallery(_conn(), request.cookies.get(GALLERY_COOKIE, ""), row["room_id"])
    return False


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
        # Endpoints reached by someone who has no session yet, so there is no
        # session-derived token for them to present. Each is rate limited, and a
        # cross-origin caller cannot read the reply.
        if request.path.startswith(("/api/login", "/api/setup")):
            return None
        if request.path.startswith("/api/g/") and \
                request.path.rsplit("/", 1)[-1] in ("unlock", "join"):
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
        """Sign out, and give up gallery access with it.

        These iPads are shared and passed along: signing out is the moment the
        device changes hands. Leaving the gallery unlocked would hand the next
        person the group's pictures and recordings without them entering the
        code. Re-entering it is a few taps; the facilitator has it.
        """
        conn = _conn()
        auth.destroy_session(conn, request.cookies.get(COOKIE, ""))
        token = request.cookies.get(GALLERY_COOKIE, "")
        if token:
            conn.execute("DELETE FROM gallery_access WHERE token = ?", (token,))
            conn.commit()
        resp = make_response(jsonify(ok=True))
        resp.delete_cookie(COOKIE, path="/", samesite="Lax")
        resp.delete_cookie(GALLERY_COOKIE, path="/", samesite="Lax")
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
        if not may_view_canvas(row):
            # Same answer as "no such canvas": whether an id exists is not
            # something an unauthorised caller should be able to learn.
            return jsonify(error="That canvas was not found."), 404
        return jsonify(canvas=_canvas_json(row, full=True))

    @app.post("/api/canvases")
    @login_required
    def create_canvas():
        data = request.get_json(silent=True) or {}
        user, conn = current_user(), _conn()
        cid = db.new_id()
        # A participant's work belongs to their group automatically: they never
        # see a gallery picker, and their pictures must reach the group anyway.
        room_id = data.get("room_id")
        if user["role"] == "participant":
            room_id = user["group_id"]
        conn.execute(
            "INSERT INTO canvas (id, owner_id, name, description, image_path, zones, "
            "published, room_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cid, user["id"], (data.get("name") or "Untitled").strip()[:120],
             (data.get("description") or "")[:2000], data.get("image_path"),
             json.dumps(_clean_zones(data.get("zones") or [], user["id"])),
             1 if data.get("published") else 0, room_id, db.now(), db.now()))
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
                                     else json.loads(row["zones"]),
                                     row["owner_id"])),
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
        conn = _conn()
        conn.execute("INSERT OR REPLACE INTO upload (path, owner_id, kind, created_at) "
                     "VALUES (?,?,?,?)", (rel, current_user()["id"], kind, db.now()))
        conn.commit()
        return jsonify(path=rel, mime=mime, url=f"/media/{rel}"), 201

    @app.get("/media/<path:rel>")
    def media(rel):
        """Serve an upload, if the caller is allowed to hear it.

        Previously this was open: a recording was only as private as its URL,
        and a URL leaks through a shared link, a browser history or a log. A
        participant's voice is not public just because someone has the address.
        """
        target = files.safe_join(UPLOAD_DIR, rel)
        if not target:
            return jsonify(error="Not found."), 404
        if not _may_fetch_upload(rel):
            return jsonify(error="Not found."), 404
        resp = send_file(target, conditional=True, max_age=0)
        # Personal media must not sit in a shared cache.
        resp.headers["Cache-Control"] = "private, no-store"
        return resp

    # -------------------------------------------------------------- galleries --
    @app.get("/api/galleries")
    @login_required
    def list_galleries():
        user, conn = current_user(), _conn()
        if auth.is_admin(user):
            rows = conn.execute(
                "SELECT r.*, (SELECT COUNT(*) FROM canvas c WHERE c.room_id = r.id) AS canvases "
                "FROM room r ORDER BY r.created_at").fetchall()
        else:
            rows = conn.execute(
                "SELECT r.*, (SELECT COUNT(*) FROM canvas c WHERE c.room_id = r.id) AS canvases "
                "FROM room r WHERE r.owner_id = ? ORDER BY r.created_at", (user["id"],)).fetchall()
        return jsonify(galleries=[_gallery_json(r, manage=True) for r in rows])

    @app.post("/api/galleries")
    @login_required
    def create_gallery():
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        if not 2 <= len(title) <= 80:
            return jsonify(error="Please give the gallery a name."), 400
        pin = (data.get("pin") or "").strip()
        problem = auth.pin_problem(pin)
        if problem:
            return jsonify(error=problem), 400

        conn, rid = _conn(), db.new_id()
        slug = auth.slugify(title, rid[:8])
        # Slugs are unique; fall back to a suffix rather than refusing the name.
        if conn.execute("SELECT 1 FROM room WHERE slug = ?", (slug,)).fetchone():
            slug = f"{slug}-{rid[:6]}"
        conn.execute(
            "INSERT INTO room (id, owner_id, title, subtitle, slug, pin_hash, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (rid, current_user()["id"], title, (data.get("subtitle") or "")[:300],
             slug, auth.hash_pin(pin), db.now()))
        conn.commit()
        row = conn.execute("SELECT r.*, 0 AS canvases FROM room r WHERE r.id = ?", (rid,)).fetchone()
        return jsonify(gallery=_gallery_json(row, manage=True)), 201

    @app.put("/api/galleries/<rid>")
    @login_required
    def update_gallery(rid):
        conn = _conn()
        row = conn.execute("SELECT * FROM room WHERE id = ?", (rid,)).fetchone()
        if row is None:
            return jsonify(error="That gallery was not found."), 404
        if not _may_manage_gallery(row):
            return jsonify(error="That gallery belongs to someone else."), 403
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or row["title"]).strip()[:80]
        subtitle = (data.get("subtitle") if data.get("subtitle") is not None
                    else row["subtitle"] or "")[:300]
        pin = (data.get("pin") or "").strip()
        if pin:
            problem = auth.pin_problem(pin)
            if problem:
                return jsonify(error=problem), 400
            conn.execute("UPDATE room SET pin_hash = ? WHERE id = ?", (auth.hash_pin(pin), rid))
            # A new code means the old one stops working everywhere.
            auth.revoke_gallery_tokens(conn, rid)
        conn.execute("UPDATE room SET title = ?, subtitle = ? WHERE id = ?", (title, subtitle, rid))
        conn.commit()
        row = conn.execute(
            "SELECT r.*, (SELECT COUNT(*) FROM canvas c WHERE c.room_id = r.id) AS canvases "
            "FROM room r WHERE r.id = ?", (rid,)).fetchone()
        return jsonify(gallery=_gallery_json(row, manage=True))

    @app.delete("/api/galleries/<rid>")
    @login_required
    def delete_gallery(rid):
        conn = _conn()
        row = conn.execute("SELECT * FROM room WHERE id = ?", (rid,)).fetchone()
        if row is None:
            return jsonify(error="That gallery was not found."), 404
        if not _may_manage_gallery(row):
            return jsonify(error="That gallery belongs to someone else."), 403
        # Canvases survive; they simply return to no gallery (ON DELETE SET NULL).
        conn.execute("DELETE FROM room WHERE id = ?", (rid,))
        conn.commit()
        return jsonify(ok=True)

    @app.get("/api/g/<slug>")
    def gallery_public(slug):
        """What a visitor may know before entering the code: the name, nothing else."""
        row = _conn().execute("SELECT * FROM room WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            return jsonify(error="That gallery was not found."), 404
        unlocked = (auth.has_gallery(_conn(), request.cookies.get(GALLERY_COOKIE, ""), row["id"])
                    or _may_manage_gallery(row))
        return jsonify(gallery=_gallery_json(row), unlocked=unlocked)

    @app.post("/api/g/<slug>/unlock")
    def gallery_unlock(slug):
        conn, ip = _conn(), _client_ip()
        row = conn.execute("SELECT * FROM room WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            return jsonify(error="That gallery was not found."), 404

        bucket = f"gallery:{row['id']}"
        delay = auth.pin_delay(auth.failed_recently(conn, bucket, ip))
        if delay:
            time.sleep(min(delay, 3.0))
            if delay >= auth._PIN_MAX_DELAY:
                return jsonify(error="Too many tries. Please wait a minute and try again."), 429

        pin = ((request.get_json(silent=True) or {}).get("pin") or "").strip()
        ok = bool(row["pin_hash"]) and auth.verify_pin(pin, row["pin_hash"])
        auth.record_attempt(conn, bucket, ip, ok)
        if not ok:
            return jsonify(error="That code is not right."), 401

        token = gallery_token()
        expires = auth.grant_gallery(conn, token, row["id"])
        resp = make_response(jsonify(gallery=_gallery_json(row), unlocked=True))
        resp.set_cookie(GALLERY_COOKIE, token, httponly=True, samesite="Lax",
                        secure=os.environ.get("IMAGERY_SECURE_COOKIE", "1") == "1",
                        expires=expires, path="/")
        return resp

    @app.post("/api/g/<slug>/join")
    def gallery_join(slug):
        """Claim a name inside a group, or sign back in to it.

        Participants have no accounts beforehand: the facilitator creates the
        group, reads out its code, and each person chooses how they are known
        and a passphrase. The group code must already have been entered.
        """
        conn = _conn()
        room = conn.execute("SELECT * FROM room WHERE slug = ?", (slug,)).fetchone()
        if room is None:
            return jsonify(error="That gallery was not found."), 404
        if not auth.has_gallery(conn, request.cookies.get(GALLERY_COOKIE, ""), room["id"]):
            return jsonify(error="Please enter the code for this gallery first."), 403

        data = request.get_json(silent=True) or {}
        display = (data.get("display_name") or "").strip()
        problem = auth.participant_name_problem(display)
        if problem:
            return jsonify(error=problem), 400
        phrase = data.get("passphrase") or ""
        key = auth.participant_key(slug, display)
        ip = _client_ip()

        row = conn.execute("SELECT * FROM user WHERE name = ? COLLATE NOCASE", (key,)).fetchone()
        if row is not None:
            # The name is taken: this is a returning participant signing in.
            delay = auth.throttle_delay(auth.failed_recently(conn, key, ip))
            if delay:
                time.sleep(min(delay, 3.0))
            ok = auth.verify_passphrase(phrase, row["pass_hash"])
            auth.record_attempt(conn, key, ip, ok)
            if not ok:
                return jsonify(error="That name is already used in this group, and the "
                                     "passphrase does not match. Try a different name, or "
                                     "check the passphrase."), 401
        else:
            problem = auth.passphrase_problem(phrase, display)
            if problem:
                return jsonify(error=problem), 400
            if not data.get("consent"):
                return jsonify(error="Please tick the box to continue."), 400
            uid, _token = auth.create_user(conn, key, display, role="participant",
                                           passphrase=phrase)
            conn.execute("UPDATE user SET group_id = ?, consent_at = ? WHERE id = ?",
                         (room["id"], time.time(), uid))
            conn.commit()
            row = conn.execute("SELECT * FROM user WHERE id = ?", (uid,)).fetchone()

        token, expires = auth.create_session(conn, row["id"], True,
                                             request.headers.get("User-Agent", ""))
        resp = make_response(jsonify(user=_user_json(row), csrf=_csrf_for(token),
                                     gallery=_gallery_json(room)))
        _set_cookie(resp, token, expires)
        return resp

    @app.get("/api/g/<slug>/canvases")
    def gallery_canvases(slug):
        conn = _conn()
        row = conn.execute("SELECT * FROM room WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            return jsonify(error="That gallery was not found."), 404
        if not (auth.has_gallery(conn, request.cookies.get(GALLERY_COOKIE, ""), row["id"])
                or _may_manage_gallery(row)):
            return jsonify(error="Please enter the code for this gallery."), 403
        rows = conn.execute(
            "SELECT c.*, u.display_name AS owner_name FROM canvas c "
            "JOIN user u ON u.id = c.owner_id WHERE c.room_id = ? "
            "ORDER BY c.updated_at DESC", (row["id"],)).fetchall()
        return jsonify(gallery=_gallery_json(row),
                       canvases=[_canvas_json(r) for r in rows])

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

    @app.post("/api/users/<uid>/reset")
    @login_required
    def reset_user(uid):
        """Issue a fresh one-time link so someone can choose a new passphrase.

        Participants forget theirs, and the facilitator is the person standing
        next to them. Nothing is revealed about the old one.
        """
        conn = _conn()
        row = conn.execute("SELECT * FROM user WHERE id = ?", (uid,)).fetchone()
        if row is None:
            return jsonify(error="That person was not found."), 404
        if not _may_manage_user(row):
            return jsonify(error="That person is in another group."), 403
        token = secrets.token_urlsafe(24)
        conn.execute("UPDATE user SET setup_token = ?, pass_hash = NULL WHERE id = ?",
                     (token, uid))
        # Any device still signed in as them is signed out.
        conn.execute("DELETE FROM session WHERE user_id = ?", (uid,))
        conn.commit()
        return jsonify(setup_url=f"/setup/{token}", display_name=row["display_name"])

    @app.get("/api/users/<uid>/export")
    @login_required
    def export_user(uid):
        """Everything held about one person, for a right-of-access request.

        Quebec's Law 25 gives people the right to see what is held about them and
        to have it in a usable form; recordings of an identifiable person are
        personal information. This returns the record, not the media -- the audio
        is downloadable at the urls it lists.
        """
        conn = _conn()
        row = conn.execute("SELECT * FROM user WHERE id = ?", (uid,)).fetchone()
        if row is None:
            return jsonify(error="That person was not found."), 404
        if not _may_manage_user(row):
            return jsonify(error="That person is in another group."), 403
        canvases = conn.execute(
            "SELECT c.*, u.display_name AS owner_name FROM canvas c "
            "JOIN user u ON u.id = c.owner_id WHERE c.owner_id = ?", (uid,)).fetchall()
        return jsonify(
            person={"display_name": row["display_name"], "role": row["role"],
                    "created_at": row["created_at"], "consent_at": row["consent_at"],
                    "last_seen_at": row["last_seen_at"]},
            canvases=[_canvas_json(c, full=True) for c in canvases])

    @app.delete("/api/users/<uid>")
    @login_required
    def delete_user(uid):
        """Erase a person and everything they made, media included.

        Law 25 gives a right to withdraw consent and have personal information
        deleted, so this has to remove the uploaded files too -- dropping the
        database rows alone would leave the recordings on disk.
        """
        conn = _conn()
        row = conn.execute("SELECT * FROM user WHERE id = ?", (uid,)).fetchone()
        if row is None:
            return jsonify(error="That person was not found."), 404
        if not _may_manage_user(row):
            return jsonify(error="That person is in another group."), 403
        if row["role"] == "admin" and conn.execute(
                "SELECT COUNT(*) AS c FROM user WHERE role = 'admin'").fetchone()["c"] <= 1:
            return jsonify(error="This is the only administrator."), 400

        removed = _purge_media_for_owner(conn, uid)
        conn.execute("DELETE FROM upload WHERE owner_id = ?", (uid,))
        conn.execute("DELETE FROM user WHERE id = ?", (uid,))
        conn.commit()
        return jsonify(ok=True, files_removed=removed)

    # ------------------------------------------------------------ static app --
    @app.get("/")
    @app.get("/setup/<path:_t>")
    @app.get("/canvas/<path:_t>")
    @app.get("/gallery")
    @app.get("/g/<path:_t>")
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
           "display_name": row["display_name"], "role": row["role"],
           "group_id": row["group_id"] if "group_id" in row.keys() else None}
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


def _clean_zones(zones, owner_id=None):
    """Clamp everything the client sends, and refuse media the owner does not own.

    `owner_id` is the canvas owner. A zone may point at the shared sound bank or
    at a file that person uploaded, and at nothing else -- otherwise one
    participant could attach another's recording to their own picture simply by
    copying the URL.
    """
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
                 "url": None if kind == "generated"
                        else _clean_media_url(z.get("url"), owner_id)}
        for key, (lo, hi) in _ZONE_NUM.items():
            clean[key] = _clamp(z.get(key), lo, hi, 0.0 if key != "radius" else 200.0)
        fx = z.get("effects") if isinstance(z.get("effects"), dict) else {}
        clean["effects"] = {k: _clamp(fx.get(k), lo, hi, 0.0) for k, (lo, hi) in _FX_NUM.items()}
        clean["effects"]["isReversed"] = bool(fx.get("isReversed"))
        out.append(clean)
    return out


# Uploads live under /media/; the shipped sound bank is a static asset.
_ALLOWED_URL_PREFIXES = ("/media/", "/static/sounds/")


def _clean_media_url(url, owner_id=None):
    """Keep only same-origin references the canvas owner is entitled to use.

    Rejects protocol-relative ("//evil.example/x") and traversal forms, anything
    outside our own prefixes, and -- the point of `owner_id` -- an upload
    belonging to somebody else.
    """
    if not isinstance(url, str):
        return None
    if ".." in url or url.startswith("//"):
        return None
    if not any(url.startswith(prefix) for prefix in _ALLOWED_URL_PREFIXES):
        return None
    url = url[:300]

    if url.startswith("/static/sounds/"):
        return url                       # the shared bank is for everyone

    rel = url[len("/media/"):]
    row = _conn().execute("SELECT owner_id FROM upload WHERE path = ?", (rel,)).fetchone()
    if row is None:
        # Unknown to the upload table: pre-dates it, or was never uploaded here.
        return url if owner_id is None else None
    if owner_id is not None and row["owner_id"] not in (None, owner_id):
        return None                      # somebody else's recording
    return url


def _may_fetch_upload(rel):
    """Who may hear a given file.

    The owner and administrators always; a facilitator for their own group's
    people; and anyone who may view a canvas that legitimately uses it -- which
    is what lets a group listen to each other's pictures without being able to
    take the recording for their own.
    """
    conn = _conn()
    user = current_user()
    row = conn.execute("SELECT owner_id FROM upload WHERE path = ?", (rel,)).fetchone()

    if user and auth.is_admin(user):
        return True
    if row is not None and user and row["owner_id"] == user["id"]:
        return True
    if row is not None and row["owner_id"] and user:
        owner = conn.execute("SELECT group_id FROM user WHERE id = ?",
                             (row["owner_id"],)).fetchone()
        if owner and owner["group_id"]:
            room = conn.execute("SELECT owner_id FROM room WHERE id = ?",
                                (owner["group_id"],)).fetchone()
            if room and room["owner_id"] == user["id"]:
                return True              # the facilitator running that group

    url = f"/media/{rel}"
    candidates = conn.execute(
        "SELECT c.*, u.display_name AS owner_name FROM canvas c "
        "JOIN user u ON u.id = c.owner_id "
        "WHERE c.image_path = ? OR c.zones LIKE ?", (rel, f"%{url}%")).fetchall()
    return any(may_view_canvas(c) for c in candidates)


def _clamp(value, lo, hi, default):
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def _canvas_or_none(cid):
    return _conn().execute(
        "SELECT c.*, u.display_name AS owner_name FROM canvas c "
        "JOIN user u ON u.id = c.owner_id WHERE c.id = ?", (cid,)).fetchone()


def _gallery_json(row, manage=False):
    out = {"id": row["id"], "title": row["title"], "slug": row["slug"],
           "subtitle": row["subtitle"]}
    if manage:
        out["canvases"] = row["canvases"] if "canvases" in row.keys() else 0
        out["has_pin"] = bool(row["pin_hash"])
        out["created_at"] = row["created_at"]
    return out


def _may_manage_user(row):
    """An admin, or the facilitator who owns that person's group."""
    user = current_user()
    if not user:
        return False
    if auth.is_admin(user):
        return True
    if not row["group_id"]:
        return False
    owner = _conn().execute("SELECT owner_id FROM room WHERE id = ?",
                            (row["group_id"],)).fetchone()
    return bool(owner) and owner["owner_id"] == user["id"]


def _purge_media_for_owner(conn, uid):
    """Delete files referenced only by this person's canvases. Returns a count."""
    rows = conn.execute("SELECT image_path, zones FROM canvas WHERE owner_id = ?",
                        (uid,)).fetchall()
    paths = set()
    for row in rows:
        if row["image_path"]:
            paths.add(row["image_path"])
        try:
            for zone in json.loads(row["zones"] or "[]"):
                url = zone.get("url") or ""
                if url.startswith("/media/"):
                    paths.add(url[len("/media/"):])
        except (ValueError, AttributeError):
            continue

    # Never remove a file another canvas still points at.
    removed = 0
    for rel in paths:
        still_used = conn.execute(
            "SELECT 1 FROM canvas WHERE owner_id != ? AND "
            "(image_path = ? OR zones LIKE ?) LIMIT 1",
            (uid, rel, f"%{rel}%")).fetchone()
        if still_used:
            continue
        target = files.safe_join(UPLOAD_DIR, rel)
        if target:
            try:
                os.remove(target)
                removed += 1
            except OSError:
                pass
    return removed


def _may_manage_gallery(row):
    user = current_user()
    return bool(user) and (row["owner_id"] == user["id"] or auth.is_admin(user))


def _may_edit(row):
    """Own work always; admins anything. A participant never edits another's.

    Everyone in a group shares one code, so without this a misplaced tap could
    let one person overwrite someone else's picture.
    """
    user = current_user()
    if not user:
        return False
    if row["owner_id"] == user["id"]:
        return True
    return auth.is_admin(user)


app = create_app() if os.environ.get("IMAGERY_EAGER") else None

"""SQLite schema and access helpers.

Deliberately stdlib-only: no ORM, no migration framework. The schema is small
and the app is self-hosted by one person, so a readable CREATE TABLE beats a
dependency. Migrations are forward-only and idempotent -- see `migrate`.
"""
import os
import sqlite3
import secrets
import time

DB_PATH = os.environ.get("IMAGERY_DB", "/data/imagery.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS user (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name  TEXT NOT NULL,
    pass_hash     TEXT,              -- NULL until the first-login setup link is used
    -- 'participant' is someone in a workshop group: they author their own
    -- pictures and see their group's collective gallery, and nothing else.
    role          TEXT NOT NULL DEFAULT 'user'
                  CHECK (role IN ('user', 'admin', 'participant')),
    group_id      TEXT REFERENCES room(id) ON DELETE CASCADE,
    consent_at    REAL,
    setup_token   TEXT,              -- one-time; lets an admin onboard without email
    created_at    REAL NOT NULL,
    last_seen_at  REAL
);

CREATE TABLE IF NOT EXISTS session (
    token       TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    user_agent  TEXT
);
CREATE INDEX IF NOT EXISTS session_user ON session(user_id);

CREATE TABLE IF NOT EXISTS login_attempt (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    ip          TEXT NOT NULL,
    at          REAL NOT NULL,
    ok          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS login_attempt_lookup ON login_attempt(name, at);
CREATE INDEX IF NOT EXISTS login_attempt_ip ON login_attempt(ip, at);

-- A canvas: one image plus its sound zones. `zones` is the JSON array, stored
-- verbatim in the same shape the original app used, so exports round-trip.
CREATE TABLE IF NOT EXISTS canvas (
    id            TEXT PRIMARY KEY,
    owner_id      TEXT NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    description   TEXT,
    image_path    TEXT,
    zones         TEXT NOT NULL DEFAULT '[]',
    published     INTEGER NOT NULL DEFAULT 0,
    room_id       TEXT REFERENCES room(id) ON DELETE SET NULL,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS canvas_owner ON canvas(owner_id);
CREATE INDEX IF NOT EXISTS canvas_room ON canvas(room_id);

CREATE TABLE IF NOT EXISTS sound (
    id          TEXT PRIMARY KEY,
    owner_id    TEXT NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sound_owner ON sound(owner_id);

-- Who uploaded each file. Without this a recording is only as private as its
-- URL, and nothing stops one participant attaching another's voice to their own
-- picture. A participant's recording of their own memories is theirs.
CREATE TABLE IF NOT EXISTS upload (
    path        TEXT PRIMARY KEY,       -- relative, e.g. "audio/ab12...webm"
    owner_id    TEXT REFERENCES user(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS upload_owner ON upload(owner_id);

-- A "room" is a group's own gallery: a named set of canvases behind a PIN.
-- Workshops are run per group and each group should see only its own work,
-- so access is per-gallery rather than per-account -- participants never sign in.
CREATE TABLE IF NOT EXISTS room (
    id          TEXT PRIMARY KEY,
    owner_id    TEXT NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    subtitle    TEXT,
    slug        TEXT UNIQUE,
    pin_hash    TEXT,
    accent_color TEXT DEFAULT '#6d5cf6',
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS room_owner ON room(owner_id);

-- A browser that has entered a gallery's PIN. One token can unlock several
-- galleries, so a facilitator moving between groups is not forced to juggle
-- cookies.
CREATE TABLE IF NOT EXISTS gallery_access (
    token       TEXT NOT NULL,
    room_id     TEXT NOT NULL REFERENCES room(id) ON DELETE CASCADE,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    PRIMARY KEY (token, room_id)
);
CREATE INDEX IF NOT EXISTS gallery_access_expiry ON gallery_access(expires_at);
"""


def connect(path=None):
    """Open a connection.

    `busy_timeout` makes concurrent writers wait for the lock instead of failing
    immediately, which matters because gunicorn runs several workers against one
    SQLite file. Journal mode is deliberately *not* set here: WAL is a property
    of the database file, so it only needs setting once, and trying to set it on
    every connection can collide with another worker's open write transaction.
    """
    conn = sqlite3.connect(path or DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Columns added after the first release. SQLite has no "ADD COLUMN IF NOT
# EXISTS", so they are applied by inspection instead of by version number --
# there are few enough that a table of them is clearer than a migration runner.
_ADDED_COLUMNS = (
    ("room", "slug", "TEXT"),
    ("room", "pin_hash", "TEXT"),
    ("user", "group_id", "TEXT"),
    ("user", "consent_at", "REAL"),
)


def _ensure_columns(conn):
    for table, column, decl in _ADDED_COLUMNS:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if not existing:
            continue                       # table not created yet; schema will do it
        if column in existing:
            continue
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        except sqlite3.OperationalError as exc:
            # Another worker added it between the PRAGMA and here.
            if "duplicate column" not in str(exc).lower():
                raise


def _relax_role_check(conn):
    """Allow the 'participant' role on databases created before it existed.

    The CHECK constraint lives in the CREATE TABLE statement, so it cannot be
    altered in place -- the table has to be rebuilt. This runs once: afterwards
    the probe insert succeeds and it returns immediately.
    """
    try:
        conn.execute("SAVEPOINT role_probe")
        conn.execute(
            "INSERT INTO user (id, name, display_name, role, created_at) "
            "VALUES ('__probe__', '__probe__', '__probe__', 'participant', 0)")
        conn.execute("ROLLBACK TO role_probe")
        conn.execute("RELEASE role_probe")
        return                                   # constraint already allows it
    except sqlite3.IntegrityError:
        conn.execute("ROLLBACK TO role_probe")
        conn.execute("RELEASE role_probe")
    except sqlite3.OperationalError:
        return                                   # table not created yet

    cols = [r["name"] for r in conn.execute("PRAGMA table_info(user)")]
    joined = ", ".join(cols)
    try:
        conn.executescript(f"""
        PRAGMA foreign_keys = OFF;
        BEGIN;
        CREATE TABLE user_new (
            id            TEXT PRIMARY KEY,
            name          TEXT NOT NULL UNIQUE COLLATE NOCASE,
            display_name  TEXT NOT NULL,
            pass_hash     TEXT,
            role          TEXT NOT NULL DEFAULT 'user'
                          CHECK (role IN ('user', 'admin', 'participant')),
            group_id      TEXT,
            consent_at    REAL,
            setup_token   TEXT,
            created_at    REAL NOT NULL,
            last_seen_at  REAL
        );
        INSERT INTO user_new ({joined}) SELECT {joined} FROM user;
        DROP TABLE user;
        ALTER TABLE user_new RENAME TO user;
        COMMIT;
        PRAGMA foreign_keys = ON;
    """)
    except sqlite3.OperationalError as exc:
        # Another worker rebuilt it first; its table is the one we want anyway.
        if "user_new" not in str(exc) and "no such table" not in str(exc).lower():
            raise


def _backfill_uploads(conn):
    """Attribute files that pre-date the upload table, from the canvases using them.

    Anything still unattributed is left with a NULL owner, which the media
    handler treats as "only reachable through a canvas you may view" rather than
    as public.
    """
    if conn.execute("SELECT 1 FROM upload LIMIT 1").fetchone():
        return
    import json as _json
    for row in conn.execute("SELECT owner_id, image_path, zones FROM canvas"):
        paths = []
        if row["image_path"]:
            paths.append((row["image_path"], "image"))
        try:
            for zone in _json.loads(row["zones"] or "[]"):
                url = (zone or {}).get("url") or ""
                if url.startswith("/media/"):
                    paths.append((url[len("/media/"):], "audio"))
        except (ValueError, AttributeError, TypeError):
            pass
        for rel, kind in paths:
            conn.execute(
                "INSERT OR IGNORE INTO upload (path, owner_id, kind, created_at) "
                "VALUES (?,?,?,?)", (rel, row["owner_id"], kind, time.time()))


def migrate(conn):
    """Bring the database up to date. Safe to run from several workers at once.

    Every gunicorn worker calls this at boot, so all of it races. Three
    protections, because each failed differently in practice:

    * WAL is set inside a try -- losing that race just means another worker
      already set the same value.
    * The whole migration takes an advisory lock, so normally only one worker
      does the work and the others find it already done.
    * Each step is still individually idempotent, because the lock is advisory
      and a worker can arrive after it has been released.
    """
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass

    conn.executescript(SCHEMA)

    # Serialise the parts that cannot simply be re-run. busy_timeout (set in
    # connect) makes a competing worker wait here rather than fail.
    try:
        conn.execute("BEGIN IMMEDIATE")
        holding = True
    except sqlite3.OperationalError:
        holding = False

    try:
        _ensure_columns(conn)
        _relax_role_check(conn)
        _backfill_uploads(conn)
    finally:
        if holding:
            try:
                conn.commit()
            except sqlite3.OperationalError:
                pass
    conn.commit()


def new_id():
    """Short, URL-safe, collision-resistant. Not sequential, so ids leak no counts."""
    return secrets.token_hex(12)


def now():
    return time.time()

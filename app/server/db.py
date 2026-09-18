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
    role          TEXT NOT NULL DEFAULT 'user'
                  CHECK (role IN ('user', 'admin')),
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

CREATE TABLE IF NOT EXISTS room (
    id          TEXT PRIMARY KEY,
    owner_id    TEXT NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    subtitle    TEXT,
    accent_color TEXT DEFAULT '#6d5cf6',
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS room_owner ON room(owner_id);
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


def migrate(conn):
    """Create the schema and, once, switch the file to WAL.

    Both are safe to run from several workers at the same time: the CREATE
    statements are IF NOT EXISTS, and a WAL switch that loses the race just
    means another worker already did it.
    """
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass          # another worker holds the lock; it is setting the same value
    conn.executescript(SCHEMA)
    conn.commit()


def new_id():
    """Short, URL-safe, collision-resistant. Not sequential, so ids leak no counts."""
    return secrets.token_hex(12)


def now():
    return time.time()

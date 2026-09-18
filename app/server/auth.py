"""Authentication: passphrases, sessions, rate limiting, roles.

Design notes, since the brief was "easy enough for older people, still secure":

* **Passphrases, not passwords.** Following NIST SP 800-63B: a generous minimum
  length, and *no* composition rules, no forced rotation, no security questions.
  Those rules make passwords harder to remember without making them harder to
  guess. "the blue kettle sings" is both easier and stronger than "P@ssw0rd1".
* **Long sessions by default.** Re-typing a passphrase is where older users get
  stuck, so a trusted device stays signed in for 90 days. The cost of that is
  bounded by being able to revoke sessions server-side.
* **Session tokens are stored hashed.** A leaked database does not hand out live
  sessions.
* **Rate limiting is per-account and per-IP.** Lockout is a delay that grows, not
  a hard block -- a permanent lockout is a denial-of-service against the very
  user who is already struggling to log in.

Hashing is `hashlib.scrypt` from the standard library, so there is no third-party
crypto dependency to audit or keep patched.
"""
import hashlib
import hmac
import os
import re
import secrets
import time

from . import db

# scrypt parameters. n=2**15 with r=8 costs ~32MB and ~50-100ms per hash, which
# is a reasonable interactive-login budget on the small host this runs on.
_N, _R, _P = 2 ** 15, 8, 1
_SALT_BYTES = 16
_KEY_LEN = 32

MIN_PASSPHRASE = 10
SESSION_DAYS_DEFAULT = 1
SESSION_DAYS_TRUSTED = 90

# Attempts allowed before the delay starts growing, and the window they are counted in.
_FREE_ATTEMPTS = 5
_WINDOW = 15 * 60
_MAX_DELAY = 30.0

# Passphrases that are common enough to be tried first in any attack. Short list
# on purpose: the length minimum does most of the work, and a huge blocklist here
# would just be a worse version of a breach-corpus check.
_BLOCKED = {
    "password", "passphrase", "motdepasse", "123456789", "1234567890",
    "qwertyuiop", "azertyuiop", "letmein123", "iloveyou1", "administrator",
    "imagery123", "changeme1", "welcome123",
}


# --------------------------------------------------------------------------- #
# Passphrase hashing
# --------------------------------------------------------------------------- #

def hash_passphrase(passphrase: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    key = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt,
                         n=_N, r=_R, p=_P, dklen=_KEY_LEN, maxmem=64 * 1024 * 1024)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${key.hex()}"


def verify_passphrase(passphrase: str, stored: str) -> bool:
    if not stored:
        return False
    try:
        scheme, n, r, p, salt_hex, key_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        key = hashlib.scrypt(passphrase.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                             n=int(n), r=int(r), p=int(p),
                             dklen=len(key_hex) // 2, maxmem=64 * 1024 * 1024)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(key.hex(), key_hex)


def passphrase_problem(passphrase: str, name: str = "") -> str | None:
    """Return a plain-language problem, or None if acceptable.

    Messages are written to be read by someone who is not technical, and say what
    to do rather than what went wrong.
    """
    if len(passphrase.strip()) < MIN_PASSPHRASE:
        return (f"Please make it a bit longer - at least {MIN_PASSPHRASE} letters. "
                "A few words together works well, like 'the blue kettle sings'.")
    if passphrase.lower().strip() in _BLOCKED:
        return "That one is guessed too easily. Try a few ordinary words instead."
    if name and passphrase.lower().strip() == name.lower().strip():
        return "This is the same as your name. Please choose something different."
    if len(set(passphrase.strip())) < 4:
        return "Please use a few more different letters."
    return None


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #

def record_attempt(conn, name: str, ip: str, ok: bool):
    conn.execute("INSERT INTO login_attempt (name, ip, at, ok) VALUES (?,?,?,?)",
                 (name.lower(), ip, time.time(), 1 if ok else 0))
    # Keep the table from growing without bound.
    conn.execute("DELETE FROM login_attempt WHERE at < ?", (time.time() - 7 * 86400,))
    conn.commit()


def failed_recently(conn, name: str, ip: str) -> int:
    since = time.time() - _WINDOW
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM login_attempt "
        "WHERE ok = 0 AND at > ? AND (name = ? OR ip = ?)",
        (since, name.lower(), ip)).fetchone()
    return row["c"] if row else 0


def throttle_delay(failures: int) -> float:
    """Escalating delay, capped. Never a permanent lockout -- see module docstring."""
    if failures < _FREE_ATTEMPTS:
        return 0.0
    return min(_MAX_DELAY, 0.5 * (2 ** (failures - _FREE_ATTEMPTS)))


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(conn, user_id: str, trusted: bool, user_agent: str = "") -> tuple[str, float]:
    token = secrets.token_urlsafe(32)
    days = SESSION_DAYS_TRUSTED if trusted else SESSION_DAYS_DEFAULT
    expires = time.time() + days * 86400
    conn.execute(
        "INSERT INTO session (token, user_id, created_at, expires_at, user_agent) "
        "VALUES (?,?,?,?,?)",
        (_hash_token(token), user_id, time.time(), expires, (user_agent or "")[:300]))
    conn.commit()
    return token, expires


def user_for_session(conn, token: str):
    if not token:
        return None
    row = conn.execute(
        "SELECT u.* FROM session s JOIN user u ON u.id = s.user_id "
        "WHERE s.token = ? AND s.expires_at > ?",
        (_hash_token(token), time.time())).fetchone()
    if row:
        conn.execute("UPDATE user SET last_seen_at = ? WHERE id = ?", (time.time(), row["id"]))
        conn.commit()
    return row


def destroy_session(conn, token: str):
    if token:
        conn.execute("DELETE FROM session WHERE token = ?", (_hash_token(token),))
        conn.commit()


def purge_expired(conn):
    conn.execute("DELETE FROM session WHERE expires_at < ?", (time.time(),))
    conn.commit()


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #

_NAME_RE = re.compile(r"^[\w .'\-]{2,40}$", re.UNICODE)


def name_problem(name: str) -> str | None:
    if not _NAME_RE.match(name or ""):
        return "Please use 2 to 40 letters. Spaces, hyphens and apostrophes are fine."
    return None


def create_user(conn, name: str, display_name: str, role: str = "user",
                passphrase: str | None = None) -> tuple[str, str | None]:
    """Create a user. Without a passphrase, returns a one-time setup token.

    The setup-token path exists so an admin can onboard someone without this app
    needing to send email -- the admin reads them the link, or opens it for them.
    """
    uid = db.new_id()
    token = None if passphrase else secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO user (id, name, display_name, pass_hash, role, setup_token, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (uid, name.strip(), (display_name or name).strip(),
         hash_passphrase(passphrase) if passphrase else None,
         role, token, time.time()))
    conn.commit()   # commits the caller's transaction too, which is intended here
    return uid, token


def set_passphrase(conn, user_id: str, passphrase: str):
    conn.execute("UPDATE user SET pass_hash = ?, setup_token = NULL WHERE id = ?",
                 (hash_passphrase(passphrase), user_id))
    # Changing the passphrase invalidates every existing session, everywhere.
    conn.execute("DELETE FROM session WHERE user_id = ?", (user_id,))
    conn.commit()


def is_admin(user) -> bool:
    return bool(user) and user["role"] == "admin"

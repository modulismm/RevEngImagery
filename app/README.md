# Imagery -- self-hosted

A replacement for the Base44-hosted *Imagery*: a picture with hidden sound zones
that play as the pointer moves over them. Built from the reverse-engineering
work in `../docs/`, so existing canvases and exports keep working.

Runs as a single container. No build step, no Node, no external services.

## Run it

```bash
cp .env.example .env        # set a first-run admin passphrase
docker compose up -d --build
```

First run creates the admin account named by `IMAGERY_ADMIN`. If you leave
`IMAGERY_ADMIN_PASSPHRASE` empty, the log prints a one-time `/setup/<token>`
link instead -- which is the better option, since the passphrase then never sits
in a file.

Everything lives in the `imagery_data` volume: the SQLite database, uploads and
the session secret. Back that volume up and you have backed up the whole app.

## Sign-in, and why it works this way

The brief was a login older people can use without help, that is still properly
secure. Following NIST SP 800-63B:

- **Passphrases, not passwords.** Long minimum, and *no* composition rules, no
  forced rotation, no security questions. "the blue kettle sings" is easier to
  remember and harder to guess than "P@ssw0rd1".
- **A real show/hide button** on every passphrase field. Typing a long phrase
  blind is the single biggest cause of failed sign-ins.
- **Stay signed in for 90 days**, ticked by default. Re-typing is where people
  get stuck; the risk is bounded because sessions can be revoked server-side and
  changing a passphrase drops all of them.
- **No email dependency.** An admin adds a person and gets a one-time setup link
  to hand over. Nothing to configure, and no mail server in the trust path.
- **Lockout is a growing delay, capped**, not a hard block -- a permanent lockout
  is a denial of service against the person already struggling to sign in.

Passphrases are hashed with `hashlib.scrypt` from the standard library, so there
is no third-party crypto dependency to keep patched. Session tokens are stored
hashed, so a database leak does not hand out live sessions.

## Roles

| Role | Sees |
|---|---|
| `user` | their own pictures |
| `admin` | every picture from every account, plus the people list |

## Security notes

- Cookies are `HttpOnly`, `SameSite=Lax` and `Secure` by default; set
  `IMAGERY_SECURE_COOKIE=0` only when testing over plain HTTP.
- Mutating requests need a session-derived `X-CSRF-Token` header.
- Uploads are validated by **magic bytes**, never by filename or declared type,
  and stored under a random name with an extension we choose. A PHP file renamed
  `.png` is rejected.
- Zone media URLs are forced same-origin, so a canvas cannot be made to point at
  someone else's server.
- Every numeric field from the client is clamped server-side.
- The container runs as a non-root user with `no-new-privileges`.
- A strict CSP is sent on every response.

## Tests

```bash
# unit tests (Flask test client)
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  sh -c "pip install -q -r requirements.txt pytest && python -m pytest tests/test_api.py -q"

# end-to-end against a running container
docker run -d --name imagery-test -p 127.0.0.1:8011:8000 \
  -e IMAGERY_ADMIN=bear -e IMAGERY_ADMIN_PASSPHRASE='the blue kettle sings' \
  -e IMAGERY_SECURE_COOKIE=0 imagery:dev
python3 tests/smoke.py http://127.0.0.1:8011
```

## What is verified, and what is not

**Verified here:** 18 unit tests and 15 end-to-end tests, all passing, plus five
consecutive cold boots on a fresh volume.

**Not verified here:** *anything in the browser.* This host has no JavaScript
runtime, so the interface -- the canvas editor, drag and resize, and the audio
engine itself -- has never been executed. The audio graph is transcribed exactly
from the original's recovered parameters and the shapes are covered by the
server-side round-trip tests, but **it needs someone to open it and listen.**

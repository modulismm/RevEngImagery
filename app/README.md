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

## Galleries per group

Workshops run per group, and each group should see only its own work, so access
is per-gallery rather than per-account: participants never sign in.

A facilitator creates a gallery under **Galeries**, gives it a name and a 4-8
digit code, and hands out the link (`/#/g/<slug>`). Canvases are assigned to a
gallery from the editor. A visitor opening that link sees the gallery's name,
enters the code on a large keypad, and sees only that gallery.

Security notes specific to this:

- A PIN is short by design -- it gets read aloud to a room -- so the strength
  comes from rate limiting, not the secret. Failures escalate the delay per
  gallery **and** per IP, capped rather than locking out permanently.
- Obvious codes (`1234`, `0000`, repeated digits) are refused.
- Changing a gallery's code revokes every existing unlock immediately.
- Unlocking one gallery grants nothing anywhere else, and a canvas in no gallery
  is not readable without signing in.
- The unlock endpoint is exempt from the session CSRF check, because the visitor
  has no session yet; it is rate limited instead and a cross-origin caller
  cannot read the reply.

## Sound bank

30 short sounds under `static/sounds/`, listed in `bank.json`, searchable in the
editor. Three are permissively licensed recordings from Wikimedia Commons; the
other 27 are synthesised by `tools/make_sounds.py` and are CC0. Rebuild with:

```bash
python3 tools/make_sounds.py app/static/sounds/_raw     # synthesise
python3 tools/fetch_sounds.py app/static/sounds/_raw    # scrape (rate limited)
tools/convert_sounds.sh app/static/sounds/_raw app/static/sounds
python3 tools/build_bank.py
```

Credits in `docs/SOUND-ATTRIBUTION.md`.


## Participants

Workshops are the point: a participant imports a photograph, places sound spots
on it, and gives each one a sound -- often their own voice. The flow is built for
someone in their eighties on a borrowed iPad.

A facilitator creates a group and reads out its code. Each person enters the
code, then chooses the name they are known by and a passphrase (their full name
works). They see their own pictures and their group's collective gallery, and
can edit only their own.

- Touching the picture places a spot and immediately asks **record your voice**
  or **choose a sound** -- placing and filling a spot is one action, not two.
- New pictures are named automatically, so there is no keyboard moment at the
  start.
- Only volume is on screen; reverb, pitch and the equaliser are folded away.
- **Recording requires HTTPS.** Without it the browser withholds the microphone
  entirely, and the app now says so plainly instead of failing oddly. It also
  detects iPads older than iOS 14.3, which cannot record at all.

Personal information and Quebec's Law 25: see `../docs/PRIVACY.md`.

## Deploying

- **On a VPS or small server**: `docker-compose.prod.yml` puts Caddy in front,
  which obtains and renews a certificate by itself. Set `IMAGERY_DOMAIN` and run
  `docker compose -f docker-compose.prod.yml up -d --build`. Nothing else.
- **Behind an existing nginx-proxy-manager**: `docker-compose.yml` publishes on
  the docker0 gateway and leaves TLS to the proxy. See `../docs/deploy.md`.

Back up with `tools/backup.sh`, which archives the whole data volume and
verifies the archive. Add it to cron.

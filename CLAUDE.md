# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Two things that grew out of each other:

1. **A reverse-engineering record** of *Imagery* (<https://imagery.base44.app/>), a Base44
   app that turns a picture into hidden sound zones you trigger by moving the pointer over
   them. `docs/schema.md`, `artifacts/`, `samples/`, `screenshots/`.
2. **`app/` -- a self-hosted replacement**, which is now the live deliverable. Everything
   new goes here.

`README.md` carries the brief this answers: art-mediation workshops with older participants,
on iPads the participants bring themselves. That is not colour -- it is why the constraints
below exist. Read it before deciding something is over-engineered.

## The constraint that shapes everything

**The development host has no JavaScript runtime.** Node is not installed and is not
expected to be. Consequences you must work with rather than around:

- The frontend is **plain ES modules, no build step, no bundler, no framework**. Do not
  introduce one. Nothing requiring a build could be verified here at all.
- Anything JS runs in a container (see Commands).
- `app/tests/dom.test.mjs` runs the real modules under **jsdom**, which catches wiring bugs
  (missing listeners, state that never reaches the server) but has no layout and no audio.
- So: **the audio engine and touch behaviour have never been observed in a real browser.**
  When you change `audio.js`, the canvas stage, or anything touch-related, say plainly in
  your report that it is unverified. `app/README.md` keeps the running verified/not list.

## Commands

All of these run from `app/` unless noted.

```bash
# build
docker build -t imagery:dev .

# backend unit tests (Flask test client)
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  sh -c "pip install -q -r requirements.txt pytest && python -m pytest tests/test_api.py -q"
# ...a single test: append -k test_name to the pytest invocation

# DOM tests (jsdom)
docker run --rm -v "$PWD":/app -w /app node:22-slim \
  sh -c "npm i --no-save jsdom >/dev/null 2>&1 && node tests/dom.test.mjs"

# end-to-end against a running container
docker run -d --name imagery-test -p 127.0.0.1:8011:8000 \
  -e IMAGERY_ADMIN=bear -e IMAGERY_ADMIN_PASSPHRASE='the blue kettle sings' \
  -e IMAGERY_SECURE_COOKIE=0 imagery:dev
python3 tests/smoke.py http://127.0.0.1:8011

# run it
cp .env.example .env && docker compose up -d --build
```

Those containers write into the bind mount as root, so `app/node_modules/` and any
`__pycache__/` they leave behind are root-owned and `rm -rf` will refuse them. Clear them the
same way they were made: `docker run --rm -v "$PWD":/r alpine rm -rf /r/app/node_modules`.
They are gitignored.

There is no linter or formatter configured, and no dependency beyond Flask and gunicorn.
Adding either is a decision to raise, not a chore to do.

Sound bank rebuild and backups are in `app/README.md`; both are scripted in `tools/`.

## Architecture

**Backend** (`app/server/`, stdlib + Flask only):

- `app.py` -- app factory and every route, in one file. `/api/*` is the surface;
  `/`, `/gallery`, `/canvas/*`, `/g/*` all serve the same SPA shell.
- `db.py` -- `sqlite3` directly. No ORM, no migration framework; `migrate` is forward-only
  and idempotent. The `CREATE TABLE` block is the schema documentation.
- `auth.py` -- `hashlib.scrypt` passphrases, session tokens stored hashed, gallery PIN rules.
- `files.py` -- upload validation by **magic bytes**, never by filename or declared type.

**Four kinds of caller**, and authorization is the union of them -- this is the part that
needs several files read before changing an endpoint:

| Caller | How it is identified | Sees |
|---|---|---|
| `admin` | session | everything, plus the people list |
| `user` | session | their own canvases |
| `participant` | session, tied to a `group_id` | their own canvases + their group's gallery |
| a workshop visitor | **no account** -- a `gallery_access` row keyed to a cookie token | one gallery, after typing its PIN |

`/media/<path>` is authorized per file via the `upload` table: a recording belongs to whoever
made it. A spot may reference the shared sound bank or a file the canvas owner uploaded, and
nothing else. Do not add a route that serves media without going through that check.

**Frontend** (`app/static/js/`): `app.js` is the shell, hash router and all views (it is
large on purpose -- one file, no build); `api.js` attaches the CSRF header to mutations;
`i18n.js` renders French by default and warns on missing keys; `recorder.js` wraps
MediaRecorder; `audio.js` reproduces the original's Web Audio graph.

## Facts that look like choices

- **`audio.js` constants are recovered, not chosen.** Filter frequencies, Q values and the
  effects mapping come from the original's shipped bundle so existing canvases sound the
  same. Changing one is a behaviour change, not a tuning tweak. `docs/schema.md` is the
  reference.
- **`canvas.zones` is stored verbatim in Base44's shape** so exports round-trip in both
  directions. Do not normalise the field names, and keep `x`/`y` as percentages.
- **`radius` is a diameter**, and its units in the original are still unconfirmed.
- `app/static/sounds/bank.json` and the MP3s are **generated** by `tools/build_bank.py` and
  friends -- edit the tools, not the output. `artifacts/` is fetched evidence, not source.

## Invariants worth not regressing

These each cost a debugging session or a security fix; the commit messages explain them.

- The container never binds `0.0.0.0` -- `IMAGERY_BIND` is `172.17.0.1` (docker0, behind
  nginx-proxy-manager) or `127.0.0.1` (behind `tailscale serve`). See `docs/deploy.md`.
- Cookies stay `Secure`/`HttpOnly`/`SameSite=Lax`; HSTS is sent only when the connection
  really is secure. `IMAGERY_SECURE_COOKIE=0` is for plain-HTTP testing only.
- A gallery PIN is short by design (read aloud to a room), so strength comes from **rate
  limiting per gallery and per IP, capped** -- never a hard lockout, which would be a denial
  of service against the person already struggling.
- Signing out gives up gallery access too: these iPads are handed from person to person.
- **Recording requires HTTPS.** Without a secure context the browser withholds the
  microphone entirely, so a plain-HTTP deployment cannot exercise the feature this exists for.
- `touch-action` on the canvas stage is `manipulation`, tightened to `none` only during an
  actual drag. A blanket `none` is what made iPads unscrollable in landscape.

## Conventions

- Commit messages are prose that explains **why**, in the present tense, no
  `feat:`/`fix:` prefixes. Look at `git log` before writing one.
- Code and docs are in English; the UI is French-first.
- `docs/PRIVACY.md` covers personal information and Quebec's Law 25 -- participants'
  recordings are personal data, and anything touching retention or export belongs there too.

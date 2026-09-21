# RevEngImagery

Reverse-engineering **Imagery** (<https://imagery.base44.app/>), an app built on the
**Base44** platform that turns an image into an interactive audio experience -- hover a
cursor over hidden sound zones to trigger sounds.

The goal is to be able to leave the platform: understand what the app is, get the data
out, and know what a rebuild would cost.

## The mandate

The work comes from a *cahier de charges* for the technical tooling used in art-mediation
workshops with older participants. Two tools, **two weeks, 30 hours**:

- **Imagery** -- <https://imagery.base44.app/Gallery>, the gallery the workshops use.
  A public page, no password, run by someone on the internal team. This repo.
- **Photo IA** -- AI photo processing at `images.sporobole.org`, reached by URL and a QR
  code, run by someone outside the project. **Not in this repo** -- see below.

Imagery is fine on a laptop and needs nothing there. Everything asked for is either an iPad
problem or a new feature.

| # | Asked for | Status |
|---|---|---|
| 1 | iPad: the view cannot be scrolled in landscape | ✅ fixed -- in the rebuild |
| 2 | Split the single *Un portrait* gallery into one per group, each behind a PIN | ✅ built |
| 3 | A bank of ~25 short, royalty-free sounds | ✅ 30 sounds, served by the app |

### Why these landed in a rebuild rather than in Base44

None of the three can be done on `imagery.base44.app` itself. The React source is not
recoverable (below), so there is nothing to patch: the iPad bug lives in code that cannot be
edited, and per-group PIN galleries are a data-model change the hosted app does not offer.
What *is* recoverable is the data and the schema -- enough to rebuild. The replacement lives
in [`app/`](app/) and reads the original's exports, so existing canvases carry over.

**1. iPad, landscape.** The cause is a blanket `touch-action: none` on the picture. In
landscape the picture fills the viewport, so every touch landed on an element that refused to
pan and the page could not be moved at all -- which matches the report exactly: landscape
only, portrait fine. The rebuild sets `touch-action: manipulation` (panning and pinch-zoom
keep working, Safari's 300 ms tap delay goes) and suppresses panning only for the duration of
an actual zone drag. That is a CSS contract rather than a per-model workaround, so it holds
across the BYOD spread of iPads and iOS versions the workshops see. A video capture of the
original bug is in the project Drive (link deliberately kept out of this file).

**2. Per-group galleries.** A facilitator creates a gallery, gives it a name and a 4-8 digit
code, and hands out `/#/g/<slug>`; participants never sign in. Obvious codes are refused, the
strength comes from rate limiting per gallery *and* per IP rather than from the secret, and
changing a code revokes every existing unlock. Full notes in
[`app/README.md`](app/README.md).

**3. Sound bank.** 30 short sounds in `app/static/sounds/`, listed in `bank.json` and
searchable from the editor: 27 synthesised CC0, 3 from Wikimedia Commons (2 public domain,
1 CC BY 3.0 -- attribution in [`docs/SOUND-ATTRIBUTION.md`](docs/SOUND-ATTRIBUTION.md)).
Nothing in it needs a licence. They are chosen against the brief's "tied to the memories of
older participants" -- a kettle, a sewing machine, a typewriter, a rotary telephone, a
musicbox, rain on a window.

> **Deviation from the brief:** the bank is served by the app, not hosted on Drive. Drive
> would mean a download-then-upload round trip on a borrowed iPad and a live network
> dependency in the room; in-app, a sound is one search away inside the editor. Adding sounds
> is a documented rebuild step. If Drive specifically is what the team wants as the drop-off
> point, that is the piece still to build.

### Photo IA -- not in this repo

The second tool in the brief is separate and untouched here. Both items are open:

| Asked for | Blocked on |
|---|---|
| **Access autonomy** -- open and close the tool without going through the person who runs it, so workshops and tests do not depend on their availability | Modality undecided: a separate account, or an on/off switch. Needs that tool's dev. |
| **Automatic downsize** of images participants upload | No size or resolution threshold set, and no decision on whether it applies to the final image or only to a working copy |

### Still to settle

- **Who curates the sound bank** after the initial set -- selection, organisation, additions.
  Unassigned.
- **Categories** were deliberately not fixed in advance; they follow what participants ask
  for. The bank is a flat searchable list today, with a French and English label per sound.
  Grouping can be added once the categories are known.
- The two Photo IA questions above.

## Where this stands

**The data comes out. The source does not.**

| | Status |
|---|---|
| Canvas metadata, sound zones, effects, coordinates | ✅ recoverable |
| Images and audio | ✅ recoverable -- public URLs, no auth |
| Data model / schema | ✅ recovered -- [`docs/schema.md`](docs/schema.md) |
| Gallery theming and rooms | ✅ via the entities API |
| **React source code** | ❌ **not recoverable** |

A **Base44 dev account is not needed for any of the data.** (Push44 wants one; it turned out
to be unnecessary.) The app ships its own per-canvas JSON export/import, and its entities API
is readable without authentication.

The source is genuinely gone: **no sourcemaps** (`/assets/index-*.js.map` is a 404), and the
505 KB bundle is mostly Base44's own runtime rather than app code. Every route serves the
same bundle -- the per-route HTML differs only in SEO meta -- so there are no per-page chunks
to recover either. **Rebuilding from the schema is faster than de-minifying.**

## Layout

```
app/                  the self-hosted replacement -- see app/README.md
docs/schema.md        recovered data model, API surface, export format
docs/ux-review.md     static UI/UX review (no browser -- see its stated limits)
docs/deploy.md        putting the replacement behind Caddy or nginx-proxy-manager
docs/PRIVACY.md       personal information and Quebec's Law 25
tools/                imagery_backup.py -- pull canvases + media into self-contained bundles
artifacts/            the served bundle, stylesheet and HTML, as fetched
samples/              a real canvas export
screenshots/          UI captures -- see screenshots/README.md for what is worth capturing
```

## Backing up

```bash
python3 tools/imagery_backup.py ~/Downloads/*.imagery*.json   # from UI exports
python3 tools/imagery_backup.py --bulk                        # everything, via the API
```

Stdlib only. Pulls remote media local and rewrites the JSON to local paths, keeping each
original as `<key>_remote` so a bundle still re-imports to Base44. Idempotent.

## Known unknowns

- **The audio graph.** How `reverbLevel`, `pitch` and the frequency bands map onto Web Audio
  nodes is real behaviour, only partly readable from the minified bundle. Screenshots will not
  help here. The rebuild transcribes the recovered parameters exactly, but that transcription
  has never been heard -- this is the part to budget listening time for.
- **`radius` units.** Percentages for `x`/`y` are confirmed; `radius` looks like pixels and
  behaves as a diameter in the rebuild, but the original's units are unverified.
- **Whether hover-only entry unlocks audio.** `AudioContext.resume()` is wired to `onMouseDown`
  and `onTouchStart`, but `mousemove` is not a qualifying user gesture under Chrome's autoplay
  policy -- so a visitor who only hovers may get silence. Needs a browser to confirm.
- **Everything in a browser, generally.** This host has no JavaScript runtime: the rebuild's
  server side is covered by tests, its interface has never been executed. The iPad fix above
  is reasoned from the cause, not observed on an iPad.

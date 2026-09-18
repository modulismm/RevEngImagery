# RevEngImagery

Reverse-engineering **Imagery** (<https://imagery.base44.app/>), an app built on the
**Base44** platform that turns an image into an interactive audio experience -- hover a
cursor over hidden sound zones to trigger sounds.

The goal is to be able to leave the platform: understand what the app is, get the data
out, and know what a rebuild would cost.

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
docs/schema.md        recovered data model, API surface, export format
docs/ux-review.md     static UI/UX review (no browser -- see its stated limits)
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
  help here. If a rebuild happens, this is the part to budget for.
- **`radius` units.** Percentages for `x`/`y` are confirmed; `radius` looks like pixels but is
  unverified.
- **Whether hover-only entry unlocks audio.** `AudioContext.resume()` is wired to `onMouseDown`
  and `onTouchStart`, but `mousemove` is not a qualifying user gesture under Chrome's autoplay
  policy -- so a visitor who only hovers may get silence. Needs a browser to confirm.

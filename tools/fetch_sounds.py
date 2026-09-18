#!/usr/bin/env python3
"""Build the built-in sound bank from Wikimedia Commons.

Only permissively licensed files are kept -- CC0, public domain and CC BY --
and every one is recorded in ATTRIBUTION.md with its author, licence and source
page. CC BY-SA is skipped: it is usable, but share-alike on bundled media is a
complication this project does not need.

Commons audio is mostly Ogg Vorbis, which Safari cannot play, so the results are
transcoded to mono MP3 (see convert_sounds.sh). This script only downloads.

    python3 tools/fetch_sounds.py app/static/sounds/_raw
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://commons.wikimedia.org/w/api.php"
UA = "RevEngImagery-soundbank/1.0 (personal self-hosted project)"

# (slug, English label, French label, search terms)
WANTED = [
    ("rain",      "Rain",        "Pluie",          "rain rainfall"),
    ("wind",      "Wind",        "Vent",           "wind breeze"),
    ("waves",     "Waves",       "Vagues",         "sea waves beach"),
    ("birds",     "Birds",       "Oiseaux",        "birds singing forest"),
    ("water",     "Water drop",  "Goutte d'eau",   "water drop droplet"),
    ("bell",      "Bell",        "Cloche",         "bell ring"),
    ("thunder",   "Thunder",     "Tonnerre",       "thunder"),
    ("fire",      "Fire",        "Feu",            "fire crackling campfire"),
    ("footsteps", "Footsteps",   "Pas",            "footsteps walking"),
    ("crickets",  "Crickets",    "Grillons",       "crickets night insects"),
]

OK_LICENCES = ("cc0", "public domain", "cc by 4.0", "cc by 3.0", "cc by 2.0", "pd")
MAX_BYTES = 6 * 1024 * 1024


def fetch(url, timeout=60):
    """GET with backoff. Commons returns 429 readily; respect it rather than hammer."""
    delay = 2.0
    for attempt in range(6):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == 5:
                raise
            wait = float(exc.headers.get("Retry-After") or delay)
            print(f"           (rate limited, waiting {wait:.0f}s)", flush=True)
            time.sleep(wait)
            delay = min(delay * 2, 30)
    raise RuntimeError("gave up after repeated rate limiting")


def get(params):
    url = API + "?" + urllib.parse.urlencode(params)
    return json.loads(fetch(url, timeout=30))


def meta(info, key):
    return (info.get("extmetadata", {}).get(key, {}) or {}).get("value", "") or ""


def strip_html(text):
    out, depth = [], 0
    for ch in text:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return " ".join("".join(out).split())


def search(terms, limit=25):
    data = get({
        "action": "query", "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:audio {terms}",
        "gsrlimit": limit, "gsrnamespace": 6,
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
    })
    return list((data.get("query", {}).get("pages") or {}).values())


# Wiktionary/Lingua Libre pronunciation recordings dominate audio search results
# and are tiny, so a "smallest file" heuristic picks them every time. They are
# someone saying a word, not the sound of the thing.
_JUNK_TITLE = ("ll-q", "pronunciation", "prononciation", "-ltr-", "spoken",
               "wikipedia", "audio de", "voice of", "isrc")


def _relevant(title, terms):
    """Require at least one search word to appear in the file's own title."""
    low = title.lower()
    return any(word in low for word in terms.lower().split() if len(word) > 3)


def pick(pages, terms):
    """Best permissively licensed file a browser can decode.

    Preference order: the title actually mentions what we searched for, the file
    is long enough to be a real recording, and among those the smallest wins so
    the bundled bank stays small.
    """
    best = None
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        if not info.get("url"):
            continue
        # Under ~30KB is almost always a one-word pronunciation clip.
        if not (30_000 <= info.get("size", 0) <= MAX_BYTES):
            continue
        title_low = page["title"].lower()
        if any(junk in title_low for junk in _JUNK_TITLE):
            continue
        if not _relevant(page["title"], terms):
            continue
        mime = info.get("mime", "")
        if not any(k in mime for k in ("ogg", "mpeg", "wav", "flac", "mp4")):
            continue
        licence = strip_html(meta(info, "LicenseShortName")).lower()
        if not any(ok in licence for ok in OK_LICENCES):
            continue
        if "sa" in licence.split():          # skip share-alike
            continue
        cand = {
            "title": page["title"],
            "url": info["url"],
            "size": info["size"],
            "mime": mime,
            "licence": strip_html(meta(info, "LicenseShortName")),
            "author": strip_html(meta(info, "Artist")) or "Unknown",
            "page": info.get("descriptionurl", ""),
        }
        if best is None or cand["size"] < best["size"]:
            best = cand
    return best


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "app/static/sounds/_raw"
    os.makedirs(out_dir, exist_ok=True)
    manifest = []

    existing = {}
    manifest_path = os.path.join(out_dir, "manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path) as fh:
            for row in json.load(fh):
                if os.path.exists(row.get("file", "")):
                    existing[row["slug"]] = row

    for slug, label_en, label_fr, terms in WANTED:
        if slug in existing:                          # resume, do not refetch
            manifest.append(existing[slug])
            print(f"{slug:10} already have it")
            continue
        print(f"{slug:10} searching…", flush=True)
        try:
            chosen = pick(search(terms, limit=40), terms)
        except Exception as exc:                      # network hiccup, keep going
            print(f"           ! {exc}")
            continue
        if not chosen:
            print("           ! nothing permissively licensed found")
            continue
        ext = {"audio/ogg": "ogg", "application/ogg": "ogg", "audio/mpeg": "mp3",
               "audio/wav": "wav", "audio/x-wav": "wav", "audio/flac": "flac",
               "audio/mp4": "m4a"}.get(chosen["mime"], "bin")
        dest = os.path.join(out_dir, f"{slug}.{ext}")
        try:
            data = fetch(chosen["url"])
        except Exception as exc:
            print(f"           ! download failed: {exc}")
            continue
        with open(dest, "wb") as fh:
            fh.write(data)
        chosen.update(slug=slug, label_en=label_en, label_fr=label_fr, file=dest)
        manifest.append(chosen)
        with open(manifest_path, "w") as fh:
            json.dump(manifest, fh, indent=2, ensure_ascii=False)
        print(f"           {os.path.basename(dest)}  {chosen['size']//1024}KB  {chosen['licence']}")
        time.sleep(2.5)                               # be polite to the API

    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    print(f"\n{len(manifest)}/{len(WANTED)} sounds fetched -> {out_dir}")


if __name__ == "__main__":
    main()

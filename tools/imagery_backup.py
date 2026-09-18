#!/usr/bin/env python3
"""
Back up Imagery (Base44) canvases into self-contained bundles.

The app's own per-canvas export carries metadata and *remote* media URLs, so the
JSON alone rots the moment the Base44 host goes away. This walks those URLs,
pulls the media down, and rewrites the JSON to point at local files -- while
keeping the original remote URL alongside, so a bundle still re-imports to
Base44 and still feeds a rewrite.

Two modes:
  local  (default) -- operate on .json files you exported from the app's UI.
  bulk   (--bulk)  -- pull every canvas from the app's public entities API.
                      Read-only GETs, but it enumerates a third-party service,
                      so it is opt-in rather than the default.

Stdlib only: runs on Wintermute, the Macs, anywhere with python3.
"""
import argparse, json, os, re, sys, urllib.request, urllib.error
from pathlib import Path

APP_ID   = "68a26cc71947ac0be6d6a35c"
API_ROOT = "https://imagery.base44.app/api/apps"
ENTITIES = ("SoundImage", "CustomSound", "GalleryRoom", "GalleryConfig")
TIMEOUT  = 60

# Every media-bearing key seen in a real export. `url` is the one that actually
# holds custom recordings; `sound_url` is null in practice but carried anyway,
# since a future export version may start populating it.
MEDIA_KEYS = ("image_url", "url", "sound_url", "file_url", "thumbnail_url")


def fetch(url, binary=True):
    req = urllib.request.Request(url, headers={"X-App-Id": APP_ID,
                                               "User-Agent": "imagery-backup/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
    return data if binary else data.decode("utf-8")


def safe_name(s, fallback="untitled"):
    s = re.sub(r"[^\w.\- ]+", "_", str(s or "")).strip().rstrip(".")
    return (s or fallback)[:120]


def local_filename(url):
    """Base44 media URLs end in <hash>_<original-name>. Keep that -- it is both
    unique and human-readable, which beats hashing the URL ourselves."""
    base = safe_name(url.rstrip("/").split("/")[-1].split("?")[0], "asset")
    return base or "asset"


def pull_media(url, media_dir, stats):
    """Download one asset if absent. Returns the path relative to the bundle."""
    fname = local_filename(url)
    dest  = media_dir / fname
    rel   = f"media/{fname}"
    if dest.exists() and dest.stat().st_size > 0:
        stats["skipped"] += 1
        return rel
    try:
        data = fetch(url)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"    ! FAILED {url}\n      {e}", file=sys.stderr)
        stats["failed"] += 1
        return None
    dest.write_bytes(data)
    stats["downloaded"] += 1
    stats["bytes"] += len(data)
    print(f"    + {fname} ({len(data):,} bytes)")
    return rel


def localize(node, media_dir, stats):
    """Walk the canvas, pulling every media URL and rewriting it in place.

    The remote URL is preserved as <key>_remote so the bundle stays a valid
    Base44 import; only the live key is repointed at the local copy.
    """
    if isinstance(node, list):
        for item in node:
            localize(item, media_dir, stats)
    elif isinstance(node, dict):
        for key in MEDIA_KEYS:
            url = node.get(key)
            if isinstance(url, str) and url.startswith("http"):
                rel = pull_media(url, media_dir, stats)
                if rel:
                    node[f"{key}_remote"] = url
                    node[key] = rel
        for value in node.values():
            if isinstance(value, (dict, list)):
                localize(value, media_dir, stats)


def bundle(canvas, out_root, stats):
    name = safe_name(canvas.get("name"), "untitled-canvas")
    dest = out_root / name
    (dest / "media").mkdir(parents=True, exist_ok=True)
    zones = canvas.get("sound_zones") or []
    print(f"  {name}  ({len(zones)} zone{'s' if len(zones) != 1 else ''})")
    localize(canvas, dest / "media", stats)
    (dest / "canvas.json").write_text(json.dumps(canvas, indent=2, ensure_ascii=False))
    stats["canvases"] += 1
    return dest


def load_local(paths):
    """Accept .json files or directories containing them."""
    files = []
    for p in paths:
        p = Path(p).expanduser()
        if p.is_dir():
            files += sorted(p.glob("*.json"))
        elif p.is_file():
            files.append(p)
        else:
            print(f"! no such path: {p}", file=sys.stderr)
    for f in files:
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"! skipping {f.name}: {e}", file=sys.stderr)
            continue
        if not isinstance(data, dict) or "sound_zones" not in data:
            print(f"! skipping {f.name}: not an Imagery canvas export", file=sys.stderr)
            continue
        data.setdefault("name", f.stem)
        yield data


def load_bulk(out_root):
    """Pull all entities. Side entities are saved whole; canvases are bundled."""
    for entity in ENTITIES:
        url = f"{API_ROOT}/{APP_ID}/entities/{entity}"
        try:
            records = json.loads(fetch(url, binary=False))
        except Exception as e:
            print(f"! {entity}: {e}", file=sys.stderr)
            continue
        print(f"  {entity}: {len(records)} record(s)")
        if entity == "SoundImage":
            canvases = records
        else:
            out_root.mkdir(parents=True, exist_ok=True)
            (out_root / f"{entity}.json").write_text(
                json.dumps(records, indent=2, ensure_ascii=False))
    for c in canvases:
        c.setdefault("export_version", "1.0")
        yield c


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help=".json exports, or directories of them")
    ap.add_argument("-o", "--out", default=os.environ.get(
        "IMAGERY_OUT", "/media/fpop/b0a10632-e09f-4153-ac08-337cc316f4f1/imagery-backup"),
        help="output root (default: sdc1, per the standing storage rule)")
    ap.add_argument("--bulk", action="store_true",
                    help="pull every canvas from the public API instead of reading files")
    args = ap.parse_args()

    if not args.bulk and not args.files:
        ap.error("give .json export files, or --bulk to pull from the API")

    out_root = Path(args.out).expanduser()
    out_root.mkdir(parents=True, exist_ok=True)
    stats = dict(canvases=0, downloaded=0, skipped=0, failed=0, bytes=0)

    print(f"-> {out_root}")
    source = load_bulk(out_root) if args.bulk else load_local(args.files)
    for canvas in source:
        bundle(canvas, out_root, stats)

    print(f"\n{stats['canvases']} canvas(es) | {stats['downloaded']} downloaded, "
          f"{stats['skipped']} already present, {stats['failed']} failed | "
          f"{stats['bytes']/1e6:.1f} MB")
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())

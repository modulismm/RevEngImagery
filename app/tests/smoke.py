#!/usr/bin/env python3
"""End-to-end smoke test against a running container.

    docker run -d --name imagery-test -p 127.0.0.1:8011:8000 \
      -e IMAGERY_ADMIN=bear -e IMAGERY_ADMIN_PASSPHRASE='the blue kettle sings' \
      -e IMAGERY_SECURE_COOKIE=0 imagery:dev
    python3 tests/smoke.py http://127.0.0.1:8011

Exercises the real HTTP surface, which the unit tests (Flask test client) do
not: gunicorn, cookies over the wire, multipart uploads, static files.
"""
import io
import json
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8011"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 2

jar = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
csrf = ""
passed = failed = 0


def check(label, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  ok    {label}")
    else:
        failed += 1
        print(f"  FAIL  {label} {detail}")


def call(method, path, body=None, files=None, expect=200):
    req = urllib.request.Request(BASE + path, method=method)
    if csrf:
        req.add_header("X-CSRF-Token", csrf)
    if files:
        boundary = "----imagery"
        parts = []
        for name, (fn, data) in files.items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
                f"filename=\"{fn}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
                + data + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        req.data = b"".join(parts)
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    elif body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with opener.open(req, timeout=15) as res:
            raw = res.read()
            status = res.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(), exc.code
    data = None
    try:
        data = json.loads(raw)
    except Exception:
        pass
    return status, data


print(f"Smoke test against {BASE}")

status, _ = call("GET", "/healthz")
check("health endpoint", status == 200, status)

status, data = call("POST", "/api/login",
                    {"name": "bear", "passphrase": "the blue kettle sings"})
if status != 200:
    print("  NOTE  sign-in failed -- this script assumes a FRESH instance whose admin\n"
          "        passphrase is still 'the blue kettle sings'. Against an instance you\n"
          "        have already set up, every authenticated check below will fail.")
check("admin can sign in", status == 200 and data and data.get("csrf"), status)
csrf = (data or {}).get("csrf", "")
check("admin role reported", (data or {}).get("user", {}).get("role") == "admin")

status, data = call("POST", "/api/canvases", {"name": "Pioupiou"})
check("create canvas", status == 201, status)
cid = (data or {}).get("canvas", {}).get("id")

status, data = call("POST", "/api/upload/image", files={"file": ("t.png", PNG)})
check("upload a real png", status == 201, status)
image_path = (data or {}).get("path", "")

status, data = call("POST", "/api/upload/image",
                    files={"file": ("shell.png", b"<?php system($_GET[0]); ?>")})
check("reject a disguised upload", status == 400, status)

zone = {"id": "1", "sound_name": "Son 1", "x": 40.19, "y": 24.94, "radius": 225.94,
        "volume": 0.7, "startTime": 0, "endTime": 2.1, "url": "/media/audio/x.webm",
        "effects": {"reverbLevel": 31, "pitch": -2, "lowFreq": 2.5,
                    "midFreq": 0, "highFreq": 2.5, "isReversed": False}}
status, data = call("PUT", f"/api/canvases/{cid}",
                    {"image_path": image_path, "zones": [zone]})
got = (data or {}).get("canvas", {}).get("zones", [{}])[0]
check("zone survives a round trip",
      abs(got.get("radius", 0) - 225.94) < 0.01
      and abs(got.get("effects", {}).get("reverbLevel", 0) - 31) < 0.01
      and abs(got.get("effects", {}).get("pitch", 0) + 2) < 0.01, got)

status, _ = call("GET", f"/media/{image_path}")
check("uploaded media is served", status == 200, status)

status, data = call("GET", "/api/canvases?all=1")
check("admin sees every canvas", (data or {}).get("scope") == "all", data)

saved, csrf = csrf, ""
status, _ = call("POST", "/api/canvases", {"name": "nope"})
check("mutation without CSRF is refused", status == 403, status)
csrf = saved

status, data = call("POST", "/api/users", {"name": "mamie"})
check("admin can add a person", status == 201 and "setup_url" in (data or {}), status)

for path in ("/static/js/audio.js", "/static/js/app.js", "/static/css/app.css", "/"):
    status, _ = call("GET", path)
    check(f"serves {path}", status == 200, status)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)

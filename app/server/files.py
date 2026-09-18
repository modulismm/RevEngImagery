"""Upload handling.

Uploads are the main way a self-hosted app gets compromised, so nothing here
trusts the client: not the filename, not the declared content type, not the
extension. The stored name is random and the type is decided by sniffing magic
bytes, then mapped to an extension we choose.
"""
import os
import secrets

MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_AUDIO_BYTES = 25 * 1024 * 1024

# (magic prefix, offset, extension, mime). Checked in order.
_IMAGE_SIGS = [
    (b"\xff\xd8\xff", 0, "jpg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", 0, "png", "image/png"),
    (b"GIF87a", 0, "gif", "image/gif"),
    (b"GIF89a", 0, "gif", "image/gif"),
    (b"WEBP", 8, "webp", "image/webp"),
]
_AUDIO_SIGS = [
    (b"\x1a\x45\xdf\xa3", 0, "webm", "audio/webm"),   # Matroska/WebM
    (b"OggS", 0, "ogg", "audio/ogg"),
    (b"ID3", 0, "mp3", "audio/mpeg"),
    (b"\xff\xfb", 0, "mp3", "audio/mpeg"),
    (b"\xff\xf3", 0, "mp3", "audio/mpeg"),
    (b"RIFF", 0, "wav", "audio/wav"),
    (b"ftyp", 4, "m4a", "audio/mp4"),
]


def sniff(data: bytes, kind: str):
    """Return (extension, mime) or None. `kind` is 'image' or 'audio'."""
    sigs = _IMAGE_SIGS if kind == "image" else _AUDIO_SIGS
    for magic, offset, ext, mime in sigs:
        if data[offset:offset + len(magic)] == magic:
            # WEBP and WAV both start with RIFF; disambiguate.
            if ext == "wav" and data[8:12] == b"WEBP":
                continue
            if ext == "webp" and data[0:4] != b"RIFF":
                continue
            return ext, mime
    return None


def store(data: bytes, kind: str, upload_dir: str):
    """Validate and write. Returns (relative_path, mime) or raises ValueError."""
    limit = MAX_IMAGE_BYTES if kind == "image" else MAX_AUDIO_BYTES
    if not data:
        return _fail("The file was empty.")
    if len(data) > limit:
        return _fail(f"That file is larger than {limit // (1024 * 1024)} MB.")
    sniffed = sniff(data, kind)
    if not sniffed:
        return _fail("That does not look like a "
                     + ("picture" if kind == "image" else "sound") + " file.")
    ext, mime = sniffed
    name = f"{secrets.token_hex(16)}.{ext}"
    sub = os.path.join(upload_dir, kind)
    os.makedirs(sub, exist_ok=True)
    with open(os.path.join(sub, name), "wb") as fh:
        fh.write(data)
    return f"{kind}/{name}", mime


def _fail(msg):
    raise ValueError(msg)


def safe_join(upload_dir: str, rel: str) -> str | None:
    """Resolve a stored path, refusing anything that escapes the upload root."""
    if not rel:
        return None
    root = os.path.realpath(upload_dir)
    target = os.path.realpath(os.path.join(root, rel))
    if target != root and not target.startswith(root + os.sep):
        return None
    return target if os.path.isfile(target) else None

"""Media from the web (App. B): stream to tmp, sniff by magic bytes, strip images at once (§7.2.2).

Nothing is trusted from the client: the declared content type and file name are ignored.
"""

import secrets as pysecrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from moira.errors import ValidationFailed
from moira.media.images import prepare
from moira.media.sniff import AUDIO_TYPES, IMAGE_TYPES, sniff

MAX_IMAGES = 10
MAX_IMAGE_BYTES = 20 * 1024 * 1024
# ~3 minutes of compressed speech is well under 6 MB; the recorder stops at 3 minutes.
MAX_AUDIO_BYTES = 6 * 1024 * 1024
CHUNK = 64 * 1024


@dataclass
class Media:
    kind: str = "text"  # text | photo | album | voice
    paths: list[str] = field(default_factory=list)
    meta: dict[str, Any] | None = None


async def _spool(f: UploadFile, tmp: Path, limit: int) -> Path:
    target = tmp / f"{pysecrets.token_hex(12)}.upload"
    size = 0
    try:
        with target.open("wb") as out:
            while chunk := await f.read(CHUNK):
                size += len(chunk)
                if size > limit:
                    raise ValidationFailed("That file is too large.")
                out.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def _cleanup(paths: list[Path]) -> None:
    for p in paths:
        p.unlink(missing_ok=True)


async def read_uploads(tmp: Path, images: list[UploadFile], audio: UploadFile | None) -> Media:
    """Validate and store uploads; on any error every stored file is deleted."""
    if audio is not None and images:
        raise ValidationFailed("Send a voice note or images, not both.")
    if len(images) > MAX_IMAGES:
        raise ValidationFailed(f"Up to {MAX_IMAGES} images at a time.")
    tmp.mkdir(parents=True, exist_ok=True)
    stored: list[Path] = []
    try:
        if audio is not None:
            p = await _spool(audio, tmp, MAX_AUDIO_BYTES)
            stored.append(p)
            mime = sniff(p)
            if mime not in AUDIO_TYPES:
                raise ValidationFailed("That doesn’t look like a voice note.")
            return Media("voice", [str(p)], {"mime": mime, "bytes": p.stat().st_size})
        out: list[str] = []
        for f in images:
            p = await _spool(f, tmp, MAX_IMAGE_BYTES)
            stored.append(p)
            mime = sniff(p)
            if mime not in IMAGE_TYPES:
                raise ValidationFailed("Only JPEG, PNG, WebP or GIF images can be saved.")
            ready = prepare(p)  # downscaled, EXIF stripped; the original is deleted
            stored.append(ready)
            out.append(str(ready))
        if not out:
            return Media()
        return Media("album" if len(out) > 1 else "photo", out, {"count": len(out)})
    except BaseException:
        _cleanup(stored)
        raise

"""Images (§7.2.2): downscale, strip EXIF (including GPS), re-encode JPEG, delete the original."""

from pathlib import Path

from PIL import Image

from moira.errors import ValidationFailed
from moira.media.sniff import IMAGE_TYPES, sniff

Image.MAX_IMAGE_PIXELS = 40_000_000
MAX_SIDE = 1280


def prepare(src: Path) -> Path:
    """Return a downscaled EXIF-free JPEG next to ``src``; the original is deleted."""
    kind = sniff(src)
    if kind not in IMAGE_TYPES:
        src.unlink(missing_ok=True)
        raise ValidationFailed("not a supported image")
    out = src.with_name(src.stem + ".prepared.jpg")
    try:
        with Image.open(src) as img:
            if img.format == "JPEG":
                img.draft("RGB", (1600, 1600))
            img.seek(0)
            frame = img.convert("RGB")
            frame.thumbnail((MAX_SIDE, MAX_SIDE))
            # A fresh image carries no EXIF, ICC or XMP blocks: nothing about where it was taken.
            clean = Image.new("RGB", frame.size)
            clean.paste(frame)
            clean.save(out, "JPEG", quality=85, optimize=True)
    except (OSError, Image.DecompressionBombError) as exc:
        out.unlink(missing_ok=True)
        raise ValidationFailed("image could not be read") from exc
    finally:
        src.unlink(missing_ok=True)
    return out

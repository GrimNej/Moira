"""Short videos (§7.2.3): only MP4, at most 90 s, checked with ffprobe. Never transcoded here."""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from moira.errors import ValidationFailed
from moira.media.sniff import sniff

MAX_SECONDS = 90
MAX_BYTES_TELEGRAM = 20 * 1024 * 1024
MAX_BYTES_WEB = 25 * 1024 * 1024
MP4_FORMATS = {"mov,mp4,m4a,3gp,3g2,mj2"}  # ffprobe's name for the ISO-BMFF demuxer


class VideoTooLong(ValidationFailed):
    code = "video_too_long"


@dataclass
class Probe:
    seconds: float
    format_name: str


def probe(path: Path) -> Probe:
    exe = shutil.which("ffprobe")
    if exe is None:
        raise ValidationFailed("ffprobe is not installed")
    try:
        out = subprocess.run(  # noqa: S603  # argument list, no shell, fixed executable
            [
                exe, "-v", "error", "-protocol_whitelist", "file", "-f", "mp4",
                "-show_entries", "format=duration,format_name", "-of", "json", str(path),
            ],
            check=True,
            capture_output=True,
            timeout=20,
        )  # fmt: skip
        fmt = json.loads(out.stdout)["format"]
        return Probe(float(fmt.get("duration") or 0), str(fmt.get("format_name", "")))
    except (subprocess.SubprocessError, OSError, ValueError, KeyError) as exc:
        raise ValidationFailed("not a readable MP4") from exc


def check(path: Path, *, max_bytes: int = MAX_BYTES_TELEGRAM) -> Probe:
    """MP4 by magic bytes and by ffprobe, within the size and length limits."""
    if sniff(path) != "video/mp4":
        raise ValidationFailed("only MP4 videos can be read")
    if path.stat().st_size > max_bytes:
        raise VideoTooLong("video too large")
    p = probe(path)
    if p.format_name not in MP4_FORMATS:
        raise ValidationFailed("only MP4 videos can be read")
    if p.seconds <= 0 or p.seconds > MAX_SECONDS:
        raise VideoTooLong("video too long")
    return p

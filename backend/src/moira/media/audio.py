"""Voice (§7.2.1): convert to 16 kHz mono 16-bit WAV with ffmpeg, split long audio, delete input.

ffmpeg runs with an argument list (no shell), ``-nostdin``, a timeout, and at lower priority
on Linux. One media job runs at a time (the ``media`` lane).
"""

import os
import shutil
import subprocess
import wave
from pathlib import Path

from moira.errors import ValidationFailed
from moira.media.sniff import AUDIO_TYPES, sniff

SEGMENT_S = 570  # the API limit is 10 minutes per request
# The demuxer is pinned to the sniffed type (format allowlist, §10.1), and ffmpeg may open only
# local files, so a crafted file cannot make it read a playlist, a URL or another file.
DEMUXER = {
    "audio/ogg": "ogg",
    "audio/webm": "matroska",
    "audio/mp4": "mov",
    "video/mp4": "mov",
    "audio/wav": "wav",
    "audio/mpeg": "mp3",
}
SAFE_INPUT = ["-protocol_whitelist", "file"]


def _ffmpeg() -> list[str]:
    exe = shutil.which("ffmpeg")
    if exe is None:
        raise ValidationFailed("ffmpeg is not installed")
    nice = ["nice", "-n", "10"] if os.name == "posix" and shutil.which("nice") else []
    return [*nice, exe, "-nostdin", "-y", "-loglevel", "error"]


def duration_s(wav: Path) -> float:
    with wave.open(str(wav), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def to_wav(src: Path) -> list[Path]:
    """Convert; returns one WAV, or several ≤ 9.5-minute parts. The input is deleted."""
    kind = sniff(src)
    if kind not in AUDIO_TYPES:
        src.unlink(missing_ok=True)
        raise ValidationFailed("not a supported audio file")
    out = src.with_suffix(".wav")
    try:
        subprocess.run(  # noqa: S603  # argument list, no shell, fixed executable
            [
                *_ffmpeg(),
                *SAFE_INPUT,
                "-f",
                DEMUXER[kind],
                "-i",
                str(src),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                "-map_metadata",
                "-1",
                str(out),
            ],
            check=True,
            timeout=60,
            capture_output=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        out.unlink(missing_ok=True)
        raise ValidationFailed("audio could not be converted") from exc
    finally:
        src.unlink(missing_ok=True)
    if duration_s(out) <= SEGMENT_S:
        return [out]
    pattern = out.with_name(out.stem + ".part%03d.wav")
    try:
        subprocess.run(  # noqa: S603
            [
                *_ffmpeg(),
                *SAFE_INPUT,
                "-f",
                "wav",
                "-i",
                str(out),
                "-f",
                "segment",
                "-segment_time",
                str(SEGMENT_S),
                "-c",
                "copy",
                str(pattern),
            ],
            check=True,
            timeout=60,
            capture_output=True,
        )
    finally:
        out.unlink(missing_ok=True)
    return sorted(out.parent.glob(out.stem + ".part*.wav"))

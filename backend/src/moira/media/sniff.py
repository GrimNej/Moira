"""Identify media by magic bytes, never by name or claimed type (§10.1)."""

from pathlib import Path


def sniff_bytes(head: bytes) -> str | None:
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio/webm"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"M4A ", b"M4B "):
            return "audio/mp4"
        if brand in (b"heic", b"heix", b"mif1", b"msf1", b"hevc"):
            return "image/heic"
        return "video/mp4"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith((b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
        return "audio/mpeg"
    return None


def sniff(path: Path) -> str | None:
    with path.open("rb") as fh:
        return sniff_bytes(fh.read(32))


IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
AUDIO_TYPES = {"audio/ogg", "audio/webm", "audio/mp4", "audio/wav", "audio/mpeg", "video/mp4"}

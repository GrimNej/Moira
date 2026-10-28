"""T32: principle 2 (no media file remains after reading), EXIF removed, ASR request schema."""

import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
import respx
from PIL import Image

from moira.capture.service import CaptureInput
from moira.db.repos import nuggets
from moira.media.images import prepare
from moira.media.sniff import sniff_bytes
from moira.pipelines import asr_keywords
from moira.services import Services
from tests.conftest import World, run_jobs

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def jpeg_with_gps(path: Path) -> None:
    img = Image.new("RGB", (3000, 2000), "skyblue")
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    gps = {1: "N", 2: (27.0, 42.0, 0.0), 3: "E", 4: (85.0, 18.0, 0.0)}
    exif[0x8825] = gps
    img.save(path, "JPEG", exif=exif.tobytes())


def ogg(path: Path, seconds: int = 2) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-c:a",
            "libopus",
            str(path),
        ],
        check=True,
    )


def test_exif_is_removed_and_the_image_downscaled(tmp_path: Path) -> None:
    src = tmp_path / "photo.jpg"
    jpeg_with_gps(src)
    assert Image.open(src).getexif().get(0x8825)
    out = prepare(src)
    assert not src.exists()  # the original is deleted at once
    with Image.open(out) as img:
        assert max(img.size) <= 1280
        assert not img.getexif()
        assert "exif" not in img.info


def test_sniff() -> None:
    assert sniff_bytes(b"\xff\xd8\xff\xe0") == "image/jpeg"
    assert sniff_bytes(b"OggS\x00") == "audio/ogg"
    assert sniff_bytes(b"\x00\x00\x00\x18ftypheic") == "image/heic"
    assert sniff_bytes(b"MZ\x90\x00") is None


@needs_ffmpeg
async def test_p02_media_deleted_after_read_voice(app: Services, world: World) -> None:
    voice = app.tmp_dir / "voice.ogg"
    ogg(voice)
    app.extras["llm"].transcripts.append("call Josh about the logo on Friday")
    r = app.capture.capture(
        CaptureInput(
            channel="telegram", kind="voice", tmp_files=[str(voice)], external_id="1:5", chat_id=1
        ),
        world.owner,
    )
    assert r.nugget is not None
    await run_jobs(app)
    assert not voice.exists()
    assert not list(app.tmp_dir.glob("*.wav"))
    n = nuggets.get(world.memory(), r.nugget.id)
    assert n is not None and "call Josh about the logo" in n.user_text  # the user's own words
    assert n.status == "filed"


async def test_p02_media_deleted_after_read_photo(app: Services, world: World) -> None:
    src = app.tmp_dir / "shot.jpg"
    jpeg_with_gps(src)
    prepared = prepare(src)
    r = app.capture.capture(
        CaptureInput(
            channel="telegram",
            kind="photo",
            tmp_files=[str(prepared)],
            external_id="1:6",
            chat_id=1,
        ),
        world.owner,
    )
    assert r.nugget is not None
    await run_jobs(app)
    assert not prepared.exists()
    assert list(app.tmp_dir.iterdir()) == []
    n = nuggets.get(world.memory(), r.nugget.id)
    assert n is not None and "SCREENSHOT TEXT" in n.content_text  # read into text
    assert n.source == "screenshot"


@respx.mock
async def test_asr_request_matches_the_documented_schema(
    world: World, monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    from moira.ai.client import MetaLLM
    from moira.ai.usage import Budget
    from moira.config import load_settings

    monkeypatch.setenv("MODEL_API_KEY", "test-key-not-real")
    settings = load_settings()
    llm = MetaLLM(settings, Budget(world.system, settings, world.clock), world.clock)
    route = respx.post("https://api.meta.ai/v1/asr/transcribe").mock(
        return_value=httpx.Response(
            200,
            json={
                "sessionId": "s",
                "transcript": "hello there",
                "audioDurationMs": 2000,
                "turns": [],
            },
        )
    )
    wav = tmp_path / "clip.wav"
    import wave

    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    t = await llm.transcribe(wav=wav, keywords=["Josh", "XMP"], user_id=None)
    assert t.text == "hello there" and t.audio_ms == 2000
    req = route.calls.last.request
    assert req.headers["authorization"] == "Bearer test-key-not-real"
    body = req.content.decode("latin-1")
    assert 'name="request"' in body and 'name="audio"; filename="clip.wav"' in body
    start = body.index("{", body.index('name="request"'))
    payload = json.loads(body[start : body.index("}", start) + 1])
    assert payload == {
        "model": "muse-voice-transcribe-1.0",
        "audioEncoding": "WAV",
        "mode": "PUSH_TO_TALK",
        "languageBias": ["English"],
        "keywords": ["Josh", "XMP"],
    }
    row = world.system.execute("SELECT kind, audio_seconds FROM usage_ledger").fetchone()
    assert row["kind"] == "asr" and row["audio_seconds"] == 2


async def test_keywords_come_from_the_memory(app: Services, world: World) -> None:
    app.capture.capture(
        CaptureInput(channel="web", text="Josh's email is josh.r@example.com"), world.owner
    )
    await run_jobs(app)
    kw = asr_keywords(world.memory(), world.clock.now_ms())
    assert "Josh" in kw and len(kw) <= 50 and all(len(k) <= 40 for k in kw)

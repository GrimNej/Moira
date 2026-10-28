"""T44/T45: saving images and voice notes from the web, and the Android share target."""

import io
from pathlib import Path

from PIL import Image

from moira.api.uploads import MAX_IMAGES
from moira.db.repos import nuggets
from moira.services import Services
from tests.conftest import World
from tests.integration.test_api_memories import client


def png(color: str = "red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buf, "PNG")
    return buf.getvalue()


def tmp_files(app: Services) -> list[Path]:
    return [p for p in Path(app.tmp_dir).iterdir() if p.is_file()]


async def test_images_are_sniffed_stripped_and_saved(app: Services, world: World) -> None:
    async with client(app, world.owner) as c:
        r = await c.post(
            "/api/nuggets/media",
            files=[("images", ("a.txt", png(), "text/plain")), ("images", ("b", png("blue"), ""))],
            data={"text": "two palettes"},
        )
    assert r.status_code == 202, r.text
    n = nuggets.by_public_id(app.memories.open(world.owner.memory_path), r.json()["id"])
    assert n is not None
    assert n.source == "screenshot"
    # Only the prepared JPEGs remain; the originals were deleted.
    left = tmp_files(app)
    assert len(left) == 2
    assert all(p.name.endswith(".prepared.jpg") for p in left)


async def test_a_fake_image_is_refused_and_nothing_is_kept(app: Services, world: World) -> None:
    async with client(app, world.owner) as c:
        r = await c.post(
            "/api/nuggets/media",
            files=[
                ("images", ("ok.png", png(), "image/png")),
                ("images", ("evil.png", b"<script>alert(1)</script>", "image/png")),
            ],
        )
    assert r.status_code == 422
    assert tmp_files(app) == []


async def test_too_many_images(app: Services, world: World) -> None:
    files = [("images", (f"{i}.png", png(), "image/png")) for i in range(MAX_IMAGES + 1)]
    async with client(app, world.owner) as c:
        r = await c.post("/api/nuggets/media", files=files)
    assert r.status_code == 422


async def test_voice_note_is_queued_for_transcription(app: Services, world: World) -> None:
    ogg = b"OggS" + b"\x00" * 200
    async with client(app, world.owner) as c:
        r = await c.post("/api/nuggets/media", files={"audio": ("v.ogg", ogg, "audio/ogg")})
    assert r.status_code == 202
    n = nuggets.by_public_id(app.memories.open(world.owner.memory_path), r.json()["id"])
    assert n is not None and n.source == "voice"
    kinds = [
        row[0] for row in app.system.execute("SELECT kind FROM jobs WHERE ref = ?", (n.public_id,))
    ]
    assert "transcribe" in kinds


async def test_audio_that_is_not_audio_is_refused(app: Services, world: World) -> None:
    async with client(app, world.owner) as c:
        r = await c.post("/api/nuggets/media", files={"audio": ("v.ogg", png(), "audio/ogg")})
    assert r.status_code == 422
    assert tmp_files(app) == []


async def test_media_route_needs_the_csrf_header(app: Services, world: World) -> None:
    async with client(app, world.owner) as c:
        c.headers.pop("X-Moira")
        r = await c.post("/api/nuggets/media", data={"text": "hi"})
    assert r.status_code == 403


async def test_share_target_saves_and_redirects(app: Services, world: World) -> None:
    async with client(app, world.owner) as c:
        c.headers.pop("X-Moira")  # a share-target POST cannot send it
        r = await c.post(
            "/share",
            data={
                "title": "Palette ideas",
                "text": "https://example.com/p",
                "url": "https://example.com/p",
            },
            headers={"Origin": "https://moira.test"},
        )
    assert r.status_code == 303
    pid = r.headers["location"].removeprefix("/?saved=")
    n = nuggets.by_public_id(app.memories.open(world.owner.memory_path), pid)
    assert n is not None
    assert n.user_text.count("https://example.com/p") == 1


async def test_share_from_another_origin_is_refused(app: Services, world: World) -> None:
    async with client(app, world.owner) as c:
        r = await c.post(
            "/share", data={"text": "hello"}, headers={"Origin": "https://evil.example"}
        )
    assert r.status_code == 403

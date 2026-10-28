"""T52: short videos are read into found content; the remote and local files are deleted."""

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from moira.ai import prompts
from moira.ai.fake import FakeLLM
from moira.ai.video import parse
from moira.capture.service import CaptureInput
from moira.db.repos import nuggets as nuggets_repo
from moira.services import Services
from tests.conftest import World, run_jobs
from tests.unit.test_ai_client import llm as meta_llm
from tests.unit.test_ai_client import resp

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg missing"
)


def mp4(path: Path, seconds: int) -> Path:
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
         f"testsrc=duration={seconds}:size=160x120:rate=10", "-c:v", "mpeg4", str(path)],
        check=True,
    )  # fmt: skip
    return path


def test_parse_reads_the_line_format() -> None:
    r = parse(
        "SPEECH: here are five tools\nthat I use daily\nON_SCREEN_TEXT: none\n"
        "CREATOR: @editlab.demo\nPLATFORM: unknown\nTOPIC: AI tools for editing\nextra: x"
    )
    assert r.speech == "here are five tools that I use daily"
    assert r.on_screen_text == "" and r.platform == ""
    assert r.creator == "@editlab.demo"
    text = r.content_text()
    assert "Creator: @editlab.demo" in text and "On screen" not in text


def test_secrets_in_a_video_are_masked() -> None:
    card = "4111 1111 1111 1111"
    r = parse(f"SPEECH: my card is {card}\nTOPIC: payments")
    assert card not in r.content_text()


@needs_ffmpeg
async def test_a_ten_second_mp4_is_read_and_deleted(app: Services, world: World) -> None:
    clip = mp4(Path(app.tmp_dir) / "clip.mp4", 10)
    r = app.capture.capture(
        CaptureInput(channel="telegram", kind="video", text="", tmp_files=[str(clip)]),
        world.owner,
    )
    assert r.nugget is not None
    await run_jobs(app)
    conn = app.memories.open(world.owner.memory_path)
    n = nuggets_repo.by_public_id(conn, r.nugget.public_id)
    assert n is not None and "@editlab.demo" in n.content_text
    assert n.user_text == ""  # speech in a recording is not the user's words
    rows = nuggets_repo.research_for(conn, n.id)
    assert any(row["method"] == "video" for row in rows)
    assert not clip.exists()
    fake: FakeLLM = app.extras["llm"]
    assert any(c[0] == "video" for c in fake.calls)


@needs_ffmpeg
async def test_a_long_video_is_refused_without_an_ai_call(app: Services, world: World) -> None:
    clip = mp4(Path(app.tmp_dir) / "long.mp4", 95)
    told = AsyncMock()
    app.extras["tell_user"] = told
    app.capture.capture(
        CaptureInput(channel="telegram", kind="video", text="", tmp_files=[str(clip)]),
        world.owner,
    )
    await run_jobs(app)
    assert told.await_args is not None and told.await_args.args[2] == "video"
    fake: FakeLLM = app.extras["llm"]
    assert not any(c[0] == "video" for c in fake.calls)
    assert not clip.exists()


async def test_the_remote_file_is_deleted_even_when_the_call_fails(
    world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    c = meta_llm(world, monkeypatch)
    c.client.files.create = AsyncMock(return_value=SimpleNamespace(id="file_123"))
    c.client.files.delete = AsyncMock()
    clip = tmp_path / "v.mp4"
    clip.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)

    c.client.responses.create.return_value = resp("SPEECH: hi\nTOPIC: test")
    assert "SPEECH" in await c.video(prompt=prompts.load("video"), path=clip, user_id=None)
    c.client.files.delete.assert_awaited_with("file_123")
    body = c.client.responses.create.await_args.kwargs
    assert body["store"] is False and body["max_output_tokens"] >= 4000

    c.client.files.delete.reset_mock()
    c.client.responses.create.side_effect = RuntimeError("boom")
    with pytest.raises(Exception):  # noqa: B017
        await c.video(prompt=prompts.load("video"), path=clip, user_id=None)
    c.client.files.delete.assert_awaited_with("file_123")
    kwargs = c.client.files.create.await_args.kwargs
    assert kwargs["purpose"] == "user_data"
    assert kwargs["extra_body"]["expires_after"] == {"anchor": "created_at", "seconds": 3600}

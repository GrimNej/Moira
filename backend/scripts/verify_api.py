"""Verify Meta Model API facts the blueprint relies on (Appendix J). SPENDS CREDITS: ask first.

Usage (from backend/, with MODEL_API_KEY set; synthetic inputs only):

    uv run python scripts/verify_api.py structured image search asr video effort tokens
    uv run python scripts/verify_api.py all

Each check prints one line ``#J<n> <check>: PASS|FAIL <evidence>``. Copy the results into
docs/reference/EXTERNAL_API_NOTES.md (Appendix D format). Nothing here touches real user data.
"""

import asyncio
import base64
import io
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import wave
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI

BASE = os.environ.get("MODEL_API_BASE", "https://api.meta.ai/v1")
MODEL = os.environ.get("MODEL_MAIN", "muse-spark-1.3")
ASR_MODEL = os.environ.get("MODEL_ASR", "muse-voice-transcribe-1.0")

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "tags"],
    "properties": {
        "title": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}


def client() -> AsyncOpenAI:
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        sys.exit("MODEL_API_KEY is not set")
    return AsyncOpenAI(base_url=BASE, api_key=key, max_retries=0)


def usage_line(resp: Any) -> str:
    u = resp.usage
    cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", None)
    reasoning = getattr(getattr(u, "output_tokens_details", None), "reasoning_tokens", None)
    return (
        f"id={resp.id} in={u.input_tokens} cached={cached} out={u.output_tokens} "
        f"reasoning={reasoning}"
    )


async def check_structured() -> str:
    """J3: text.format json_schema with strict on the Responses API."""
    resp = await client().responses.create(
        model=MODEL,
        instructions="Return a title and three tags for the note.",
        input="Note: a synthetic reel about five AI tools for video editing.",
        text={
            "format": {"type": "json_schema", "name": "verify_v1", "schema": SCHEMA, "strict": True}
        },
        reasoning={"effort": "low"},
        max_output_tokens=300,
        store=False,
    )
    data = json.loads(resp.output_text)
    assert set(data) == {"title", "tags"}, data
    return f"keys={sorted(data)} {usage_line(resp)}"


def tiny_png() -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (320, 120), "white")
    ImageDraw.Draw(img).text((10, 50), "MOIRA TEST 38BDF8", fill="black")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


async def check_image() -> str:
    """J4: input_image with a base64 data URL."""
    url = "data:image/png;base64," + base64.b64encode(tiny_png()).decode()
    resp = await client().responses.create(
        model=MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Copy the text in the image exactly."},
                    {"type": "input_image", "image_url": url},
                ],
            }
        ],
        reasoning={"effort": "low"},
        max_output_tokens=200,
        store=False,
    )
    ok = "38BDF8" in resp.output_text.upper()
    return f"{'read' if ok else 'MISREAD'} text={resp.output_text[:60]!r} {usage_line(resp)}"


async def check_search() -> str:
    """J5 / J20: web_search tool with search_context_size and include results."""
    resp = await client().responses.create(
        model=MODEL,
        input="What is SQLite's FTS5 trigram tokenizer? One sentence with the source URL.",
        tools=[{"type": "web_search", "search_context_size": "low"}],
        include=["web_search_call.results"],
        reasoning={"effort": "low"},
        max_output_tokens=700,
        store=False,
    )
    searches = sum(1 for item in resp.output if item.type == "web_search_call")
    return f"searches={searches} {usage_line(resp)}"


async def check_effort() -> str:
    """J9: reasoning effort 'minimal' accepted."""
    resp = await client().responses.create(
        model=MODEL,
        input="Reply with the word ok.",
        reasoning={"effort": "minimal"},
        max_output_tokens=50,
        store=False,
    )
    return f"output={resp.output_text.strip()[:20]!r} {usage_line(resp)}"


async def check_tokens() -> str:
    """J24: POST /v1/responses/input_tokens counts tokens before a call."""
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(
            f"{BASE}/responses/input_tokens",
            headers={"Authorization": f"Bearer {os.environ['MODEL_API_KEY']}"},
            json={"model": MODEL, "input": "How many tokens is this sentence?"},
        )
    return f"status={r.status_code} body={r.text[:120]}"


def synthetic_wav(path: Path, seconds: float = 2.0, rate: int = 16000) -> None:
    """A mono 16-bit PCM WAV of a quiet tone (no real voice)."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * i / rate)))
            for i in range(int(seconds * rate))
        )
        w.writeframes(frames)


async def check_asr() -> str:
    """J6: multipart request + audio parts. A tone gives no words; the schema is the test."""
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "clip.wav"
        synthetic_wav(wav)
        request = {
            "model": ASR_MODEL,
            "audioEncoding": "WAV",
            "mode": "PUSH_TO_TALK",
            "languageBias": ["English"],
            "keywords": ["Moira", "Josh"],
        }
        with wav.open("rb") as audio:
            files = {
                "request": (None, json.dumps(request), "application/json"),
                "audio": ("clip.wav", audio, "audio/wav"),
            }
            async with httpx.AsyncClient(timeout=60) as http:
                r = await http.post(
                    f"{BASE}/asr/transcribe",
                    files=files,
                    headers={"Authorization": f"Bearer {os.environ['MODEL_API_KEY']}"},
                )
    return f"status={r.status_code} body={r.text[:160]}"


async def check_video() -> str:
    """J7: Files API upload with expiry, video understanding, delete."""
    with tempfile.TemporaryDirectory() as tmp:
        mp4 = Path(tmp) / "clip.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=3:size=320x240:rate=10",
                "-pix_fmt",
                "yuv420p",
                str(mp4),
            ],
            check=True,
        )
        c = client()
        with mp4.open("rb") as fh:
            f = await c.files.create(
                file=fh,
                purpose="user_data",
                extra_body={"expires_after": {"anchor": "created_at", "seconds": 3600}},
            )
        try:
            resp = await c.responses.create(
                model=MODEL,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Describe this video in one sentence."},
                            {"type": "input_file", "file_id": f.id},
                        ],
                    }
                ],
                reasoning={"effort": "low"},
                max_output_tokens=300,
                store=False,
            )
            text = resp.output_text[:60]
        finally:
            await c.files.delete(f.id)
    return f"file={f.id} deleted text={text!r} {usage_line(resp)}"


CHECKS: dict[str, tuple[str, Callable[[], Awaitable[str]]]] = {
    "structured": ("J3", check_structured),
    "image": ("J4", check_image),
    "search": ("J5", check_search),
    "asr": ("J6", check_asr),
    "video": ("J7", check_video),
    "effort": ("J9", check_effort),
    "tokens": ("J24", check_tokens),
}


async def main(names: list[str]) -> int:
    if names == ["all"]:
        names = list(CHECKS)
    failed = 0
    for name in names:
        ref, fn = CHECKS[name]
        try:
            print(f"#{ref} {name}: PASS {await fn()}")
        except Exception as exc:  # noqa: BLE001  # a verification script reports every failure
            failed += 1
            print(f"#{ref} {name}: FAIL {type(exc).__name__}: {str(exc)[:200]}")
    return 1 if failed else 0


if __name__ == "__main__":
    args = sys.argv[1:] or ["all"]
    unknown = [a for a in args if a != "all" and a not in CHECKS]
    if unknown:
        sys.exit(f"unknown checks: {unknown}; choose from {sorted(CHECKS)} or all")
    sys.exit(asyncio.run(main(args)))

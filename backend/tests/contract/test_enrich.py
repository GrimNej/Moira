"""T26 (real API, synthetic data only, spends credits): run with `make contract`.

Files the 10 update sequences of data/eval/updates.jsonl and 5 public reels with the real
model and checks the Now lines. Results go to docs/reference/EXTERNAL_API_NOTES.md and the
first row of docs/eval/RESULTS.md. Never runs in CI (`-m "not contract"`).
"""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

UPDATES = Path(__file__).resolve().parents[3] / "data" / "eval" / "updates.jsonl"
PUBLIC_REELS: list[str] = [
    # Fill in 5 public reels on D2 (never private posts): the post ids are checked in code.
]


def sequences() -> list[dict]:  # type: ignore[type-arg]
    return [json.loads(line) for line in UPDATES.read_text(encoding="utf-8").splitlines() if line]


@pytest.fixture
def real(app, monkeypatch):  # type: ignore[no-untyped-def]
    if not os.environ.get("MODEL_API_KEY"):
        pytest.skip("MODEL_API_KEY not set")
    from moira.ai.client import MetaLLM
    from moira.ai.usage import Budget
    from moira.config import load_settings

    settings = load_settings()
    app.extras["llm"] = MetaLLM(settings, Budget(app.system, settings, app.clock), app.clock)
    return app


@pytest.mark.parametrize("seq", sequences(), ids=lambda s: s["id"])
async def test_update_sequence(real, world, seq) -> None:  # type: ignore[no-untyped-def]
    from tests.conftest import run_jobs

    from moira.capture.service import CaptureInput
    from moira.db.repos import hubs

    for step in seq["steps"]:
        text = step.get("text", "") or "screenshot"
        real.capture.capture(CaptureInput(channel="web", text=text), world.owner)
        await run_jobs(real)
        expect = step.get("expect")
        if not expect:
            continue
        lines = " ".join(h.now_line.lower() for h in hubs.active(world.memory()))
        for word in expect.get("now_has", []):
            assert word.lower() in lines, (seq["id"], lines)
        for word in expect.get("now_lacks", []):
            assert word.lower() not in lines, (seq["id"], lines)


@pytest.mark.parametrize("url", PUBLIC_REELS)
async def test_public_reel_research(real, world, url) -> None:  # type: ignore[no-untyped-def]
    from moira.ai.research import research

    res = await research(real.extras["llm"], url, url, user_id=None)
    assert res.status in ("ok", "not_found")

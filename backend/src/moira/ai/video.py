"""VIDEO (§9.8.7): what a short video shows and says, as found content (never the user's words)."""

from dataclasses import dataclass
from pathlib import Path

from moira.ai import prompts
from moira.ai.client import LLM
from moira.capture import secrets

FIELDS = ("SPEECH", "ON_SCREEN_TEXT", "CREATOR", "PLATFORM", "TOPIC")
MAX_CHARS = 6000
NONE = {"", "none", "unknown", "n/a"}


@dataclass
class VideoReport:
    speech: str
    on_screen_text: str
    creator: str
    platform: str
    topic: str

    def content_text(self) -> str:
        """The text stored in ``content_text`` (masked, capped)."""
        parts = [
            ("Said in the video", self.speech),
            ("On screen", self.on_screen_text),
            ("Creator", self.creator),
            ("Platform", self.platform),
            ("About", self.topic),
        ]
        text = "\n".join(f"{k}: {v}" for k, v in parts if v)
        return secrets.mask(text)[0][:MAX_CHARS]


def parse(raw: str) -> VideoReport:
    """Read the line format; unknown lines are ignored, missing fields are empty."""
    got: dict[str, str] = {}
    current: str | None = None
    for line in raw.splitlines():
        key, sep, rest = line.partition(":")
        if sep and key.strip().upper() in FIELDS:
            current = key.strip().upper()
            got[current] = rest.strip()
        elif current is not None and line.strip():
            got[current] = (got[current] + " " + line.strip()).strip()
    clean = {k: ("" if v.strip().lower() in NONE else v.strip()) for k, v in got.items()}
    return VideoReport(*(clean.get(f, "") for f in FIELDS))


async def read(llm: LLM, path: Path, *, user_id: int | None) -> VideoReport:
    return parse(await llm.video(prompt=prompts.load("video"), path=path, user_id=user_id))

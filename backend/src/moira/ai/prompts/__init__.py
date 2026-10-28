"""Prompt files with front matter (§9.4). Loaded once; the version goes into every ledger row."""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

HERE = Path(__file__).parent
FRONT = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


@dataclass(frozen=True, slots=True)
class Prompt:
    name: str
    version: str
    model: str
    effort: str
    schema: str
    text: str

    @property
    def major(self) -> str:
        return self.version.split(".")[0]


@cache
def load(name: str) -> Prompt:
    raw = (HERE / f"{name}.md").read_text(encoding="utf-8")
    m = FRONT.match(raw)
    if m is None:
        raise ValueError(f"prompt {name} has no front matter")
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return Prompt(
        name=meta["name"],
        version=meta["version"],
        model=meta["model"],
        effort=meta["effort"],
        schema=meta["schema"],
        text=m.group(2).strip(),
    )


def escape(text: str) -> str:
    """Variable content can't close or forge a tagged block (§9.4)."""
    return text.replace("<", "‹").replace(">", "›")


def all_prompts() -> list[Prompt]:
    return [load(p.stem) for p in sorted(HERE.glob("*.md"))]

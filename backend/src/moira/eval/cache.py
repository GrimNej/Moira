"""A response cache for eval runs, keyed by (prompt version, input hash), so re-runs cost ~0."""

import hashlib
import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from moira.ai.client import LLM, InputPart, ResearchRaw, Transcript
from moira.ai.prompts import Prompt

T = TypeVar("T", bound=BaseModel)


class CachedLLM:
    def __init__(self, inner: LLM, folder: Path) -> None:
        self.inner = inner
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    def _key(self, prompt: Prompt, payload: str) -> Path:
        digest = hashlib.sha256(f"{prompt.name}:{prompt.version}:{payload}".encode()).hexdigest()
        return self.folder / prompt.name / f"{digest}.json"

    async def structured(
        self, *, prompt: Prompt, inputs: list[InputPart], schema: type[T], **kw: Any
    ) -> T:
        payload = json.dumps(
            [[p.text, hashlib.sha256(p.image_data_url.encode()).hexdigest()] for p in inputs]
        )
        path = self._key(prompt, payload)
        if path.exists():
            self.hits += 1
            return schema.model_validate_json(path.read_text(encoding="utf-8"))
        self.misses += 1
        out = await self.inner.structured(prompt=prompt, inputs=inputs, schema=schema, **kw)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(out.model_dump_json(), encoding="utf-8")
        return out

    async def research(self, *, prompt: Prompt, text: str, user_id: int | None) -> ResearchRaw:
        return await self.inner.research(prompt=prompt, text=text, user_id=user_id)

    async def video(self, *, prompt: Prompt, path: Path, user_id: int | None) -> str:
        return await self.inner.video(prompt=prompt, path=path, user_id=user_id)

    async def transcribe(
        self, *, wav: Path, keywords: list[str], user_id: int | None
    ) -> Transcript:
        return await self.inner.transcribe(wav=wav, keywords=keywords, user_id=user_id)

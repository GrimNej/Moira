"""The AI client (§9.2): Responses API via the openai SDK, ASR via httpx, retries, breaker.

Every Responses call sends ``store=False``. Prompts are never logged at INFO. Every call writes
a usage_ledger row, success or failure.
"""

import asyncio
import base64
import json
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from moira.ai.prompts import Prompt
from moira.ai.schemas import SCHEMAS
from moira.ai.usage import Budget, actual_usd, estimate_usd
from moira.clock import Clock
from moira.config import Settings
from moira.db.repos.usage import UsageRow
from moira.errors import (
    AiInvalidOutput,
    AiRejected,
    AiTransient,
    AiUnavailable,
)
from moira.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)
Effort = Literal["minimal", "low", "medium", "high", "xhigh"]


@dataclass(frozen=True, slots=True)
class InputPart:
    """A text block or an image (data URL) for a Responses input message."""

    text: str = ""
    image_data_url: str = ""

    @staticmethod
    def image(jpeg: bytes) -> "InputPart":
        return InputPart(image_data_url="data:image/jpeg;base64," + base64.b64encode(jpeg).decode())


@dataclass(frozen=True, slots=True)
class ResearchRaw:
    text: str
    sources: list[dict[str, str]]
    searches: int


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    audio_ms: int


class LLM(Protocol):
    async def structured(
        self,
        *,
        prompt: Prompt,
        inputs: list[InputPart],
        schema: type[T],
        effort: Effort,
        max_output_tokens: int,
        timeout_s: float,
        user_id: int | None,
        kind: str,
        model: str | None = None,
    ) -> T: ...

    async def research(self, *, prompt: Prompt, text: str, user_id: int | None) -> ResearchRaw: ...

    async def video(self, *, prompt: Prompt, path: Path, user_id: int | None) -> str: ...

    async def transcribe(
        self, *, wav: Path, keywords: list[str], user_id: int | None
    ) -> Transcript: ...


@dataclass
class Breaker:
    """5 consecutive transient failures within 2 minutes → open 120 s → one half-open probe."""

    clock: Clock
    threshold: int = 5
    window_ms: int = 120_000
    open_ms: int = 120_000
    failures: list[int] = field(default_factory=list)
    opened_at: int | None = None
    probing: bool = False

    def before(self) -> None:
        now = self.clock.now_ms()
        if self.opened_at is None:
            return
        if now - self.opened_at < self.open_ms:
            raise AiUnavailable(
                "circuit open", retry_after_s=(self.open_ms - (now - self.opened_at)) / 1000
            )
        if self.probing:
            raise AiUnavailable("circuit half-open", retry_after_s=5)
        self.probing = True

    def success(self) -> None:
        self.failures.clear()
        self.opened_at = None
        self.probing = False

    def failure(self) -> None:
        now = self.clock.now_ms()
        if self.probing:
            self.opened_at = now
            self.probing = False
            return
        self.failures = [t for t in self.failures if now - t <= self.window_ms] + [now]
        if len(self.failures) >= self.threshold:
            self.opened_at = now
            self.failures.clear()
            log.warning("ai_breaker_open")

    @property
    def is_open(self) -> bool:
        return self.opened_at is not None and self.clock.now_ms() - self.opened_at < self.open_ms


def responses_request(
    *,
    model: str,
    prompt: Prompt,
    inputs: list[InputPart],
    schema: dict[str, Any] | None,
    schema_name: str,
    effort: Effort,
    max_output_tokens: int,
    extra_text: str = "",
) -> dict[str, Any]:
    """The Responses request body (N.5): fixed instructions first, then variable blocks."""
    content: list[dict[str, Any]] = []
    for part in inputs:
        if part.image_data_url:
            content.append({"type": "input_image", "image_url": part.image_data_url})
        elif part.text:
            content.append({"type": "input_text", "text": part.text})
    if extra_text:
        content.append({"type": "input_text", "text": extra_text})
    body: dict[str, Any] = {
        "model": model,
        "instructions": prompt.text,
        "input": [{"role": "user", "content": content}],
        "reasoning": {"effort": effort},
        "max_output_tokens": max_output_tokens,
        "store": False,
    }
    if schema is not None:
        body["text"] = {
            "format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}
        }
    return body


def chat_request(body: dict[str, Any]) -> dict[str, Any]:
    """The same call on Chat Completions (STRUCTURED_TRANSPORT=chat, §9.2)."""
    content = []
    for part in body["input"][0]["content"]:
        if part["type"] == "input_image":
            content.append({"type": "image_url", "image_url": {"url": part["image_url"]}})
        else:
            content.append({"type": "text", "text": part["text"]})
    fmt = body.get("text", {}).get("format")
    out: dict[str, Any] = {
        "model": body["model"],
        "messages": [
            {"role": "system", "content": body["instructions"]},
            {"role": "user", "content": content},
        ],
        "max_completion_tokens": body["max_output_tokens"],
        "reasoning_effort": body["reasoning"]["effort"],
    }
    if fmt:
        out["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": fmt["name"], "schema": fmt["schema"], "strict": True},
        }
    return out


class MetaLLM:
    """The real client. Our own retry loop (jobs) handles retries: ``max_retries=0``."""

    def __init__(self, settings: Settings, budget: Budget, clock: Clock) -> None:
        from openai import AsyncOpenAI

        assert settings.model_api_key is not None
        self.settings = settings
        self.budget = budget
        self.clock = clock
        self.breaker = Breaker(clock)
        self.client = AsyncOpenAI(
            base_url=settings.model_api_base,
            api_key=settings.model_api_key.get_secret_value(),
            max_retries=0,
        )

    def _ledger(
        self,
        *,
        user_id: int | None,
        kind: str,
        model: str,
        ok: bool,
        started: float,
        prompt_version: str | None,
        usage: Any = None,
        searches: int = 0,
        audio_seconds: int = 0,
    ) -> None:
        inp = int(getattr(usage, "input_tokens", 0) or 0)
        out = int(getattr(usage, "output_tokens", 0) or 0)
        cached = int(getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0)
        reasoning = int(
            getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0
        )
        usd = actual_usd(model, inp, cached, out, searches, audio_seconds)
        self.budget.record(
            UsageRow(
                user_id=user_id,
                day_utc=self.budget.day(),
                kind=kind,
                model=model,
                est_usd=usd,
                ok=ok,
                created_at=self.clock.now_ms(),
                input_tokens=inp,
                cached_tokens=cached,
                output_tokens=out,
                reasoning_tokens=reasoning,
                web_searches=searches,
                audio_seconds=audio_seconds,
                prompt_version=prompt_version,
                latency_ms=int((_time.monotonic() - started) * 1000),
            )
        )
        log.info(
            "ai_call",
            kind=kind,
            model=model,
            prompt=prompt_version,
            input=inp,
            cached=cached,
            output=out,
            usd=round(usd, 5),
            ok=ok,
        )

    def _classify(self, exc: Exception) -> Exception:
        from openai import APIConnectionError, APIStatusError, APITimeoutError

        if isinstance(exc, APITimeoutError | APIConnectionError | asyncio.TimeoutError):
            return AiTransient(type(exc).__name__)
        if isinstance(exc, APIStatusError):
            if exc.status_code == 429 or exc.status_code >= 500:
                ra = exc.response.headers.get("retry-after") if exc.response else None
                return AiTransient(str(exc.status_code), float(ra) if ra else None)
            return AiRejected(f"{exc.status_code} request_id={exc.request_id}")
        return exc

    async def _call(self, body: dict[str, Any], timeout_s: float) -> Any:
        self.breaker.before()
        try:
            if self.settings.structured_transport == "chat" and "text" in body:
                resp = await self.client.chat.completions.create(
                    **chat_request(body), timeout=timeout_s
                )
            else:
                resp = await self.client.responses.create(**body, timeout=timeout_s)
        except Exception as exc:  # classified below
            err = self._classify(exc)
            if isinstance(err, AiTransient):
                self.breaker.failure()
            raise err from exc
        self.breaker.success()
        return resp

    @staticmethod
    def _text(resp: Any) -> str:
        if hasattr(resp, "output_text"):
            return str(resp.output_text)
        return str(resp.choices[0].message.content or "")

    async def structured(
        self,
        *,
        prompt: Prompt,
        inputs: list[InputPart],
        schema: type[T],
        effort: Effort,
        max_output_tokens: int,
        timeout_s: float,
        user_id: int | None,
        kind: str,
        model: str | None = None,
    ) -> T:
        model = model or (
            prompt.model if prompt.model.endswith("contributor") else self.settings.model_main
        )
        if not self.settings.ai_enabled:
            raise AiUnavailable("AI switched off", retry_after_s=600)
        chars = len(prompt.text) + sum(len(p.text) for p in inputs)
        images = sum(1 for p in inputs if p.image_data_url)
        self.budget.check(
            user_id=user_id, estimate=estimate_usd(model, chars, images, max_output_tokens)
        )
        body = responses_request(
            model=model,
            prompt=prompt,
            inputs=inputs,
            schema=SCHEMAS[schema],
            schema_name=f"{prompt.name}_v{prompt.major}",
            effort=effort,
            max_output_tokens=max_output_tokens,
        )
        started = _time.monotonic()
        try:
            resp = await self._call(body, timeout_s)
        except Exception:
            self._ledger(
                user_id=user_id,
                kind=kind,
                model=model,
                ok=False,
                started=started,
                prompt_version=prompt.version,
            )
            raise
        self._ledger(
            user_id=user_id,
            kind=kind,
            model=model,
            ok=True,
            started=started,
            prompt_version=prompt.version,
            usage=getattr(resp, "usage", None),
        )
        text = self._text(resp)
        try:
            return schema.model_validate_json(text)
        except ValidationError as err:
            repair = responses_request(
                model=model,
                prompt=prompt,
                inputs=inputs,
                schema=SCHEMAS[schema],
                schema_name=f"{prompt.name}_v{prompt.major}",
                effort=effort,
                max_output_tokens=max_output_tokens,
                extra_text=f"Your previous output failed validation: {err.errors()[:3]}. "
                "Return corrected JSON only.",
            )
            started = _time.monotonic()
            resp2 = await self._call(repair, timeout_s)
            self._ledger(
                user_id=user_id,
                kind=kind,
                model=model,
                ok=True,
                started=started,
                prompt_version=prompt.version,
                usage=getattr(resp2, "usage", None),
            )
            try:
                return schema.model_validate_json(self._text(resp2))
            except ValidationError:
                raise AiInvalidOutput(f"{prompt.name} output failed validation twice") from None

    async def research(self, *, prompt: Prompt, text: str, user_id: int | None) -> ResearchRaw:
        model = self.settings.model_main
        self.budget.check(
            user_id=user_id, estimate=estimate_usd(model, len(text) + 9000, 0, 700, 2), searches=2
        )
        body = {
            "model": model,
            "instructions": prompt.text,
            "input": text,
            "tools": [{"type": "web_search", "search_context_size": "low"}],
            "include": ["web_search_call.results"],
            "reasoning": {"effort": "low"},
            "max_output_tokens": 700,
            "store": False,
        }
        started = _time.monotonic()
        try:
            resp = await self._call(body, 90)
        except Exception:
            self._ledger(
                user_id=user_id,
                kind="research",
                model=model,
                ok=False,
                started=started,
                prompt_version=prompt.version,
            )
            raise
        searches, sources = parse_search_output(resp)
        self._ledger(
            user_id=user_id,
            kind="research",
            model=model,
            ok=True,
            started=started,
            prompt_version=prompt.version,
            usage=getattr(resp, "usage", None),
            searches=searches,
        )
        return ResearchRaw(self._text(resp), sources, searches)

    async def video(self, *, prompt: Prompt, path: Path, user_id: int | None) -> str:
        model = self.settings.model_main
        self.budget.check(
            user_id=user_id, estimate=estimate_usd(model, 60_000, 0, 4000), video=True
        )
        started = _time.monotonic()
        with path.open("rb") as fh:
            uploaded = await self.client.files.create(
                file=fh,
                purpose="user_data",
                extra_body={"expires_after": {"anchor": "created_at", "seconds": 3600}},
            )
        try:
            body = {
                "model": model,
                "instructions": prompt.text,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Report on this video."},
                            {"type": "input_file", "file_id": uploaded.id},
                        ],
                    }
                ],
                "reasoning": {"effort": "low"},
                "max_output_tokens": 4000,
                "store": False,
            }
            resp = await self._call(body, 120)
        finally:
            try:
                await self.client.files.delete(uploaded.id)
            except Exception as exc:  # noqa: BLE001  # it expires in an hour anyway
                log.warning("file_delete_failed", error=type(exc).__name__)
        self._ledger(
            user_id=user_id,
            kind="video",
            model=model,
            ok=True,
            started=started,
            prompt_version=prompt.version,
            usage=getattr(resp, "usage", None),
        )
        return self._text(resp)

    async def transcribe(
        self, *, wav: Path, keywords: list[str], user_id: int | None
    ) -> Transcript:
        """Multipart ``request`` (JSON) + ``audio`` (WAV) parts (§7.2.1, N.5)."""
        if not self.settings.ai_enabled:
            raise AiUnavailable("AI switched off", retry_after_s=600)
        self.budget.check(user_id=user_id, estimate=0.03)
        self.breaker.before()
        request = {
            "model": self.settings.model_asr,
            "audioEncoding": "WAV",
            "mode": "PUSH_TO_TALK",
            "languageBias": ["English"],
            "keywords": keywords[:50],
        }
        key = self.settings.model_api_key
        assert key is not None
        started = _time.monotonic()
        try:
            with wav.open("rb") as audio:
                files: dict[str, Any] = {
                    "request": (None, json.dumps(request), "application/json"),
                    "audio": ("clip.wav", audio, "audio/wav"),
                }
                async with httpx.AsyncClient(timeout=60) as http:
                    r = await http.post(
                        f"{self.settings.model_api_base}/asr/transcribe",
                        files=files,
                        headers={"Authorization": "Bearer " + key.get_secret_value()},
                    )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            self.breaker.failure()
            raise AiTransient(type(exc).__name__) from exc
        if r.status_code == 429 or r.status_code >= 500:
            self.breaker.failure()
            raise AiTransient(str(r.status_code), float(r.headers.get("retry-after", 0)) or None)
        if r.status_code >= 400:
            raise AiRejected(str(r.status_code))
        self.breaker.success()
        data = r.json()
        audio_ms = int(data.get("audioDurationMs") or 0)
        self._ledger(
            user_id=user_id,
            kind="asr",
            model=self.settings.model_asr,
            ok=True,
            started=started,
            prompt_version=None,
            audio_seconds=max(1, audio_ms // 1000),
        )
        return Transcript(str(data.get("transcript") or ""), audio_ms)


def parse_search_output(resp: Any) -> tuple[int, list[dict[str, str]]]:
    """Count web_search_call items; collect url_citation annotations and result entries (§7.5)."""
    searches = 0
    sources: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(url: str | None, title: str | None) -> None:
        if url and url not in seen:
            seen.add(url)
            sources.append({"url": url, "title": title or ""})

    for item in getattr(resp, "output", []) or []:
        itype = getattr(item, "type", "")
        if itype == "web_search_call":
            searches += 1
            for res in getattr(item, "results", None) or []:
                add(getattr(res, "url", None), getattr(res, "title", None))
        elif itype == "message":
            for part in getattr(item, "content", []) or []:
                for ann in getattr(part, "annotations", []) or []:
                    if getattr(ann, "type", "") == "url_citation":
                        add(getattr(ann, "url", None), getattr(ann, "title", None))
    return searches, sources

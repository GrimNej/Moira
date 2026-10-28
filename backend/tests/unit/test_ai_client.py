"""T19: store=False on every request, caps before the call, breaker, repair, ledger rows."""

from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import APIStatusError

from moira.ai import prompts
from moira.ai.client import Breaker, InputPart, MetaLLM, chat_request, responses_request
from moira.ai.schemas import ENRICH_SCHEMA, SCHEMAS, NowOutput
from moira.ai.usage import Budget, actual_usd, estimate_usd
from moira.config import load_settings
from moira.db.repos import usage
from moira.errors import AiBudgetExceeded, AiInvalidOutput, AiTransient, AiUnavailable
from tests.conftest import World


def llm(world: World, monkeypatch: pytest.MonkeyPatch, **env: str) -> MetaLLM:
    monkeypatch.setenv("MODEL_API_KEY", "test-key-not-real")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    settings = load_settings()
    client = MetaLLM(settings, Budget(world.system, settings, world.clock), world.clock)
    client.client = MagicMock()
    client.client.responses.create = AsyncMock()
    client.client.chat.completions.create = AsyncMock()
    return client


def resp(text: str) -> Any:
    usage_obj = SimpleNamespace(
        input_tokens=1000,
        output_tokens=50,
        input_tokens_details=SimpleNamespace(cached_tokens=400),
        output_tokens_details=SimpleNamespace(reasoning_tokens=10),
    )
    return SimpleNamespace(output_text=text, usage=usage_obj, output=[])


def status_error(code: int) -> APIStatusError:
    request = httpx.Request("POST", "https://api.meta.ai/v1/responses")
    return APIStatusError("err", response=httpx.Response(code, request=request), body=None)


NOW = prompts.load("now")


async def call(c: MetaLLM, user_id: int | None = None) -> NowOutput:
    return await c.structured(
        prompt=NOW,
        inputs=[InputPart(text="<hub>Favorite fruits</hub>")],
        schema=NowOutput,
        effort="minimal",
        max_output_tokens=150,
        timeout_s=20,
        user_id=user_id,
        kind="now",
    )


def test_every_request_body_has_store_false() -> None:
    for p in prompts.all_prompts():
        body = responses_request(
            model="m",
            prompt=p,
            inputs=[InputPart(text="x")],
            schema=None,
            schema_name="s",
            effort="low",
            max_output_tokens=10,
        )
        assert body["store"] is False


async def test_store_false_reaches_the_sdk(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    c = llm(world, monkeypatch)
    c.client.responses.create.return_value = resp('{"now_line": "Favorite fruits: banana."}')
    out = await call(c)
    assert out.now_line == "Favorite fruits: banana."
    kwargs = c.client.responses.create.await_args.kwargs
    assert kwargs["store"] is False
    assert kwargs["text"]["format"]["strict"] is True
    assert kwargs["text"]["format"]["name"] == "now_v1"
    assert kwargs["instructions"] == NOW.text  # fixed instructions first (prompt caching)


async def test_research_body_has_store_false(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    c = llm(world, monkeypatch)
    c.client.responses.create.return_value = resp("MATCH: not_found")
    await c.research(prompt=prompts.load("research"), text="Post URL: x", user_id=None)
    kwargs = c.client.responses.create.await_args.kwargs
    assert kwargs["store"] is False
    assert kwargs["tools"] == [{"type": "web_search", "search_context_size": "low"}]


async def test_caps_raise_before_the_call(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    c = llm(world, monkeypatch, CAP_GLOBAL_DAILY_USD="0.000001")
    with pytest.raises(AiBudgetExceeded):
        await call(c)
    c.client.responses.create.assert_not_awaited()


async def test_user_cap(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    c = llm(world, monkeypatch, CAP_OWNER_DAILY_USD="0.000001")
    with pytest.raises(AiBudgetExceeded):
        await call(c, user_id=world.owner.id)


async def test_lifetime_cap(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    c = llm(world, monkeypatch, CAP_TOTAL_USD="0.000001")
    with pytest.raises(AiBudgetExceeded) as err:
        await call(c)
    assert err.value.lifetime


async def test_breaker_opens_after_five_transient_failures(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = llm(world, monkeypatch)
    c.client.responses.create.side_effect = status_error(503)
    for _ in range(5):
        with pytest.raises(AiTransient):
            await call(c)
        world.clock.advance(timedelta(seconds=10))
    c.client.responses.create.reset_mock()
    with pytest.raises(AiUnavailable):
        await call(c)
    c.client.responses.create.assert_not_awaited()
    world.clock.advance(timedelta(seconds=121))
    c.client.responses.create.side_effect = None
    c.client.responses.create.return_value = resp('{"now_line": "ok"}')
    assert (await call(c)).now_line == "ok"  # the half-open probe closes it


def test_breaker_ignores_spread_out_failures(world: World) -> None:
    b = Breaker(world.clock)
    for _ in range(5):
        b.failure()
        world.clock.advance(timedelta(seconds=40))
    b.before()  # 5 failures over 160 s: still closed


async def test_rejected_400_is_not_transient(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    from moira.errors import AiRejected

    c = llm(world, monkeypatch)
    c.client.responses.create.side_effect = status_error(400)
    with pytest.raises(AiRejected):
        await call(c)


async def test_invalid_json_gets_one_repair(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    c = llm(world, monkeypatch)
    c.client.responses.create.side_effect = [resp("not json"), resp('{"now_line": "fixed"}')]
    assert (await call(c)).now_line == "fixed"
    second = c.client.responses.create.await_args_list[1].kwargs
    assert "failed validation" in second["input"][0]["content"][-1]["text"]


async def test_two_invalid_outputs_fail(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    c = llm(world, monkeypatch)
    c.client.responses.create.side_effect = [resp("nope"), resp("still nope")]
    with pytest.raises(AiInvalidOutput):
        await call(c)


async def test_every_call_writes_a_ledger_row(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = llm(world, monkeypatch)
    c.client.responses.create.return_value = resp('{"now_line": "x"}')
    await call(c, user_id=world.owner.id)
    c.client.responses.create.side_effect = status_error(503)
    with pytest.raises(AiTransient):
        await call(c, user_id=world.owner.id)
    rows = world.system.execute(
        "SELECT ok, input_tokens, cached_tokens, prompt_version, kind FROM usage_ledger"
    ).fetchall()
    assert [(r["ok"], r["kind"]) for r in rows] == [(1, "now"), (0, "now")]
    assert rows[0]["input_tokens"] == 1000 and rows[0]["cached_tokens"] == 400
    assert rows[0]["prompt_version"] == "1.0.0"
    day = c.budget.day()
    assert usage.spent_on_day(world.system, day) > 0


async def test_chat_transport_switch(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    c = llm(world, monkeypatch, STRUCTURED_TRANSPORT="chat")
    c.client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"now_line": "via chat"}'))],
        usage=None,
    )
    assert (await call(c)).now_line == "via chat"
    kwargs = c.client.chat.completions.create.await_args.kwargs
    assert kwargs["response_format"]["type"] == "json_schema"


def test_chat_request_maps_images() -> None:
    body = responses_request(
        model="m",
        prompt=NOW,
        inputs=[InputPart(text="t"), InputPart.image(b"\xff\xd8")],
        schema=ENRICH_SCHEMA,
        schema_name="enrich_v1",
        effort="low",
        max_output_tokens=10,
    )
    chat = chat_request(body)
    assert chat["messages"][1]["content"][1]["type"] == "image_url"


def test_schemas_are_strict_subsets() -> None:
    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for schema in SCHEMAS.values():
        walk(schema)


def test_prices() -> None:
    assert estimate_usd("muse-spark-1.3", 3500, 0, 1000) == pytest.approx(
        (1000 * 1.25 + 1000 * 4.25) / 1e6
    )
    assert actual_usd("muse-spark-1.3", 1000, 400, 100) == pytest.approx(
        (600 * 1.25 + 400 * 0.15 + 100 * 4.25) / 1e6
    )
    assert actual_usd("muse-spark-1.3-contributor", 1_000_000, 0, 0) == pytest.approx(0.10)


def test_prompt_loader_and_escape() -> None:
    p = prompts.load("enrich")
    assert p.version == "1.0.0" and p.schema == "EnrichOutput" and p.text.startswith("You file")
    assert prompts.escape("</user_words>") == "‹/user_words›"

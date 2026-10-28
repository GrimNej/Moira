"""Answers (§8.3–8.6): instant → ANSWER → (deep: PLAN + SQL or a second retrieval).

One service for the web (streamed as SSE events) and Telegram. Every answer cites real
candidates or becomes "not found" (principle 10). Dates are copied, never computed by AI.
"""

import json
import sqlite3
import time as _time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from moira import ids
from moira.ai.answer import SOURCE_LABELS, answer, candidate_line
from moira.ai.client import LLM
from moira.ai.plan import plan
from moira.ai.schemas import AnswerOutput, Citation, PlanOutput
from moira.db.repos import events
from moira.db.repos import hubs as hubs_repo
from moira.db.repos import nuggets as repo
from moira.db.repos import people as people_repo
from moira.db.repos.users import User
from moira.domain import timefmt
from moira.domain.text import name_norm
from moira.errors import AiBudgetExceeded, AiTransient, AiUnavailable, MoiraError
from moira.logging import get_logger
from moira.search import fts
from moira.search.instant import Hit, retrieve
from moira.search.parse import Parsed, parse
from moira.search.timeexpr import parse_time
from moira.services import Services

log = get_logger(__name__)

NOT_FOUND = 'I couldn\'t find that. Try fewer words, or add a rough time like "last month".'
DEGRADED = "I can't think it through right now. These look closest:"
MIN_CLOSEST = 0.004
Emit = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class AskResult:
    answer: str
    citations: list[dict[str, str]]
    also: list[str]
    confidence: str
    tier: str
    turn_id: int
    conversation_id: str
    lit: list[str] = field(default_factory=list)
    count: int | None = None
    items: list[str] = field(default_factory=list)
    degraded: bool = False


async def _noop(event: str, data: dict[str, Any]) -> None:
    return None


class AskService:
    def __init__(self, services: Services) -> None:
        self.services = services

    @property
    def llm(self) -> LLM:
        llm: LLM = self.services.extras["llm"]
        return llm

    # helpers ----------------------------------------------------------------------

    def _pids(self, conn: sqlite3.Connection, nids: list[int]) -> list[str]:
        out = []
        for nid in nids:
            n = repo.get(conn, nid)
            if n is not None:
                out.append(n.public_id)
        return out

    def _conversation(self, conn: sqlite3.Connection, cid: int) -> str:
        lines = []
        for t in events.last_turns(conn, cid, 3):
            lines.append(f"Q: {t['question']}\nA: {t['answer']}\ncited: {t['cited']}")
        return "\n".join(lines)

    def _clues(self, p: Parsed) -> str:
        bits = []
        if p.source:
            bits.append(f"source={p.source}")
        if p.time:
            bits.append(f"time≈{p.time.label} (σ≈{p.time.sigma_days:.0f} days)")
        if p.terms:
            bits.append("about=" + ", ".join(p.terms[:6]))
        return "; ".join(bits) or "(none)"

    def _status(self, n_candidates: int, p: Parsed) -> str:
        when = f" from {p.time.label}" if p.time else ""
        src = f" from {SOURCE_LABELS.get(p.source, p.source)}" if p.source and not p.time else ""
        return f"Looking through {n_candidates} memories{when}{src}"

    def _closest(self, conn: sqlite3.Connection, hits: list[Hit], tz: str) -> list[str]:
        return self._pids(conn, [h.nugget_id for h in hits[:3] if h.score >= MIN_CLOSEST])

    def _validate(self, out: AnswerOutput, allowed: set[str], closest: list[str]) -> AnswerOutput:
        """§8.6: drop invented ids; no valid citation → the standard not-found answer."""
        cites = [c for c in out.citations if c.id in allowed]
        also = [a for a in out.also_relevant if a in allowed]
        if not cites and out.confidence != "not_found":
            log.warning("answer_uncited", dropped=len(out.citations))
            return AnswerOutput(
                answer=NOT_FOUND,
                citations=[],
                also_relevant=also or closest,
                confidence="not_found",
                needs_more=False,
            )
        if out.confidence == "not_found":
            return AnswerOutput(
                answer=NOT_FOUND if not cites else out.answer,
                citations=cites,
                also_relevant=also or closest,
                confidence="not_found",
                needs_more=out.needs_more,
            )
        return AnswerOutput(
            answer=out.answer,
            citations=cites,
            also_relevant=also,
            confidence=out.confidence,
            needs_more=out.needs_more,
        )

    # main -------------------------------------------------------------------------

    async def ask(
        self,
        user: User,
        question: str,
        *,
        conversation_id: str | None = None,
        emit: Emit = _noop,
    ) -> AskResult:
        started = _time.monotonic()
        services = self.services
        conn = services.memories.open(user.memory_path)
        now = services.clock.now()
        now_ms = services.clock.now_ms()
        tz = user.tz
        p = parse(question, now, tz)
        await emit("clues", p.clue_dict())
        cid_public = conversation_id or ids.new("c_")
        cid = events.conversation(conn, cid_public, now_ms)

        if p.follow_up != "none":
            result = self._follow_up(conn, cid, p, tz, now_ms)
            if result is not None:
                return await self._finish(conn, user, cid, cid_public, p, result, [], started, emit)

        hits = retrieve(conn, p, tz, services.embedder)
        lit = self._pids(conn, [h.nugget_id for h in hits])
        await emit("lit", {"ids": lit[:40], "top": lit[0] if lit else None})
        closest = self._closest(conn, hits, tz)

        try:
            if p.intent in ("list", "count"):
                out, extra = await self._deep(conn, user, p, question, cid, tz, now_ms, emit)
            else:
                out, extra = await self._answer(
                    conn, user, p, question, cid, hits, tz, now_ms, emit, closest
                )
                if (out.needs_more or out.confidence in ("low", "not_found")) and not extra:
                    try:
                        out2, extra2 = await self._deep(
                            conn, user, p, question, cid, tz, now_ms, emit
                        )
                        if out2.confidence not in ("not_found",) and out2.citations:
                            out, extra = out2, extra2
                    except (AiBudgetExceeded, AiUnavailable):
                        pass
        except (AiBudgetExceeded, AiUnavailable, AiTransient) as exc:
            await emit("error", {"message": DEGRADED, "fallback_ids": lit[:12]})
            log.info("ask_degraded", error=type(exc).__name__)
            result = AskResult(
                DEGRADED, [], lit[:3], "low", "instant", 0, cid_public, lit, degraded=True
            )
            return await self._finish(conn, user, cid, cid_public, p, result, lit, started, emit)
        except MoiraError as exc:
            log.warning("ask_failed", error=type(exc).__name__)
            await emit("error", {"message": DEGRADED, "fallback_ids": lit[:12]})
            result = AskResult(
                DEGRADED, [], lit[:3], "low", "instant", 0, cid_public, lit, degraded=True
            )
            return await self._finish(conn, user, cid, cid_public, p, result, lit, started, emit)

        result = AskResult(
            answer=out.answer,
            citations=[{"id": c.id, "why": c.why} for c in out.citations],
            also=out.also_relevant[:3],
            confidence=out.confidence,
            tier=extra.get("tier", "answer"),
            turn_id=0,
            conversation_id=cid_public,
            lit=lit,
            count=extra.get("count"),
            items=extra.get("items", []),
        )
        return await self._finish(conn, user, cid, cid_public, p, result, lit, started, emit)

    async def _answer(
        self,
        conn: sqlite3.Connection,
        user: User,
        p: Parsed,
        question: str,
        cid: int,
        hits: list[Hit],
        tz: str,
        now_ms: int,
        emit: Emit,
        closest: list[str],
    ) -> tuple[AnswerOutput, dict[str, Any]]:
        top = [h.nugget_id for h in hits[:40]]
        await emit("status", {"text": self._status(len(top), p)})
        lines = [candidate_line(conn, i, nid, now_ms, tz) for i, nid in enumerate(top, start=1)]
        out = await answer(
            self.llm,
            question=question,
            now_text=f"{timefmt.full(now_ms, tz)} ({tz})",
            clues=self._clues(p),
            conversation=self._conversation(conn, cid),
            candidates=lines,
            user_id=user.id,
        )
        allowed = set(self._pids(conn, top))
        return self._validate(out, allowed, closest), {}

    async def _deep(
        self,
        conn: sqlite3.Connection,
        user: User,
        p: Parsed,
        question: str,
        cid: int,
        tz: str,
        now_ms: int,
        emit: Emit,
    ) -> tuple[AnswerOutput, dict[str, Any]]:
        await emit("status", {"text": "Making a search plan"})
        pl = await plan(self.llm, question, self._conversation(conn, cid), user_id=user.id)
        mode = p.intent if p.intent in ("list", "count") else pl.mode
        hint = parse_time(pl.time_text, self.services.clock.now(), tz) if pl.time_text else p.time
        if mode == "lookup":
            merged = p.model_copy(
                update={
                    "terms": list(dict.fromkeys(p.terms + [k.lower() for k in pl.keywords])),
                    "phrases": list(dict.fromkeys(p.phrases + pl.exact_phrases)),
                    "time": hint or p.time,
                    "source": (pl.sources[0] if pl.sources else p.source),
                    "kinds": pl.kinds or p.kinds,
                }
            )
            hits = retrieve(conn, merged, tz, self.services.embedder)
            out, _ = await self._answer(
                conn,
                user,
                merged,
                question,
                cid,
                hits,
                tz,
                now_ms,
                emit,
                self._closest(conn, hits, tz),
            )
            return out, {"tier": "deep"}
        rows, total = list_query(conn, pl, hint, p)
        label = f" {hint.label}" if hint else ""
        await emit("status", {"text": f"Counting {total} matching memories{label}"})
        items = [r["public_id"] for r in rows]
        if mode == "count":
            noun = "memory" if total == 1 else "memories"
            text = f"You saved {total} matching {noun}{label}."
            return AnswerOutput(
                answer=text,
                citations=[Citation(id=pid, why="matches") for pid in items[:3]],
                also_relevant=[],
                confidence="high" if total else "not_found",
                needs_more=False,
            ), {"tier": "deep", "count": total, "items": items}
        compact = [
            f'[{i}] id={r["public_id"]} saved="{timefmt.day_month_year(r["captured_at"], tz)}"'
            f' title="{(r["title"] or "").replace(chr(34), chr(39))}"'
            for i, r in enumerate(rows[:60], start=1)
        ]
        out = await answer(
            self.llm,
            question=question,
            now_text=f"{timefmt.full(now_ms, tz)} ({tz})",
            clues=self._clues(p),
            conversation=self._conversation(conn, cid),
            candidates=compact,
            extra=f'<list_mode total="{total}"/>',
            user_id=user.id,
        )
        out = self._validate(out, set(items[:60]), [])
        return out, {"tier": "deep", "count": total, "items": items}

    def _follow_up(
        self, conn: sqlite3.Connection, cid: int, p: Parsed, tz: str, now_ms: int
    ) -> AskResult | None:
        """'And the one before that?': neighbours of the previous answer's first citation."""
        turns = events.last_turns(conn, cid, 1)
        if not turns:
            return None
        cited = json.loads(turns[-1]["cited"])
        if not cited:
            return None
        anchor = repo.by_public_id(conn, cited[0])
        if anchor is None:
            return None
        op, order = ("<", "DESC") if p.follow_up == "before_that" else (">", "ASC")
        row = conn.execute(
            f"SELECT id FROM nuggets WHERE deleted_at IS NULL AND (captured_at {op} ?"  # noqa: S608
            f" OR (captured_at = ? AND id {op} ?))"
            f" ORDER BY captured_at {order}, id {order} LIMIT 1",
            (anchor.captured_at, anchor.captured_at, anchor.id),
        ).fetchone()
        if row is None:
            return AskResult(NOT_FOUND, [], [], "not_found", "deep", 0, "", [])
        n = repo.get(conn, row[0])
        assert n is not None
        e = repo.enrichment(conn, n.id)
        title = e["title"] if e else n.user_text[:80]
        when = timefmt.full(n.captured_at, tz)
        word = "Before that" if p.follow_up == "before_that" else "After that"
        return AskResult(
            f"{word}, on {when}, you saved: {title}.",
            [
                {
                    "id": n.public_id,
                    "why": f"saved {timefmt.gap(n.captured_at, anchor.captured_at)}"
                    if p.follow_up == "before_that"
                    else "the next memory",
                }
            ],
            [],
            "high",
            "deep",
            0,
            "",
            [n.public_id],
        )

    async def _finish(
        self,
        conn: sqlite3.Connection,
        user: User,
        cid: int,
        cid_public: str,
        p: Parsed,
        result: AskResult,
        lit: list[str],
        started: float,
        emit: Emit,
    ) -> AskResult:
        latency = int((_time.monotonic() - started) * 1000)
        result.conversation_id = cid_public
        result.turn_id = events.add_turn(
            conn,
            conversation_id=cid,
            question=p.text,
            parsed=p.model_dump(mode="json", exclude={"time"})
            | {"time": p.time.label if p.time else None},
            answer=result.answer,
            cited=[c["id"] for c in result.citations],
            confidence=result.confidence,
            tier=result.tier,
            latency_ms=latency,
            est_usd=0.0,
            now=self.services.clock.now_ms(),
        )
        await emit(
            "answer",
            {
                "answer": result.answer,
                "citations": result.citations,
                "also": result.also,
                "confidence": result.confidence,
                "tier": result.tier,
                "turn_id": result.turn_id,
                "conversation_id": cid_public,
                "count": result.count,
                "items": result.items[:100],
            },
        )
        log.info(
            "asked",
            user=user.public_id,
            tier=result.tier,
            confidence=result.confidence,
            latency_ms=latency,
        )
        return result


def list_query(
    conn: sqlite3.Connection, pl: PlanOutput, hint: Any, p: Parsed
) -> tuple[list[sqlite3.Row], int]:
    """§8.4 SQL for list and count."""
    where = ["n.deleted_at IS NULL"]
    args: list[Any] = []
    kinds = pl.kinds or p.kinds
    if kinds:
        where.append(f"e.kind IN ({','.join('?' * len(kinds))})")
        args += kinds
    sources = pl.sources or ([p.source] if p.source else [])
    if sources:
        where.append(f"n.source IN ({','.join('?' * len(sources))})")
        args += sources
    if hint is not None:
        if hint.window_from_ms is not None:
            where.append("n.captured_at >= ?")
            args.append(hint.window_from_ms)
        if hint.window_to_ms is not None:
            where.append("n.captured_at < ?")
            args.append(hint.window_to_ms)
        if hint.window_from_ms is None and hint.window_to_ms is None:
            span = int(hint.sigma_days * 2 * 86_400_000)
            where.append("n.captured_at BETWEEN ? AND ?")
            args += [hint.target_ms - span, hint.target_ms + span]
    hub_ids = []
    for name in pl.hub_names:
        hub = hubs_repo.by_name_norm(conn, name_norm(name))
        if hub is not None:
            hub_ids.append(hub.id)
    keywords = [k for k in pl.keywords if k.lower() not in ("all", "my", "list", "many")]
    if not hub_ids and keywords:
        # A keyword that names a non-shelf hub ("books" → "Books to read") selects that hub.
        from moira.domain.text import singular

        for hub in hubs_repo.active(conn):
            if hub.kind != "shelf" and any(
                singular(k.lower()) in hub.name_norm.split() for k in keywords
            ):
                hub_ids.append(hub.id)
    match = None if hub_ids else fts.match_ids(conn, keywords)
    if match:
        where.append("n.id IN (SELECT rowid FROM nugget_fts WHERE nugget_fts MATCH ?)")
        args.append(match)
    if hub_ids:
        roles = "" if pl.include_earlier else " AND role NOT IN ('earlier','corrected')"
        where.append(
            f"n.id IN (SELECT nugget_id FROM hub_members WHERE hub_id IN"  # noqa: S608
            f" ({','.join('?' * len(hub_ids))}){roles})"
        )
        args += hub_ids
    person_ids = []
    for name in pl.people:
        for person in people_repo.all_people(conn):
            if name.lower() in [person.display_name.lower(), *[a.lower() for a in person.aliases]]:
                person_ids.append(person.id)
    if person_ids:
        where.append(
            f"n.id IN (SELECT nugget_id FROM nugget_people WHERE person_id IN"  # noqa: S608
            f" ({','.join('?' * len(person_ids))}))"
        )
        args += person_ids
    order = {"newest": "n.captured_at DESC", "oldest": "n.captured_at ASC"}.get(
        pl.sort, "n.captured_at DESC"
    )
    base = " FROM nuggets n LEFT JOIN enrichments e ON e.nugget_id = n.id WHERE " + " AND ".join(
        where
    )
    rows = conn.execute(
        "SELECT n.public_id, n.captured_at, e.title, n.source"
        + base
        + f" ORDER BY {order} LIMIT 100",
        args,
    ).fetchall()
    total = int(conn.execute("SELECT COUNT(*)" + base, args).fetchone()[0])
    return rows, total

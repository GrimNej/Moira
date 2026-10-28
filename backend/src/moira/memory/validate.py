"""Validate a filing (§7.4.3, V1–V12): the safety net between the model and the memory.

The key rule is V5 (principle 7): a fact operation needs evidence that is a substring of the
user's own words. Found content can never change a fact.
"""

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Literal

from pydantic import ValidationError

from moira.ai.enrich import EnrichContext
from moira.ai.schemas import EnrichOutput, HubAction
from moira.capture import secrets
from moira.db.repos import hubs as hubs_repo
from moira.db.repos.nuggets import Nugget
from moira.domain.text import contains_evidence, name_norm
from moira.errors import ValidationFailed
from moira.logging import get_logger
from moira.memory.shelf import shelf_by_name, shelf_name_for

log = get_logger(__name__)

Mode = Literal["file", "refresh", "edit_refile"]
CHANGE_CUE = re.compile(
    r"(?i)\b(?:now|anymore|any more|no longer|switched|changed|instead|actually|these days"
    r"|from now on|used to)\b|\bnot\b.{0,40}\banymore\b|\bnot\b.{1,40}\bbut\b"
)
NOT_PEOPLE = {
    "i",
    "me",
    "my",
    "we",
    "you",
    "he",
    "she",
    "they",
    "it",
    "the",
    "a",
    "an",
    "and",
    "or",
    "today",
    "tomorrow",
    "yesterday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "google",
    "youtube",
    "instagram",
    "github",
    "apple",
    "microsoft",
    "meta",
    "telegram",
    "moira",
    "ai",
}


@dataclass
class Action:
    """A validated hub action, resolved to internal ids."""

    hub_id: int | None
    new_hub_name: str
    new_hub_kind: str
    role: str
    fact_op: str
    replaces: list[int]
    new_now_line: str
    evidence: str
    confidence: float
    also_add: list[int] = field(default_factory=list)
    is_primary: bool = False
    hub_kind: str = "topic"


@dataclass
class PersonRef:
    name: str
    person_id: int | None
    hint: str


@dataclass
class Validated:
    title: str
    summary: str
    kind: str
    tags: list[str]
    questions: list[str]
    image_text: str
    image_text_masked: bool
    structured_list: dict[str, object] | None
    guess: str
    needs_research: bool
    actions: list[Action]
    people: list[PersonRef]
    downgrades: list[str] = field(default_factory=list)


def parse(raw: str) -> EnrichOutput:
    """V1: the output must parse into the model (the client already tried one repair)."""
    try:
        return EnrichOutput.model_validate_json(raw)
    except ValidationError as err:
        raise ValidationFailed(f"enrich output invalid: {err.error_count()} errors") from None


def _trim(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _looks_like_person(name: str, hub_names: set[str]) -> bool:
    n = name.strip()
    if not n or not n[0].isupper() or len(n) > 40:
        return False
    first = n.split()[0].lower()
    return first not in NOT_PEOPLE and name_norm(n) not in hub_names


def validate(
    conn: sqlite3.Connection,
    out: EnrichOutput,
    ctx: EnrichContext,
    nugget: Nugget,
    *,
    mode: Mode = "file",
) -> Validated:
    downgrades: list[str] = []

    def downgrade(rule: str) -> None:
        downgrades.append(rule)
        log.info("validation.downgrade", rule=rule)

    # V2 trim
    title = _trim(out.title, 80) or _trim(nugget.user_text, 80) or "Saved item"
    summary = _trim(out.summary, 280)
    tags = [_trim(t.lower(), 24) for t in out.tags if t.strip()][:8]
    questions = [_trim(q, 120) for q in out.search_questions if q.strip()][:6]

    # V12 image text: ≤ 6,000 chars, masked
    image_text, masked = secrets.mask(out.image_text[:6000])
    image_text = image_text[:6000]

    existing = {h.name_norm: h for h in hubs_repo.active(conn)}
    all_known = {**ctx.candidate_hubs, **ctx.shelves}
    current_of = {
        hid: {m.nugget_id for m in hubs_repo.members(conn, hid, ("current",))}
        for hid in set(all_known.values())
    }
    already_current = {
        m.hub_id for m in hubs_repo.memberships(conn, nugget.id) if m.role == "current"
    }

    actions: list[Action] = []
    for a in out.hub_actions:
        act = _resolve(a, all_known, existing, downgrade)  # V3
        if act is None:
            continue
        if act.hub_id is not None:
            hub = hubs_repo.get(conn, act.hub_id)
            act.hub_kind = hub.kind if hub else "topic"
            current_of.setdefault(
                act.hub_id, {m.nugget_id for m in hubs_repo.members(conn, act.hub_id, ("current",))}
            )
        else:
            act.hub_kind = act.new_hub_kind or "topic"

        # V4: also_add only from similar nuggets, only on a new topic hub
        wanted = [ctx.similar[i] for i in a.also_add_nugget_ids if i in ctx.similar]
        if len(wanted) < len(a.also_add_nugget_ids):
            downgrade("V4")
        act.also_add = wanted if (act.hub_id is None and act.hub_kind == "topic") else []

        # V5: facts need a fact/person hub and evidence from the user's own words
        is_fact_hub = act.hub_kind in ("fact", "person")
        if act.fact_op != "none" or act.role == "current":
            ok = is_fact_hub and contains_evidence(nugget.user_text, act.evidence)
            if not ok:
                downgrade("V5")
                act.fact_op, act.role, act.replaces, act.new_now_line = "none", "member", [], ""

        # V6: replaced nuggets must be current members of that hub
        if act.fact_op in ("replace", "remove", "correct"):
            ids = [nid for pid, nid in ctx.similar.items() if pid in a.replaces_nugget_ids]
            ids += _ids_from_hub(conn, act.hub_id, a.replaces_nugget_ids)
            current = current_of.get(act.hub_id or -1, set())
            valid = [i for i in dict.fromkeys(ids) if i in current and i != nugget.id]
            if not valid:
                downgrade("V6")
                act.fact_op = "add" if act.fact_op == "replace" else "none"
                if act.fact_op == "none":
                    act.role = "member"
            act.replaces = valid

        # V7: a low-confidence replace needs a change cue in the user's words
        if (
            act.fact_op == "replace"
            and act.confidence < 0.75
            and not CHANGE_CUE.search(nugget.user_text)
        ):
            downgrade("V7")
            act.fact_op, act.replaces = "add", []

        # V8: fact ops need a Now line of 1–200 characters
        if act.fact_op != "none":
            line = act.new_now_line.strip()
            if not 1 <= len(line) <= 200:
                downgrade("V8")
                act.fact_op, act.role, act.replaces = "none", "member", []
            else:
                act.new_now_line = line

        # Filing modes (§7.4.7)
        if mode == "refresh" and (act.fact_op != "none" or act.role == "current"):
            act.fact_op, act.role, act.replaces, act.new_now_line = "none", "member", [], ""
        if mode == "edit_refile" and act.fact_op != "none" and act.hub_id not in already_current:
            downgrade("edit_scope")
            act.fact_op, act.role, act.replaces, act.new_now_line = "none", "member", [], ""
        if mode == "refresh" and act.hub_id is None:
            continue  # a refresh may add memberships to existing hubs only
        actions.append(act)

    # One action per hub (keep the first)
    seen: set[object] = set()
    unique = []
    for act in actions:
        key = act.hub_id if act.hub_id is not None else ("new", name_norm(act.new_hub_name))
        if key not in seen:
            seen.add(key)
            unique.append(act)
    actions = unique

    # V9: at least one action survives
    if not actions:
        downgrade("V9") if out.hub_actions else None
        shelf = shelf_by_name(
            conn, shelf_name_for(out.kind, nugget.source, nugget.user_text + " " + summary)
        )
        actions.append(
            Action(shelf.id, "", "", "member", "none", [], "", "", 1.0, hub_kind="shelf")
        )

    # V10: exactly one primary
    primary = next(
        (a for a in actions if a.hub_kind != "shelf" and a.role in ("current", "member")), None
    ) or next((a for a in actions if a.hub_kind == "shelf"), actions[0])
    primary.is_primary = True

    # V11: people
    hub_names = set(existing)
    people: list[PersonRef] = []
    for p in out.people:
        if p.person_id and p.person_id in ctx.people:
            people.append(PersonRef(p.name, ctx.people[p.person_id], p.hint))
        elif not p.person_id and _looks_like_person(p.name, hub_names):
            people.append(PersonRef(p.name.strip(), None, p.hint))
        else:
            downgrade("V11")

    lst: dict[str, object] | None = None
    if out.structured_list_items and out.structured_list_title:
        lst = {
            "title": _trim(out.structured_list_title, 80),
            "items": [_trim(i, 120) for i in out.structured_list_items][:50],
        }
    return Validated(
        title=title,
        summary=summary,
        kind=out.kind,
        tags=tags,
        questions=questions,
        image_text=image_text,
        image_text_masked=masked,
        structured_list=lst,
        guess=_trim(out.guess, 280),
        needs_research=out.needs_research,
        actions=actions,
        people=people,
        downgrades=downgrades,
    )


def _ids_from_hub(conn: sqlite3.Connection, hub_id: int | None, public_ids: list[str]) -> list[int]:
    if hub_id is None or not public_ids:
        return []
    marks = ",".join("?" * len(public_ids))
    rows = conn.execute(
        f"SELECT n.id FROM nuggets n JOIN hub_members m ON m.nugget_id = n.id"  # noqa: S608
        f" WHERE m.hub_id = ? AND n.public_id IN ({marks})",
        (hub_id, *public_ids),
    ).fetchall()
    return [r[0] for r in rows]


def _resolve(
    a: HubAction,
    known: dict[str, int],
    existing: dict[str, hubs_repo.Hub],
    downgrade: object,
) -> Action | None:
    """V3: exactly one of a candidate id, a shelf id or a new name (≤ 40 chars)."""
    has_id = bool(a.hub_id.strip())
    has_name = bool(a.new_hub_name.strip())
    if has_id == has_name:
        downgrade("V3")  # type: ignore[operator]
        return None
    base: dict[str, object] = dict(
        role=a.role,
        fact_op=a.fact_op,
        replaces=[],
        new_now_line=a.new_now_line,
        evidence=a.evidence,
        confidence=max(0.0, min(1.0, a.confidence)),
    )
    if has_id:
        if a.hub_id not in known:
            downgrade("V3")  # type: ignore[operator]
            return None
        return Action(hub_id=known[a.hub_id], new_hub_name="", new_hub_kind="", **base)  # type: ignore[arg-type]
    name = re.sub(r"\s+", " ", a.new_hub_name).strip()
    if len(name) > 40:
        downgrade("V3")  # type: ignore[operator]
        return None
    match = existing.get(name_norm(name))
    if match is not None:
        return Action(hub_id=match.id, new_hub_name="", new_hub_kind="", **base)  # type: ignore[arg-type]
    return Action(hub_id=None, new_hub_name=name, new_hub_kind=a.new_hub_kind or "topic", **base)  # type: ignore[arg-type]

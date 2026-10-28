"""Apply a validated filing (§7.4.4) in one transaction: enrichment, hubs, facts, people,
events, indexes and the star. Every change is a hub event so it can be undone (§7.12).
"""

import json
import sqlite3
from dataclasses import dataclass, field

from moira import ids
from moira.capture import exacts as exacts_mod
from moira.db.repos import events
from moira.db.repos import hubs as hubs_repo
from moira.db.repos import nuggets as repo
from moira.db.repos import people as people_repo
from moira.db.repos import stars as stars_repo
from moira.db.repos.nuggets import Nugget
from moira.domain.text import name_norm
from moira.embed.model import Embedder
from moira.memory import indexing, people
from moira.memory.placement import hub_anchor, place_hub_center, place_star
from moira.memory.shelf import shelf_by_name, shelf_name_for
from moira.memory.validate import Action, Validated
from moira.search import vectors


@dataclass
class FilingResult:
    group_id: str
    fact_changed: bool
    now_changes: list[tuple[str, str]] = field(default_factory=list)  # (hub name, new Now line)
    touched_hubs: list[int] = field(default_factory=list)
    star: tuple[float, float] | None = None
    primary_hub_id: int | None = None


def _member_dict(m: hubs_repo.Member) -> dict[str, object]:
    return {
        "role": m.role,
        "is_primary": m.is_primary,
        "since": m.since,
        "until": m.until,
        "decided_by": m.decided_by,
        "confidence": m.confidence,
        "evidence": m.evidence,
    }


def _set_member(
    conn: sqlite3.Connection,
    group: str,
    hub_id: int,
    nugget_id: int,
    *,
    role: str,
    is_primary: bool,
    now: int,
    evidence: str = "",
    confidence: float | None = None,
) -> None:
    old = hubs_repo.member(conn, hub_id, nugget_id)
    if old is None:
        hubs_repo.add_member(
            conn,
            hub_id=hub_id,
            nugget_id=nugget_id,
            role=role,
            since=now,
            decided_by="ai",
            is_primary=is_primary,
            confidence=confidence,
            evidence=evidence,
        )
        new = hubs_repo.member(conn, hub_id, nugget_id)
        assert new is not None
        events.record(
            conn,
            group_id=group,
            event="member_added",
            actor="ai",
            now=now,
            hub_id=hub_id,
            nugget_id=nugget_id,
            after=_member_dict(new),
        )
    elif old.role != role:
        hubs_repo.set_role(conn, hub_id, nugget_id, role, None, "ai")
        if evidence:
            conn.execute(
                "UPDATE hub_members SET evidence = ? WHERE hub_id = ? AND nugget_id = ?",
                (evidence, hub_id, nugget_id),
            )
        events.record(
            conn,
            group_id=group,
            event="role_changed",
            actor="ai",
            now=now,
            hub_id=hub_id,
            nugget_id=nugget_id,
            before={"role": old.role, "until": old.until, "decided_by": old.decided_by},
            after={"role": role, "until": None},
        )


def _retire(
    conn: sqlite3.Connection, group: str, hub_id: int, nugget_id: int, role: str, now: int
) -> None:
    old = hubs_repo.member(conn, hub_id, nugget_id)
    if old is None or old.role == role:
        return
    hubs_repo.set_role(conn, hub_id, nugget_id, role, now, "ai")
    events.record(
        conn,
        group_id=group,
        event="role_changed",
        actor="ai",
        now=now,
        hub_id=hub_id,
        nugget_id=nugget_id,
        before={"role": old.role, "until": old.until, "decided_by": old.decided_by},
        after={"role": role, "until": now},
    )


def _set_now(conn: sqlite3.Connection, group: str, hub_id: int, line: str, now: int) -> bool:
    hub = hubs_repo.get(conn, hub_id)
    assert hub is not None
    if hub.now_line == line:
        return False
    hubs_repo.set_now_line(conn, hub_id, line, now)
    events.record(
        conn,
        group_id=group,
        event="now_changed",
        actor="ai",
        now=now,
        hub_id=hub_id,
        before={"now_line": hub.now_line},
        after={"now_line": line},
    )
    return True


def _create_hub(
    conn: sqlite3.Connection,
    group: str,
    act: Action,
    nugget: Nugget,
    kind: str,
    now: int,
    person_ids: list[int],
) -> int:
    vec = vectors.get(conn, "vec_nuggets", nugget.id)
    shelf = shelf_by_name(conn, shelf_name_for(kind, nugget.source, nugget.user_text))
    anchor = hub_anchor(conn, vec, (shelf.x, shelf.y))
    public_id = ids.new("h_")
    x, y = place_hub_center(conn, anchor, public_id)
    person_id = None
    if act.hub_kind == "person":
        match = people.find_by_name(conn, act.new_hub_name)
        if match is None:
            match = people_repo.create(
                conn,
                public_id=ids.new("p_"),
                display_name=act.new_hub_name,
                now=now,
                aliases=[act.new_hub_name.split()[0]],
            )
        person_id = match.id
        if match.id not in person_ids:
            person_ids.append(match.id)
    hub = hubs_repo.create(
        conn,
        public_id=public_id,
        name=act.new_hub_name,
        name_norm=name_norm(act.new_hub_name),
        kind=act.hub_kind,
        x=x,
        y=y,
        now=now,
        person_id=person_id,
    )
    events.record(
        conn,
        group_id=group,
        event="hub_created",
        actor="ai",
        now=now,
        hub_id=hub.id,
        after={"name": hub.name, "kind": hub.kind},
    )
    return hub.id


def apply_filing(
    conn: sqlite3.Connection,
    nugget: Nugget,
    v: Validated,
    *,
    group_id: str,
    model: str,
    prompt_version: str,
    raw_output: str,
    now: int,
    tz: str,
    embedder: Embedder | None,
) -> FilingResult:
    result = FilingResult(group_id=group_id, fact_changed=False)
    conn.execute("BEGIN IMMEDIATE")
    try:
        # 1. enrichment, image text, exacts from it
        repo.upsert_enrichment(
            conn,
            nugget.id,
            title=v.title,
            summary=v.summary,
            kind=v.kind,
            tags=v.tags,
            questions=v.questions,
            structured_list=v.structured_list,
            guess=v.guess,
            model=model,
            prompt_version=prompt_version,
            raw_output=raw_output,
            now=now,
        )
        if v.image_text and v.image_text not in nugget.content_text:
            repo.append_content_text(conn, nugget.id, v.image_text, now)
            repo.delete_exacts(conn, nugget.id, "content_text")
            repo.insert_exacts(
                conn,
                nugget.id,
                [e.as_tuple() for e in exacts_mod.extract(v.image_text, tz)],
                "content_text",
            )

        # 4 (first, so person hubs can link): people
        person_ids = people.resolve(conn, v.people, now=now)

        # 2–3. hubs, memberships, fact operations
        had_primary = hubs_repo.primary_hub(conn, nugget.id) is not None
        for act in v.actions:
            hub_id = act.hub_id
            if hub_id is None:
                hub_id = _create_hub(conn, group_id, act, nugget, v.kind, now, person_ids)
            act.hub_id = hub_id
            result.touched_hubs.append(hub_id)
            role = act.role if act.role in ("current", "member", "related") else "member"
            if act.fact_op == "remove":
                role = "member"  # it records the removal
            _set_member(
                conn,
                group_id,
                hub_id,
                nugget.id,
                role=role,
                is_primary=act.is_primary and not had_primary,
                now=now,
                evidence=act.evidence if act.fact_op != "none" else "",
                confidence=act.confidence,
            )
            for other in act.also_add:
                _set_member(conn, group_id, hub_id, other, role="member", is_primary=False, now=now)
            if act.fact_op in ("replace", "remove"):
                for r in act.replaces:
                    _retire(conn, group_id, hub_id, r, "earlier", now)
            elif act.fact_op == "correct":
                for r in act.replaces:
                    _retire(conn, group_id, hub_id, r, "corrected", now)
            changed = (
                act.fact_op != "none"
                and bool(act.new_now_line)
                and _set_now(conn, group_id, hub_id, act.new_now_line, now)
            )
            if changed:
                hub = hubs_repo.get(conn, hub_id)
                result.fact_changed = True
                result.now_changes.append((hub.name if hub else "", act.new_now_line))

        # Exactly one primary: V10 chose it; an earlier primary (re-filing) is kept.
        primary = next(a for a in v.actions if a.is_primary)
        current_primary = hubs_repo.primary_hub(conn, nugget.id)
        if current_primary is None and primary.hub_id is not None:
            hubs_repo.set_primary(conn, nugget.id, primary.hub_id)
            current_primary = hubs_repo.get(conn, primary.hub_id)
        result.primary_hub_id = current_primary.id if current_primary else None

        for pid in person_ids:
            people_repo.link_nugget(conn, nugget.id, pid)

        # 6. indexes
        indexing.index_full(conn, nugget.id, embedder)
        for other in {o for a in v.actions for o in a.also_add}:
            indexing.index_full(conn, other, embedder)
        for hid in dict.fromkeys(result.touched_hubs):
            indexing.index_hub(conn, hid, embedder)

        # 7. the star, placed once
        if stars_repo.get(conn, nugget.id) is None and result.primary_hub_id is not None:
            vec = vectors.get(conn, "vec_nuggets", nugget.id)
            x, y = place_star(
                conn,
                nugget_id=nugget.id,
                public_id=nugget.public_id,
                hub_id=result.primary_hub_id,
                vec=vec,
            )
            stars_repo.insert(conn, nugget.id, x, y, now=now)
            result.star = (x, y)
        from moira.memory.importance import recompute

        recompute(conn, now, [nugget.id])

        # 8. filed
        repo.set_status(conn, nugget.id, "filed", now)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return result


def enrichment_json(conn: sqlite3.Connection, nugget_id: int) -> dict[str, object] | None:
    e = repo.enrichment(conn, nugget_id)
    return json.loads(e["raw_output"]) if e is not None else None

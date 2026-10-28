"""Capture (§7.1): store first, think later. Nothing can be lost after the raw event insert."""

import sqlite3
from dataclasses import dataclass, field
from typing import Any, Literal

from moira import ids
from moira.capture import exacts as exacts_mod
from moira.capture import grouping, questions, secrets, urls
from moira.clock import Clock
from moira.db.repos import nuggets as repo
from moira.db.repos import users as users_repo
from moira.db.repos.nuggets import Nugget
from moira.db.repos.users import User
from moira.domain.text import normalize_input, text_hash
from moira.embed.model import Embedder
from moira.jobs.queue import Queue
from moira.logging import get_logger
from moira.memory import indexing
from moira.memory.registry import Memories

log = get_logger(__name__)

Channel = Literal["telegram", "web", "share", "import", "demo"]
MEDIA_SOURCE = {"photo": "screenshot", "album": "screenshot", "voice": "voice", "video": "video"}
MEDIA_JOB = {"voice": "transcribe", "video": "read_video", "document": "read_pdf"}


@dataclass
class CaptureInput:
    channel: Channel
    kind: str = "text"  # text|link|photo|album|voice|video|document|forward|location|contact|other
    text: str = ""
    external_id: str | None = None
    media_meta: dict[str, Any] | None = None
    original_posted_at: int | None = None
    forward_from: str | None = None
    media_group_id: str | None = None
    chat_id: int | None = None
    tmp_files: list[str] = field(default_factory=list)
    force_save: bool = False
    captured_at: int | None = None  # demo import only; otherwise "now"
    is_sample: bool = False


@dataclass
class CaptureResult:
    status: Literal["saved", "grouped", "duplicate", "question"]
    raw_event_id: int
    nugget: Nugget | None = None
    found_secrets: bool = False
    text: str = ""  # the masked text (the question text for questions)


class CaptureService:
    def __init__(
        self,
        *,
        system: sqlite3.Connection,
        memories: Memories,
        queue: Queue,
        clock: Clock,
        embedder: Embedder | None,
    ) -> None:
        self.system = system
        self.memories = memories
        self.queue = queue
        self.clock = clock
        self.embedder = embedder

    def capture(self, inp: CaptureInput, user: User) -> CaptureResult:
        conn = self.memories.open(user.memory_path)
        now = self.clock.now_ms()
        captured_at = inp.captured_at or now
        text, found = secrets.mask(normalize_input(inp.text))  # 1, 2
        has_media = bool(inp.tmp_files) or inp.kind in (
            "photo",
            "album",
            "voice",
            "video",
            "document",
        )
        url = urls.first_url(text)
        meta = dict(inp.media_meta or {})
        if inp.media_group_id:
            meta["media_group_id"] = inp.media_group_id
        if inp.tmp_files:
            meta["tmp_files"] = inp.tmp_files

        is_q = (
            inp.channel == "telegram"
            and not inp.force_save
            and questions.is_question(text, has_url=url is not None, has_media=has_media)
        )
        conn.execute("BEGIN IMMEDIATE")
        try:
            raw_id = repo.insert_raw_event(  # 3: nothing can be lost after this line
                conn,
                channel=inp.channel,
                kind="question" if is_q else inp.kind,
                text=text,
                received_at=now,
                external_id=inp.external_id,
                media_meta=meta or None,
                original_posted_at=inp.original_posted_at,
            )
            if is_q:  # 4
                conn.execute("COMMIT")
                return CaptureResult("question", raw_id, None, found, text)
            result = self._save(conn, inp, user, raw_id, text, url, found, captured_at, now)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        if result.nugget is not None and inp.chat_id is not None and result.status != "duplicate":
            users_repo.upsert_chat(self.system, chat_id=inp.chat_id, user_id=user.id, now=now)
            users_repo.set_chat_last_nugget(self.system, inp.chat_id, result.nugget.public_id)
        log.info(
            "captured",
            user=user.public_id,
            channel=inp.channel,
            kind=inp.kind,
            status=result.status,
            masked=found,
        )
        return result

    def edit(
        self, user: User, channel: Channel, external_id: str, new_text: str, *, via: str
    ) -> Nugget | None:
        """A user edit (§7.10): new raw event version, new nugget version, re-file later.

        The raw layer changes only through ``nugget_versions`` (invariant 4). When the edited
        message was one part of a group, only that part's text is replaced.
        """
        conn = self.memories.open(user.memory_path)
        now = self.clock.now_ms()
        original = repo.raw_event_by_external(conn, channel, external_id)
        if original is None or original["nugget_id"] is None:
            return None
        nugget = repo.get(conn, original["nugget_id"])
        if nugget is None or nugget.deleted_at is not None:
            return None
        text, found = secrets.mask(normalize_input(new_text))
        old_part = original["text"] or ""
        latest = conn.execute(
            "SELECT text FROM raw_events WHERE edit_of = ? ORDER BY id DESC LIMIT 1",
            (original["id"],),
        ).fetchone()
        if latest is not None:
            old_part = latest["text"] or ""
        if old_part and old_part in nugget.user_text and old_part != nugget.user_text:
            user_text = nugget.user_text.replace(old_part, text, 1)
        else:
            user_text = text
        if user_text == nugget.user_text:
            return nugget
        conn.execute("BEGIN IMMEDIATE")
        try:
            repo.insert_raw_event(
                conn,
                channel=channel,
                kind=original["kind"],
                text=text,
                received_at=now,
                external_id=external_id,
                edit_of=original["id"],
                nugget_id=nugget.id,
            )
            repo.add_version(conn, nugget.id, user_text, via, now)
            if found:
                conn.execute("UPDATE nuggets SET has_masked_secret = 1 WHERE id = ?", (nugget.id,))
            repo.delete_exacts(conn, nugget.id, "user_text")
            repo.insert_exacts(
                conn,
                nugget.id,
                [e.as_tuple() for e in exacts_mod.extract(user_text, user.tz)],
                "user_text",
            )
            indexing.index_instant(conn, nugget.id, self.embedder)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        self.queue.enqueue(user.id, "edit_refile", ref=nugget.public_id)
        log.info("edited", user=user.public_id, channel=channel)
        return repo.get(conn, nugget.id)

    def _open_group(self, inp: CaptureInput, user: User, conn: sqlite3.Connection) -> Nugget | None:
        """§7.1.1: same chat, previous nugget's file job still queued, merge rule holds."""
        if inp.channel != "telegram" or inp.chat_id is None:
            return None
        chat = users_repo.chat(self.system, inp.chat_id)
        if chat is None or not chat["last_nugget_pid"]:
            return None
        prev = repo.by_public_id(conn, chat["last_nugget_pid"])
        if prev is None or prev.deleted_at is not None:
            return None
        if not self.queue.file_job_open(user.id, prev.public_id):
            return None
        first = grouping.first_part(conn, prev.id)
        if first is None:
            return None
        new = grouping.Part(inp.kind, inp.text, inp.media_group_id)
        if grouping.group_count(conn, prev.id) > 1 and not (
            inp.media_group_id and inp.media_group_id == first.media_group_id
        ):
            return None  # a caption already joined: keep groups to two parts (albums excepted)
        return prev if grouping.should_merge(first, new) else None

    def _save(
        self,
        conn: sqlite3.Connection,
        inp: CaptureInput,
        user: User,
        raw_id: int,
        text: str,
        url: str | None,
        found: bool,
        captured_at: int,
        now: int,
    ) -> CaptureResult:
        canon = urls.canonicalize(url) if url else None
        group = self._open_group(inp, user, conn)  # 5
        if group is not None:
            repo.link_raw_event(conn, raw_id, group.id)
            if text:
                repo.append_user_text(conn, group.id, text, now)
            if url and canon and not group.url:
                repo.set_url(conn, group.id, url, canon, urls.source_for(url), now)
            elif inp.kind in MEDIA_SOURCE and group.source in ("typed", "forward"):
                repo.set_source(conn, group.id, MEDIA_SOURCE[inp.kind], now)
            if found:
                conn.execute("UPDATE nuggets SET has_masked_secret = 1 WHERE id = ?", (group.id,))
            nugget = repo.get(conn, group.id)
            assert nugget is not None
            self._after(conn, inp, user, nugget, text, url, "user_text", first_at=group.captured_at)
            return CaptureResult("grouped", raw_id, nugget, found, text)

        key = canon or (
            text_hash(text) if text and len(text) <= 280 and not inp.tmp_files else None
        )
        if key and not inp.force_save:
            dup = repo.find_by_dedupe(conn, key)
            if dup is not None and self._only_repeats(text, url, dup):
                repo.bump_saved_count(conn, dup.id, now)
                repo.link_raw_event(conn, raw_id, dup.id)
                return CaptureResult("duplicate", raw_id, dup, found, text)

        nugget = repo.insert(
            conn,
            public_id=ids.new("n_"),
            source=self._source(inp, url),
            user_text=text,
            captured_at=captured_at,
            captured_tz=user.tz,
            now=now,
            url=url,
            url_canonical=canon,
            original_posted_at=inp.original_posted_at,
            forward_from=inp.forward_from,
            dedupe_key=key,
            has_masked_secret=found,
            is_sample=inp.is_sample,
        )
        repo.link_raw_event(conn, raw_id, nugget.id)
        self._after(conn, inp, user, nugget, text, url, "user_text", first_at=captured_at)
        return CaptureResult("saved", raw_id, nugget, found, text)

    @staticmethod
    def _only_repeats(text: str, url: str | None, dup: Nugget) -> bool:
        """Same URL with no new words, or exactly the same short text (§7.1 rules)."""
        if url:
            rest = text
            for u in urls.find_urls(text):
                rest = rest.replace(u, "")
            return not rest.strip()
        return text_hash(text) == dup.dedupe_key

    @staticmethod
    def _source(inp: CaptureInput, url: str | None) -> str:
        if url:
            return urls.source_for(url)
        if inp.kind in MEDIA_SOURCE:
            return MEDIA_SOURCE[inp.kind]
        if inp.kind == "forward":
            return "forward"
        if inp.kind in ("location", "contact"):
            return inp.kind
        if inp.kind == "document":
            return "other"
        return "typed"

    def _after(
        self,
        conn: sqlite3.Connection,
        inp: CaptureInput,
        user: User,
        nugget: Nugget,
        text: str,
        url: str | None,
        origin: str,
        *,
        first_at: int,
    ) -> None:
        """Steps 7–9: exacts, instant index, jobs."""
        found = exacts_mod.extract(text, user.tz)
        if found:
            existing = {(r["kind"], r["normalized"]) for r in repo.exacts_for(conn, nugget.id)}
            fresh = [e.as_tuple() for e in found if (e.kind, e.normalized) not in existing]
            repo.insert_exacts(conn, nugget.id, fresh, origin)
        indexing.index_instant(conn, nugget.id, self.embedder)
        if url:
            self.queue.enqueue(user.id, "read_link", ref=nugget.public_id, payload={"url": url})
        job = MEDIA_JOB.get(inp.kind)
        if job and inp.tmp_files:
            self.queue.enqueue(user.id, job, ref=nugget.public_id, payload={"files": inp.tmp_files})
        self.queue.enqueue_file(user.id, nugget.public_id, first_at)

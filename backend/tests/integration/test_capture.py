"""T14: capture creates a raw event, a nugget, exacts and instant index rows (§7.1)."""

from datetime import timedelta

import pytest

from moira.capture.questions import is_question, strip_ask
from moira.capture.service import CaptureInput
from moira.db.repos import jobs as jobs_repo
from moira.db.repos import nuggets
from tests.conftest import World


def tg(text: str = "", kind: str = "text", msg: int = 1, **kw: object) -> CaptureInput:
    return CaptureInput(
        channel="telegram",
        kind=kind,
        text=text,
        external_id=f"1:{msg}",
        chat_id=1,
        **kw,  # type: ignore[arg-type]
    )


def test_message_creates_raw_event_nugget_exacts_and_index(world: World) -> None:
    r = world.capture.capture(tg("Josh's email is josh.r@example.com, color #38BDF8"), world.owner)
    assert r.status == "saved" and r.nugget is not None
    conn = world.memory()
    raws = nuggets.raw_events_for(conn, r.nugget.id)
    assert len(raws) == 1 and raws[0]["external_id"] == "1:1"
    assert {(e["kind"], e["normalized"]) for e in nuggets.exacts_for(conn, r.nugget.id)} >= {
        ("email", "josh.r@example.com"),
        ("hex_color", "#38BDF8"),
    }
    assert (
        conn.execute("SELECT COUNT(*) FROM nugget_fts WHERE rowid = ?", (r.nugget.id,)).fetchone()[
            0
        ]
        == 1
    )
    assert (
        conn.execute("SELECT COUNT(*) FROM nugget_tri WHERE rowid = ?", (r.nugget.id,)).fetchone()[
            0
        ]
        == 1
    )
    assert (
        conn.execute("SELECT COUNT(*) FROM vec_nuggets WHERE rowid = ?", (r.nugget.id,)).fetchone()[
            0
        ]
        == 1
    )
    file_job = jobs_repo.queued_for_ref(world.system, world.owner.id, r.nugget.public_id, "file")
    assert file_job is not None
    assert file_job.run_after == world.clock.now_ms() + 20_000


def test_bare_link_and_caption_become_one_nugget(world: World) -> None:
    a = world.capture.capture(tg("https://instagram.com/reels/C9xYz12AbCd/", msg=1), world.owner)
    world.clock.advance(timedelta(seconds=8))
    b = world.capture.capture(tg("good reel about AI editing", msg=2), world.owner)
    assert a.status == "saved" and b.status == "grouped"
    assert a.nugget is not None and b.nugget is not None and a.nugget.id == b.nugget.id
    n = b.nugget
    assert n.source == "instagram"
    assert n.url_canonical == "https://www.instagram.com/reel/C9xYz12AbCd"
    assert "good reel" in n.user_text and "instagram.com" in n.user_text
    assert len(nuggets.raw_events_for(world.memory(), n.id)) == 2


def test_caption_first_then_link_also_groups(world: World) -> None:
    a = world.capture.capture(tg("look at this", msg=1), world.owner)
    b = world.capture.capture(tg("https://youtu.be/Qm8vR2xLk4E", msg=2), world.owner)
    assert b.status == "grouped" and a.nugget is not None and b.nugget is not None
    assert b.nugget.id == a.nugget.id and b.nugget.source == "youtube"


def test_no_grouping_after_the_file_job_ran(world: World) -> None:
    a = world.capture.capture(tg("https://instagram.com/reel/AAA111/", msg=1), world.owner)
    assert a.nugget is not None
    job = jobs_repo.queued_for_ref(world.system, world.owner.id, a.nugget.public_id, "file")
    assert job is not None
    jobs_repo.finish(world.system, job.id, world.clock.now_ms())
    b = world.capture.capture(tg("nice one", msg=2), world.owner)
    assert b.status == "saved"


def test_two_ordinary_messages_do_not_group(world: World) -> None:
    world.capture.capture(tg("buy milk", msg=1), world.owner)
    b = world.capture.capture(tg("call mum", msg=2), world.owner)
    assert b.status == "saved"


def test_same_url_without_new_words_bumps_saved_count(world: World) -> None:
    a = world.capture.capture(
        CaptureInput(channel="web", text="https://github.com/o/r"), world.owner
    )
    b = world.capture.capture(
        CaptureInput(channel="web", text="https://GitHub.com/o/r/"), world.owner
    )
    assert b.status == "duplicate" and a.nugget is not None and b.nugget is not None
    n = nuggets.get(world.memory(), a.nugget.id)
    assert n is not None and n.saved_count == 2


def test_same_url_with_new_words_is_a_new_nugget(world: World) -> None:
    world.capture.capture(CaptureInput(channel="web", text="https://github.com/o/r"), world.owner)
    b = world.capture.capture(
        CaptureInput(channel="web", text="https://github.com/o/r this fixed my build"), world.owner
    )
    assert b.status == "saved"


def test_questions_are_logged_raw_and_not_saved(world: World) -> None:
    r = world.capture.capture(tg("josh's email?"), world.owner)
    assert r.status == "question" and r.nugget is None
    row = nuggets.raw_event(world.memory(), r.raw_event_id)
    assert row is not None and row["kind"] == "question"


def test_web_never_groups_or_asks(world: World) -> None:
    a = world.capture.capture(CaptureInput(channel="web", text="josh's email?"), world.owner)
    assert a.status == "saved"


def test_secrets_are_masked_before_storage(world: World) -> None:
    r = world.capture.capture(tg("wifi password: blue-otter-77"), world.owner)
    assert r.found_secrets and r.nugget is not None
    assert "blue-otter" not in r.nugget.user_text
    assert r.nugget.has_masked_secret
    raw = nuggets.raw_event(world.memory(), r.raw_event_id)
    assert raw is not None and "blue-otter" not in raw["text"]


def test_link_and_media_jobs_are_enqueued(world: World) -> None:
    r = world.capture.capture(tg("https://blog.example.com/post"), world.owner)
    assert r.nugget is not None
    assert jobs_repo.queued_for_ref(world.system, world.owner.id, r.nugget.public_id, "read_link")
    v = world.capture.capture(tg(kind="voice", msg=2, tmp_files=["/tmp/v.ogg"]), world.owner)
    assert v.nugget is not None and v.nugget.source == "voice"


@pytest.mark.parametrize(
    ("text", "has_url", "expected"),
    [
        ("josh's email?", False, True),
        ("what was that FPS fix", False, True),
        ("/ask palette from github", False, True),
        ("good reel https://instagram.com/reel/abc?", True, False),
        ("remind me: buy milk?", False, True),
        ("my favorite fruit is now banana", False, False),
        ("find a good cafe near thamel", False, True),
    ],
)
def test_question_detection_table(text: str, has_url: bool, expected: bool) -> None:
    assert is_question(text, has_url=has_url, has_media=False) is expected


def test_strip_ask() -> None:
    assert strip_ask("/ask palette from github") == "palette from github"
    assert strip_ask("/ask@moira_bot josh") == "josh"
    assert strip_ask("plain") == "plain"

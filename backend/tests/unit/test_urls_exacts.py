"""T11: URL canonicalization (≥ 30 cases incl. App. E.3), post ids, sources and exacts."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from moira.capture.exacts import extract
from moira.capture.urls import canonicalize, find_urls, is_walled, post_id, source_for

CANON = [
    # Appendix E.3
    (
        "https://www.instagram.com/reel/C9xYz12AbCd/?igsh=MWQ1ZGUx",
        "https://www.instagram.com/reel/C9xYz12AbCd",
        "C9xYz12AbCd",
    ),
    (
        "https://instagram.com/reels/C9xYz12AbCd/",
        "https://www.instagram.com/reel/C9xYz12AbCd",
        "C9xYz12AbCd",
    ),
    (
        "https://youtu.be/Qm8vR2xLk4E?si=abc123&t=42",
        "https://www.youtube.com/watch?v=Qm8vR2xLk4E&t=42",
        "Qm8vR2xLk4E",
    ),
    (
        "https://m.youtube.com/watch?v=Qm8vR2xLk4E&feature=share",
        "https://www.youtube.com/watch?v=Qm8vR2xLk4E",
        "Qm8vR2xLk4E",
    ),
    (
        "https://www.youtube.com/shorts/abcDEF12345",
        "https://www.youtube.com/shorts/abcDEF12345",
        "abcDEF12345",
    ),
    ("HTTPS://GitHub.com/Owner/Repo/", "https://github.com/Owner/Repo", None),
    (
        "https://github.com/o/r/blob/main/app.py#L10-L20",
        "https://github.com/o/r/blob/main/app.py#L10-L20",
        None,
    ),
    (
        "https://twitter.com/user/status/1234567890?s=20&t=abc",
        "https://x.com/user/status/1234567890",
        "1234567890",
    ),
    (
        "https://www.tiktok.com/@creator.demo/video/7300000000000000000?is_from_webapp=1",
        "https://www.tiktok.com/@creator.demo/video/7300000000000000000",
        "7300000000000000000",
    ),
    (
        "https://blog.example.com/post?utm_source=x&id=7&fbclid=abc",
        "https://blog.example.com/post?id=7",
        None,
    ),
    ("https://example.com:443/path/", "https://example.com/path", None),
    ("https://user:pw@example.com/", "https://example.com/", None),
    # Our own
    ("http://Example.COM:80/A/b/", "http://example.com/A/b", None),
    ("https://example.com:8443/x", "https://example.com:8443/x", None),
    ("https://example.com/?", "https://example.com/", None),
    ("example.com/docs", "https://example.com/docs", None),
    (
        "https://www.instagram.com/p/AbC_123-x/?utm_source=ig_web_copy_link",
        "https://www.instagram.com/p/AbC_123-x",
        "AbC_123-x",
    ),
    (
        "https://instagr.am/tv/XyZ987/",
        "https://www.instagram.com/tv/XyZ987",
        "XyZ987",
    ),
    (
        "https://m.instagram.com/reel/QQQ111/?hl=en",
        "https://www.instagram.com/reel/QQQ111",
        "QQQ111",
    ),
    (
        "https://mobile.twitter.com/a/status/42?lang=en",
        "https://x.com/a/status/42",
        "42",
    ),
    ("https://x.com/a/status/99?s=46", "https://x.com/a/status/99", "99"),
    (
        "https://music.youtube.com/watch?v=Zz9&list=PL1&feature=share",
        "https://www.youtube.com/watch?v=Zz9&list=PL1",
        "Zz9",
    ),
    (
        "https://www.youtube.com/watch?v=abc&si=SHARE&pp=xyz",
        "https://www.youtube.com/watch?v=abc",
        "abc",
    ),
    (
        "https://www.facebook.com/page/videos/123456/?ref=share",
        "https://www.facebook.com/page/videos/123456",
        "123456",
    ),
    (
        "https://threads.net/@me/post/C1dE2f?xmt=1",
        "https://www.threads.net/@me/post/C1dE2f",
        "C1dE2f",
    ),
    (
        "https://shop.example/item?id=5&ref=home&gclid=1&color=red",
        "https://shop.example/item?id=5&color=red",
        None,
    ),
    ("https://news.example/a?mc_cid=1&mc_eid=2&_ga=3", "https://news.example/a", None),
    ("https://example.com/a?s=1&t=2", "https://example.com/a?s=1&t=2", None),
    ("https://gist.github.com/u/abc123/", "https://gist.github.com/u/abc123", None),
    ("https://example.com/#utm_x", "https://example.com/", None),
    ("https://docs.example/page#section-2", "https://docs.example/page#section-2", None),
    ("https://vm.tiktok.com/ZMabc/", "https://vm.tiktok.com/ZMabc", None),
]


@pytest.mark.parametrize(("url", "canonical", "pid"), CANON)
def test_canonicalization_table(url: str, canonical: str, pid: str | None) -> None:
    assert canonicalize(url) == canonical
    assert post_id(url) == pid


def test_at_least_thirty_cases() -> None:
    assert len(CANON) >= 30


urls = st.builds(
    lambda host, path, q: f"https://{host}/{path}{q}",
    st.sampled_from(
        ["instagram.com", "youtu.be", "m.youtube.com", "twitter.com", "example.com", "github.com"]
    ),
    st.from_regex(r"[A-Za-z0-9_/-]{0,20}", fullmatch=True),
    st.sampled_from(["", "?utm_source=a&id=1", "?v=abc&si=x", "?s=1&t=2", "?igsh=zz"]),
)


@given(urls)
def test_canonicalization_is_idempotent(url: str) -> None:
    once = canonicalize(url)
    assert canonicalize(once) == once


@pytest.mark.parametrize(
    ("url", "source", "walled"),
    [
        ("https://www.instagram.com/reel/x", "instagram", True),
        ("https://youtu.be/x", "youtube", False),
        ("https://raw.githubusercontent.com/a/b/c", "github", False),
        ("https://twitter.com/a", "x", True),
        ("https://vm.tiktok.com/x", "tiktok", True),
        ("https://fb.watch/x", "facebook", True),
        ("https://threads.com/x", "threads", True),
        ("https://www.linkedin.com/posts/x", "web", True),
        ("https://blog.example.com", "web", False),
    ],
)
def test_source_and_walled(url: str, source: str, walled: bool) -> None:
    assert source_for(url) == source
    assert is_walled(url) is walled


def test_find_urls_strips_trailing_punctuation() -> None:
    assert find_urls("see https://a.example/x). and b.example.com/y, ok") == [
        "https://a.example/x",
        "b.example.com/y",
    ]


def kinds(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for e in extract(text):
        out.setdefault(e.kind, []).append(e.normalized)
    return out


def test_email_and_handle() -> None:
    k = kinds("mail Josh.R@Example.com or ping @Josh_R and @creator.demo.")
    assert k["email"] == ["josh.r@example.com"]
    assert k["handle"] == ["josh_r", "creator.demo"]


def test_phone_nepal_default() -> None:
    assert kinds("call me at 9841234567")["phone"] == ["+9779841234567"]


def test_phone_us_region() -> None:
    assert "+14155550123" in [
        e.normalized for e in extract("call (415) 555-0123", tz="America/Los_Angeles")
    ]


def test_hex_colors() -> None:
    assert kinds("palette #38bdf8 and #FFF")["hex_color"] == ["#38BDF8", "#FFFFFF"]
    assert "hex_color" not in kinds("that was #bad")
    assert kinds("bg #facade")["hex_color"] == ["#FACADE"]
    assert kinds("rgba(56, 189, 248, 0.5) text")["hex_color"] == ["rgba(56,189,248,0.5)"]


def test_numbers_with_units() -> None:
    k = kinds("got 144 fps after 1,250 tweaks at 3.5 GHz")
    assert "144fps" in k["number"]
    assert "1250" in k["number"]
    assert "3.5ghz" in k["number"]


def test_dates_kept_as_written() -> None:
    k = kinds("due 12 Oct, moved to 2026-10-20 then Oct 30")
    assert k["date_text"] == ["12 Oct", "2026-10-20", "Oct 30"]


def test_codes() -> None:
    k = kinds("my RTX4070 on a B550 board, run `npm ci --silent`")
    assert "rtx4070" in k["code"]
    assert "b550" in k["code"]
    assert "npm ci --silent" in k["code"]


def test_url_exact_is_canonical() -> None:
    assert kinds("good reel https://instagram.com/reels/C9xYz12AbCd/?igsh=1")["url"] == [
        "https://www.instagram.com/reel/C9xYz12AbCd"
    ]


def test_values_are_kept_character_for_character() -> None:
    values = {e.value for e in extract("Josh.R@Example.com #38bdf8")}
    assert {"Josh.R@Example.com", "#38bdf8"} <= values

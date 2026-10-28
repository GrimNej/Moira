"""T21: SSRF guard (every case of §7.3.3 blocked) and the readers (respx mocks)."""

import socket

import httpx
import pytest
import respx

from moira.errors import SsrfBlocked
from moira.readers import github, page, walled, youtube
from moira.readers.base import read_link
from moira.readers.ssrf import SafeFetcher, check_ip, check_url

PUBLIC = "93.184.216.34"


def resolver(table: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    def resolve(host: str, port: int) -> list[str]:
        if host in table:
            return table[host]
        try:
            socket.inet_aton(host)
            return [host]
        except OSError:
            pass
        raise socket.gaierror(host)

    return resolve


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "127.1.2.3",
        "10.0.0.5",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "255.255.255.255",
        "::1",
        "fe80::1",
        "fc00::1",
        "fd12:3456::1",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
        "::",
        "240.0.0.1",
    ],
)
def test_private_and_special_addresses_are_blocked(ip: str) -> None:
    with pytest.raises(SsrfBlocked):
        check_ip(ip)


def test_public_address_is_allowed() -> None:
    check_ip(PUBLIC)
    check_ip("2606:4700::6810:84e5")


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "http://user:pw@example.com/",
        "http://example.com:8080/",
        "gopher://example.com/",
        "javascript:alert(1)",
    ],
)
def test_bad_urls_are_blocked(url: str) -> None:
    with pytest.raises(SsrfBlocked):
        check_url(url, resolver({"example.com": [PUBLIC]}))


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://2130706433/",  # decimal 127.0.0.1
        "http://0x7f000001/",  # hex
        "http://0177.0.0.1/",  # octal
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "http://evil.example/",  # a domain that resolves to 127.0.0.1
        "http://mixed.example/",  # any bad address blocks
    ],
)
def test_internal_targets_are_blocked(url: str) -> None:
    table = {
        "localhost": ["127.0.0.1"],
        "2130706433": ["127.0.0.1"],
        "0x7f000001": ["127.0.0.1"],
        "0177.0.0.1": ["127.0.0.1"],
        "::1": ["::1"],
        "evil.example": ["127.0.0.1"],
        "mixed.example": [PUBLIC, "10.0.0.1"],
    }
    with pytest.raises(SsrfBlocked):
        check_url(url, resolver(table))


@respx.mock
async def test_redirect_to_metadata_service_is_blocked() -> None:
    respx.get(f"http://{PUBLIC}/go").mock(
        return_value=httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"})
    )
    fetcher = SafeFetcher(resolve=resolver({"example.com": [PUBLIC]}))
    with pytest.raises(SsrfBlocked):
        await fetcher.get("http://example.com/go")


@respx.mock
async def test_fetch_pins_the_ip_and_sends_the_host_header() -> None:
    route = respx.get(f"http://{PUBLIC}/post").mock(
        return_value=httpx.Response(
            200, html="<title>Hi</title>", headers={"content-type": "text/html"}
        )
    )
    fetcher = SafeFetcher(resolve=resolver({"blog.example.com": [PUBLIC]}))
    res = await fetcher.get("http://blog.example.com/post")
    assert res.status == 200 and "Hi" in res.text
    sent = route.calls.last.request
    assert sent.headers["host"] == "blog.example.com"
    assert "cookie" not in sent.headers
    assert sent.headers["user-agent"].startswith("MoiraBot/1.0")


@respx.mock
async def test_too_many_redirects() -> None:
    for i in range(5):
        respx.get(f"http://{PUBLIC}/r{i}").mock(
            return_value=httpx.Response(302, headers={"location": f"http://example.com/r{i + 1}"})
        )
    fetcher = SafeFetcher(resolve=resolver({"example.com": [PUBLIC]}))
    with pytest.raises(SsrfBlocked, match="redirects"):
        await fetcher.get("http://example.com/r0")


@respx.mock
async def test_non_html_is_refused() -> None:
    respx.get(f"http://{PUBLIC}/f.zip").mock(
        return_value=httpx.Response(200, content=b"PK", headers={"content-type": "application/zip"})
    )
    fetcher = SafeFetcher(resolve=resolver({"example.com": [PUBLIC]}))
    res = await fetcher.get("http://example.com/f.zip")
    assert res.status == 415


@respx.mock
async def test_body_is_capped() -> None:
    big = "<p>" + "a" * (3 * 1024 * 1024) + "</p>"
    respx.get(f"http://{PUBLIC}/big").mock(
        return_value=httpx.Response(200, text=big, headers={"content-type": "text/html"})
    )
    fetcher = SafeFetcher(resolve=resolver({"example.com": [PUBLIC]}))
    res = await fetcher.get("http://example.com/big")
    assert len(res.text) <= 2 * 1024 * 1024


@respx.mock
async def test_youtube_reader() -> None:
    respx.get("https://www.youtube.com/oembed").mock(
        return_value=httpx.Response(
            200, json={"title": "Max FPS setup guide", "author_name": "TechDemo"}
        )
    )
    r = await youtube.read("https://www.youtube.com/watch?v=Qm8vR2xLk4E")
    assert r.status == "ok" and r.method == "youtube_oembed"
    assert r.title == "Max FPS setup guide" and r.author == "TechDemo"


@respx.mock
async def test_youtube_blocked() -> None:
    respx.get("https://www.youtube.com/oembed").mock(return_value=httpx.Response(401))
    r = await youtube.read("https://www.youtube.com/watch?v=private")
    assert r.status == "blocked"


@respx.mock
async def test_github_reader() -> None:
    respx.get("https://api.github.com/repos/demo/palette").mock(
        return_value=httpx.Response(
            200,
            json={
                "description": "Tailwind palette tool",
                "topics": ["colors"],
                "language": "TS",
                "stargazers_count": 42,
                "homepage": "https://palette.example",
            },
        )
    )
    respx.get("https://api.github.com/repos/demo/palette/readme").mock(
        return_value=httpx.Response(200, text="# Palette\nPick colors like #38BDF8.")
    )
    r = await github.read("https://github.com/demo/palette")
    assert r.status == "ok" and r.method == "github_api"
    assert "Tailwind palette tool" in r.findings and "#38BDF8" in r.excerpt
    assert r.title == "demo/palette"


@respx.mock
async def test_github_rate_limited_is_blocked() -> None:
    respx.get("https://api.github.com/repos/demo/x").mock(return_value=httpx.Response(403))
    r = await github.read("https://github.com/demo/x")
    assert r.status == "blocked"


async def test_walled_platforms_make_no_request() -> None:
    with respx.mock(assert_all_called=False) as mock:
        r = await walled.read("https://www.instagram.com/reel/C9xYz12AbCd/")
        assert not mock.calls
    assert r.status == "skipped" and r.method == "web_search"
    assert "C9xYz12AbCd" in r.findings


@respx.mock
async def test_page_reader_extracts_metadata_and_text() -> None:
    html = """<html><head><title>Raw title</title>
    <meta property="og:title" content="Better title"><meta property="og:site_name" content="Blog">
    <meta name="description" content="A post about RAM.">
    <meta name="author" content="Ana"></head>
    <body><nav>menu</nav><article><p>Turn on XMP in the BIOS.</p></article><footer>f</footer></body></html>"""
    respx.get(f"http://{PUBLIC}/post").mock(
        return_value=httpx.Response(200, html=html, headers={"content-type": "text/html"})
    )
    fetcher = SafeFetcher(resolve=resolver({"blog.example.com": [PUBLIC]}))
    r = await page.read("http://blog.example.com/post", fetcher)
    assert r.status == "ok" and r.title == "Better title" and r.author == "Ana"
    assert "Turn on XMP" in r.excerpt and "menu" not in r.excerpt


@respx.mock
async def test_javascript_wall_is_blocked() -> None:
    respx.get(f"http://{PUBLIC}/app").mock(
        return_value=httpx.Response(
            200,
            html="<body>Please enable JavaScript to continue.</body>",
            headers={"content-type": "text/html"},
        )
    )
    fetcher = SafeFetcher(resolve=resolver({"app.example.com": [PUBLIC]}))
    r = await page.read("http://app.example.com/app", fetcher)
    assert r.status == "blocked"


async def test_dispatch_by_source() -> None:
    r = await read_link("https://x.com/a/status/42", fetcher=SafeFetcher(resolve=resolver({})))
    assert r.status == "skipped"

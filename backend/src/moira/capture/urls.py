"""URL finding, canonicalization, source detection and post ids (§7.3.1, §7.1.2, App. E.2–E.3)."""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

URL_RE = re.compile(r"https?://[^\s<>\"'\]]+", re.IGNORECASE)
TLDS = "com|org|net|io|dev|ai|app|co|me|gg|tv|xyz|np|in|uk|info|so|sh|to|ly|edu|gov"
BARE_RE = re.compile(rf"(?<![@\w./-])(?:[a-z0-9-]+\.)+(?:{TLDS})\b(?:/[^\s<>\"']*)?", re.IGNORECASE)
TRAILING = ".,;:!?)'\""

WALLED = {"instagram", "x", "tiktok", "facebook", "threads", "linkedin"}
TRACKING = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "igsh",
    "igshid",
    "si",
    "feature",
    "ref",
    "ref_src",
    "ref_url",
    "mc_cid",
    "mc_eid",
    "_ga",
    "yclid",
    "spm",
}
HOST_MAP = {
    "youtube.com": "www.youtube.com",
    "m.youtube.com": "www.youtube.com",
    "music.youtube.com": "www.youtube.com",
    "mobile.twitter.com": "x.com",
    "twitter.com": "x.com",
    "www.twitter.com": "x.com",
    "www.x.com": "x.com",
    "instagram.com": "www.instagram.com",
    "m.instagram.com": "www.instagram.com",
    "instagr.am": "www.instagram.com",
    "tiktok.com": "www.tiktok.com",
    "m.tiktok.com": "www.tiktok.com",
    "facebook.com": "www.facebook.com",
    "m.facebook.com": "www.facebook.com",
    "threads.com": "www.threads.net",
    "threads.net": "www.threads.net",
    "www.threads.com": "www.threads.net",
}
SOURCE_HOSTS = (
    ("instagram", ("instagram.com", "instagr.am")),
    ("youtube", ("youtube.com", "youtu.be")),
    ("github", ("github.com", "gist.github.com", "raw.githubusercontent.com")),
    ("x", ("x.com", "twitter.com")),
    ("tiktok", ("tiktok.com",)),
    ("facebook", ("facebook.com", "fb.watch")),
    ("threads", ("threads.net", "threads.com")),
    ("linkedin", ("linkedin.com",)),
)


def _strip_trailing(url: str) -> str:
    while url and url[-1] in TRAILING:
        if url[-1] == ")" and url.count("(") >= url.count(")"):
            break
        url = url[:-1]
    return url


def find_urls(text: str) -> list[str]:
    """Every URL in the text as written (scheme URLs first, then bare domains)."""
    found = [_strip_trailing(m.group(0)) for m in URL_RE.finditer(text)]
    rest = URL_RE.sub(" ", text)
    found += [_strip_trailing(m.group(0)) for m in BARE_RE.finditer(rest)]
    return [u for u in found if u]


def first_url(text: str) -> str | None:
    urls = find_urls(text)
    return urls[0] if urls else None


def platform(host: str) -> str:
    host = host.lower().removeprefix("www.")
    for name, hosts in SOURCE_HOSTS:
        if any(host == h or host.endswith("." + h) for h in hosts):
            return name
    return "web"


def source_for(url: str) -> str:
    """§7.1.2 source of a link. LinkedIn is walled but has no source value: it is ``web``."""
    p = platform(urlsplit(_with_scheme(url)).hostname or "")
    return "web" if p == "linkedin" else p


def is_walled(url: str) -> bool:
    return platform(urlsplit(_with_scheme(url)).hostname or "") in WALLED


def _with_scheme(url: str) -> str:
    return url if re.match(r"(?i)^https?://", url) else "https://" + url


def canonicalize(url: str) -> str:
    """Canonical form used for dedupe and research (idempotent)."""
    parts = urlsplit(_with_scheme(url.strip()))
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    port = parts.port
    path = parts.path or "/"
    query = parse_qsl(parts.query, keep_blank_values=True)
    fragment = parts.fragment

    if host == "youtu.be":
        video = path.strip("/").split("/")[0]
        host, path = "www.youtube.com", "/watch"
        query = [("v", video), *query]
    host = HOST_MAP.get(host, host)
    name = platform(host)

    if name == "instagram":
        path = re.sub(r"^/reels/", "/reel/", path)
    if name in WALLED:
        query = []
    else:
        query = [
            (k, v)
            for k, v in query
            if not (k.lower().startswith("utm_") or k.lower() in TRACKING)
            and not (name == "x" and k in ("s", "t"))
        ]
    if name == "youtube":
        keep = {"v", "t", "list"}
        query = [(k, v) for k, v in query if k in keep]

    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/") or "/"
    if name != "github":
        fragment = fragment if fragment and not fragment.startswith(("utm", "xtor")) else ""
    return urlunsplit((scheme, netloc, path, urlencode(query, doseq=True), fragment))


POST_ID_PATTERNS = (
    ("instagram", re.compile(r"^/(?:p|reel|tv)/([A-Za-z0-9_-]+)")),
    ("x", re.compile(r"/status/(\d+)")),
    ("tiktok", re.compile(r"/video/(\d+)")),
    ("youtube", re.compile(r"^/shorts/([A-Za-z0-9_-]+)")),
    ("facebook", re.compile(r"/(?:videos|reel|posts)/([A-Za-z0-9._-]+)")),
    ("threads", re.compile(r"/post/([A-Za-z0-9_-]+)")),
)


def post_id(url: str) -> str | None:
    """The platform post id used to verify research (§7.3.1 step 6)."""
    canonical = canonicalize(url)
    parts = urlsplit(canonical)
    name = platform(parts.hostname or "")
    if name == "youtube":
        v = dict(parse_qsl(parts.query)).get("v")
        if v:
            return v
    for pname, pattern in POST_ID_PATTERNS:
        if pname == name:
            m = pattern.search(parts.path)
            if m:
                return m.group(1)
    return None


def handle_from_url(url: str) -> str | None:
    """A creator handle visible in the URL path (TikTok ``/@name``, Instagram ``/name/``)."""
    parts = urlsplit(canonicalize(url))
    m = re.match(r"^/@([A-Za-z0-9_.]+)", parts.path)
    if m:
        return m.group(1).lower()
    return None

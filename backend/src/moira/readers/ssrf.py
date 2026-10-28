"""SSRF guard (§7.3.3): users send URLs, the server must never fetch internal addresses.

1. http/https only, ports 80/443, no userinfo.
2. Resolve the host; reject if ANY address is not globally routable (loopback, private,
   link-local, CGNAT, unique-local, multicast, reserved, unspecified, IPv4-mapped forms).
3. Connect to the validated IP (pinned) with the original Host header and TLS SNI.
4. Follow at most 3 redirects by hand, re-checking each hop.
5. Timeouts 4 s connect / 8 s read / 10 s total; stop at 2 MB; HTML or plain text only.
6. No cookies, no credentials; User-Agent ``MoiraBot/1.0``.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from moira.errors import SsrfBlocked

Resolver = Callable[[str, int], list[str]]
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
ALLOWED_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
CGNAT = ipaddress.ip_network("100.64.0.0/10")
USER_AGENT = "MoiraBot/1.0 (+https://moira.example/about)"


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def check_ip(raw: str) -> None:
    ip = ipaddress.ip_address(raw.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if (
        not ip.is_global
        or ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (isinstance(ip, ipaddress.IPv4Address) and ip in CGNAT)
    ):
        raise SsrfBlocked("address not allowed")


@dataclass(frozen=True, slots=True)
class Target:
    scheme: str
    host: str
    port: int
    url: str
    ips: list[str]


def check_url(url: str, resolve: Resolver) -> Target:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise SsrfBlocked("scheme not allowed")
    if parts.username or parts.password:
        raise SsrfBlocked("credentials in URL")
    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise SsrfBlocked("no host")
    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError:
        raise SsrfBlocked("bad port") from None
    if port not in (80, 443):
        raise SsrfBlocked("port not allowed")
    try:
        ips = resolve(host, port)
    except (OSError, UnicodeError):
        raise SsrfBlocked("host does not resolve") from None
    if not ips:
        raise SsrfBlocked("host does not resolve")
    for ip in ips:
        check_ip(ip)
    return Target(scheme, host, port, url, ips)


@dataclass(frozen=True, slots=True)
class FetchResult:
    status: int
    text: str
    final_url: str
    content_type: str


class SafeFetcher:
    def __init__(self, resolve: Resolver = system_resolver) -> None:
        self.resolve = resolve
        self.timeout = httpx.Timeout(10.0, connect=4.0, read=8.0)

    async def get(self, url: str) -> FetchResult:
        return await asyncio.wait_for(self._get(url), timeout=10.0)

    async def _get(self, url: str) -> FetchResult:
        current = url
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=False, trust_env=False
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                target = check_url(current, self.resolve)
                parts = urlsplit(current)
                ip = target.ips[0]
                ip_host = f"[{ip}]" if ":" in ip else ip
                netloc = ip_host if target.port in (80, 443) else f"{ip_host}:{target.port}"
                pinned = urlunsplit((target.scheme, netloc, parts.path or "/", parts.query, ""))
                headers = {"Host": target.host, "User-Agent": USER_AGENT, "Accept": "text/html"}
                extensions = {"sni_hostname": target.host} if target.scheme == "https" else {}
                req = client.build_request("GET", pinned, headers=headers, extensions=extensions)
                resp = await client.send(req, stream=True)
                try:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("location")
                        if not location:
                            return FetchResult(resp.status_code, "", current, "")
                        current = urljoin(current, location)
                        continue
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if resp.status_code == 200 and ctype not in ALLOWED_TYPES:
                        return FetchResult(415, "", current, ctype)
                    body = bytearray()
                    async for chunk in resp.aiter_bytes():
                        body.extend(chunk)
                        if len(body) >= MAX_BYTES:
                            break
                    text = bytes(body[:MAX_BYTES]).decode(resp.encoding or "utf-8", "replace")
                    return FetchResult(resp.status_code, text, current, ctype)
                finally:
                    await resp.aclose()
        raise SsrfBlocked("too many redirects")

"""Mask secrets before storage and before any AI call (Appendix E.1, principle 13).

Patterns run in the order S1 to S8 on NFC text. The original value is never stored or logged.
"""

import math
import re
from collections import Counter
from collections.abc import Callable
from urllib.parse import urlsplit

KEY = "[hidden key]"
CODE = "[hidden code]"
PASSWORD = "[hidden password]"  # noqa: S105  # the replacement label, not a password
PRIVATE_KEY = "[hidden private key]"

S1 = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----")
S2 = re.compile(
    "|".join(
        (
            r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}",
            r"gh[pousr]_[A-Za-z0-9]{36,}",
            r"github_pat_[A-Za-z0-9_]{60,}",
            r"xox[abprs]-[A-Za-z0-9-]{10,}",
            r"(?:AKIA|ASIA)[0-9A-Z]{16}",
            r"AIza[0-9A-Za-z_-]{35}",
            r"[rs]k_(?:live|test)_[A-Za-z0-9]{16,}",
            r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b",
            r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
            # Meta Model API key: prefix not yet verified (Appendix J12); S8 covers it meanwhile.
        )
    )
)
S3_KEYS = "token|access_token|api_key|apikey|key|secret|sig|signature|password|pwd|auth|code"
S3 = re.compile(rf"([?&](?:{S3_KEYS})=)([^&#\s]{{6,}})", re.IGNORECASE)
S4 = re.compile(r"\b(?:\d[ -]?){13,19}\b")
S5 = re.compile(r"(?i)(\b(?:cvv2|cvv|cvc|security code)\b\D{0,10})(\d{3,4})\b")
S6A = re.compile(
    r"(?i)(\b(?:otp|one[- ]time (?:code|password|passcode)|verification code|security code"
    r"|login code|auth(?:entication)? code|2fa(?: code)?|confirmation code)\b\D{0,20})(\d{4,8})\b"
)
S6B = re.compile(r"(?i)\b(\d{4,8})\b(?= is your\b[^.\n]{0,30}\b(?:code|otp|password)\b)")
S7_STRONG = re.compile(
    r"(?i)(\b(?:wi-?fi password|password|passwd|pwd|passcode|pin code)\b)"
    r"(\s*(?:is|:|=|-)?\s*)(?!\[hidden)(\S{3,64})"
)
S7_WEAK = re.compile(r"(?i)(\b(?:pass|pw|pin)\b)(\s*[:=]\s*|\s+is\s+)(?!\[hidden)(\S{3,64})")
S8 = re.compile(r"[A-Za-z0-9_\-+/=]{24,}")
URLISH = re.compile(r"https?://\S+|\b[\w.+-]+@[\w-]+\.[\w.]+")
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
HEX = re.compile(r"^[0-9a-fA-F]+$")

CARD_PREFIXES = (
    ("4",),
    tuple(str(p) for p in range(51, 56)),
    tuple(str(p) for p in range(2221, 2721)),
    ("34", "37"),
    ("6011", "65", *(str(p) for p in range(644, 650))),
    ("35",),
    ("30", "36", "38"),
    ("62",),
)


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def is_card(digits: str) -> bool:
    if not 13 <= len(digits) <= 19 or not luhn_ok(digits):
        return False
    return any(digits.startswith(p) for group in CARD_PREFIXES for p in group)


def entropy(s: str) -> float:
    counts = Counter(s)
    return -sum(c / len(s) * math.log2(c / len(s)) for c in counts.values())


def _s4(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if not is_card(digits):
            return raw
        tail = raw[len(raw.rstrip(" -")) :]
        return f"[hidden card •••• {digits[-4:]}]{tail}"

    return S4.sub(repl, text)


def _s7_strong(m: re.Match[str]) -> str:
    keyword, sep, value = m.group(1), m.group(2), m.group(3)
    has_sep = bool(sep.strip())
    # "change my password soon": without a separator, only mask values that look like secrets.
    if not has_sep and value.isalpha():
        return m.group(0)
    return f"{keyword}{sep}{PASSWORD}"


def _s8(text: str) -> str:
    protected = [(m.start(), m.end()) for m in URLISH.finditer(text)]

    def repl(m: re.Match[str]) -> str:
        token = m.group(0)
        if any(a <= m.start() < b for a, b in protected):
            return token
        if UUID.match(token) or HEX.match(token.replace("-", "")):
            return token
        if not (
            any(c.isupper() for c in token)
            and any(c.islower() for c in token)
            and any(c.isdigit() for c in token)
        ):
            return token
        if entropy(token) < 3.5:
            return token
        return KEY

    return S8.sub(repl, text)


def _s3(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        if m.group(2).startswith("[hidden"):
            return m.group(0)
        return m.group(1) + KEY

    return S3.sub(repl, text)


STEPS: tuple[Callable[[str], str], ...] = (
    lambda t: S1.sub(PRIVATE_KEY, t),
    lambda t: S2.sub(KEY, t),
    _s3,
    _s4,
    lambda t: S5.sub(lambda m: m.group(1) + CODE, t),
    lambda t: S6B.sub(CODE, S6A.sub(lambda m: m.group(1) + CODE, t)),
    lambda t: S7_WEAK.sub(
        lambda m: m.group(1) + m.group(2) + PASSWORD, S7_STRONG.sub(_s7_strong, t)
    ),
    _s8,
)


def mask(text: str) -> tuple[str, bool]:
    """Return the masked text and whether anything was masked."""
    out = text
    for step in STEPS:
        out = step(out)
    return out, out != text


def detect(text: str) -> bool:
    """True if masking would change the text."""
    return mask(text)[1]


def url_host(url: str) -> str:
    """Log helper: only the host of a URL may be logged (§13.11)."""
    return urlsplit(url).hostname or ""

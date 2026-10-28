"""Exact strings extracted by code, stored character for character (App. E.2, principle 12)."""

import re
from dataclasses import dataclass

import phonenumbers

from moira.capture.urls import canonicalize, find_urls

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
HANDLE = re.compile(r"(?<![\w@.])@([A-Za-z0-9_](?:[A-Za-z0-9_.]{0,28}[A-Za-z0-9_])?)")
HEX = re.compile(r"(?<![\w&])#([0-9A-Fa-f]{8}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")
RGB = re.compile(r"rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(?:,\s*[\d.]+\s*)?\)", re.I)
COLOR_WORDS = re.compile(r"(?i)\b(?:colou?rs?|palette|hex|bg|background|font)\b")
UNIT_NUMBER = re.compile(
    r"(?i)\b(\d+(?:\.\d+)?)\s?(ms|fps|hz|ghz|mhz|gb|mb|kb|tb|%|°c|rs|npr|usd)(?![a-z])"
)
# E.2 digit runs, plus thousands separators ("1,250") which the E.2 pattern alone misses.
NUMBER = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d{3,}(?:[.,]\d+)*\b")
MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
DATE_TEXT = re.compile(
    rf"(?i)\b(?:\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{MONTHS})[a-z]*(?:\s+\d{{4}})?"
    rf"|(?:{MONTHS})[a-z]*\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?)\b"
)
BACKTICK = re.compile(r"`([^`]{2,200})`")
MODEL = re.compile(r"\b(?=[A-Za-z-]*\d)(?=[\d-]*[A-Za-z])[A-Za-z0-9-]{3,32}\b")


@dataclass(frozen=True, slots=True)
class Exact:
    kind: str
    value: str
    normalized: str

    def as_tuple(self) -> tuple[str, str, str]:
        return self.kind, self.value, self.normalized


def region_for_tz(tz: str) -> str:
    """Phone region from the user's time zone (default Nepal)."""
    table = {
        "Asia/Kathmandu": "NP",
        "Asia/Kolkata": "IN",
        "Asia/Calcutta": "IN",
        "Europe/London": "GB",
        "Australia/Sydney": "AU",
    }
    if tz in table:
        return table[tz]
    if tz.startswith("America/"):
        return "US"
    return "NP"


def _hex6(code: str) -> str:
    code = code.upper()
    if len(code) == 3:
        code = "".join(c * 2 for c in code)
    return "#" + code


def extract(text: str, tz: str = "Asia/Kathmandu") -> list[Exact]:
    """All exact strings in ``text``, in a stable order, without duplicates."""
    out: list[Exact] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, value: str, normalized: str) -> None:
        if (kind, normalized) not in seen:
            seen.add((kind, normalized))
            out.append(Exact(kind, value, normalized))

    urls = find_urls(text)
    for url in urls:
        add("url", url, canonicalize(url))
    no_urls = text
    for url in urls:
        no_urls = no_urls.replace(url, " ")

    for m in EMAIL.finditer(no_urls):
        add("email", m.group(0), m.group(0).lower())
    no_emails = EMAIL.sub(" ", no_urls)

    for match in phonenumbers.PhoneNumberMatcher(no_emails, region_for_tz(tz)):
        add(
            "phone",
            match.raw_string,
            phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164),
        )

    for m in HANDLE.finditer(no_emails):
        add("handle", m.group(0), m.group(1).lower())

    hexes = list(HEX.finditer(no_urls))
    color_context = len(hexes) + len(RGB.findall(no_urls)) > 1 or bool(COLOR_WORDS.search(text))
    for m in hexes:
        code = m.group(1)
        letters_only = code.isalpha() and len(code) in (3, 6)
        if letters_only and not color_context:
            continue
        add("hex_color", m.group(0), _hex6(code) if len(code) != 8 else "#" + code.upper())
    for m in RGB.finditer(no_urls):
        add("hex_color", m.group(0), re.sub(r"\s+", "", m.group(0).lower()))

    for m in DATE_TEXT.finditer(no_urls):
        add("date_text", m.group(0), m.group(0))
    no_dates = DATE_TEXT.sub(" ", no_urls)

    for m in UNIT_NUMBER.finditer(no_dates):
        add("number", m.group(0), m.group(1).replace(",", "") + m.group(2).lower())
    for m in NUMBER.finditer(no_dates):
        add("number", m.group(0), re.sub(r"[.,]", "", m.group(0)))

    for m in BACKTICK.finditer(text):
        add("code", m.group(0), m.group(1).lower())
    for m in MODEL.finditer(HEX.sub(" ", no_emails.replace("@", " "))):
        token = m.group(0)
        if token.isdigit() or re.fullmatch(r"\d+(?:st|nd|rd|th|am|pm|[a-z]{1,3})", token, re.I):
            continue
        add("code", token, token.lower())
    return out

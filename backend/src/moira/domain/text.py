"""Small pure text helpers shared by capture, memory and search."""

import hashlib
import re
import unicodedata

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE = re.compile(r"\s+")
_BLANKS = re.compile(r"\n{3,}")


def normalize_input(text: str) -> str:
    """Capture step 1 (§7.1): NFC, trim, collapse 3+ blank lines."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    return _BLANKS.sub("\n\n", text.strip())


def collapse_ws(text: str) -> str:
    return _SPACE.sub(" ", text).strip()


def singular(word: str) -> str:
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def name_norm(name: str) -> str:
    """Hub name key (§6.3 ``hubs.name_norm``): lowercase, punctuation stripped, singularized."""
    words = collapse_ws(_PUNCT.sub(" ", name.lower())).split(" ")
    return " ".join(singular(w) for w in words if w)


def text_hash(text: str) -> str:
    """Dedupe key for short texts (§6.3): sha1 of the whitespace-normalized lowercase text."""
    return hashlib.sha1(collapse_ws(text.lower()).encode(), usedforsecurity=False).hexdigest()


def contains_evidence(haystack: str, quote: str) -> bool:
    """Invariant 3 (§6.4): case-insensitive substring after whitespace normalization."""
    q = collapse_ws(quote.lower())
    return bool(q) and q in collapse_ws(haystack.lower())

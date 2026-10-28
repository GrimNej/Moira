"""Question or save? Conservative on purpose (§4.2.3, App. E.4): when unsure, save."""

PREFIXES = ("find ", "show me ", "what was ", "what's my ", "who was ", "when did i ")


def is_question(text: str, *, has_url: bool, has_media: bool) -> bool:
    t = text.strip()
    if not t or has_url or has_media:
        return False
    low = t.lower().replace("’", "'")
    return low.endswith("?") or low.startswith("/ask") or low.startswith(PREFIXES)


def strip_ask(text: str) -> str:
    """``/ask`` or ``/ask@bot`` removed; the rest is the question."""
    t = text.strip()
    if t.lower().startswith("/ask"):
        t = t[4:]
        if t.startswith("@"):
            t = t.split(" ", 1)[1] if " " in t else ""
    return t.strip()

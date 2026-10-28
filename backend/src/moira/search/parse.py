"""Query parsing (§8.1), code only: terms, phrases, exacts, source, kinds, time, intent."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from moira.capture.exacts import extract
from moira.search import lexicon
from moira.search.timeexpr import TimeHint, extract_time

PHRASE = re.compile(r'"([^"]{2,})"')
WORD = re.compile(r"[\w'.@#-]+", re.UNICODE)


class ExactToken(BaseModel):
    kind: str
    value: str
    normalized: str


class Parsed(BaseModel):
    text: str
    terms: list[str]
    phrases: list[str]
    exact: list[ExactToken]
    source: str | None
    kinds: list[str]
    time: TimeHint | None
    wants_past: bool
    intent: Literal["lookup", "list", "count"]
    follow_up: Literal["none", "before_that", "after_that"]

    model_config = {"arbitrary_types_allowed": True}

    def clue_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "time_label": self.time.label if self.time else None,
            "terms": self.terms[:6],
            "intent": self.intent,
        }


def _term(w: str) -> str:
    w = w.strip(".,;:!?'\"()[]").lower()
    return w.removesuffix("'s")


def parse(text: str, now: datetime, tz: str) -> Parsed:
    question = text.strip()
    phrases = PHRASE.findall(question)
    rest = PHRASE.sub(" ", question)
    hint, rest = extract_time(rest, now, tz)
    source = lexicon.detect_source(rest)
    rest_no_source = lexicon.strip_source_words(rest)
    exact = [
        ExactToken(kind=e.kind, value=e.value, normalized=e.normalized)
        for e in extract(question, tz)
        if e.kind in ("url", "email", "phone", "handle", "hex_color", "number", "code")
    ]
    terms = []
    for w in WORD.findall(rest_no_source):
        t = _term(w)
        if len(t) < 2 or t in lexicon.STOPWORDS or (t.isdigit() and len(t) < 3):
            continue
        if t not in terms:
            terms.append(t)
    intent: Literal["lookup", "list", "count"] = "lookup"
    if lexicon.COUNT.search(question):
        intent = "count"
    elif lexicon.LIST.search(question):
        intent = "list"
    follow: Literal["none", "before_that", "after_that"] = "none"
    if lexicon.BEFORE_THAT.search(question):
        follow = "before_that"
    elif lexicon.AFTER_THAT.search(question):
        follow = "after_that"
    return Parsed(
        text=question,
        terms=terms,
        phrases=phrases,
        exact=exact,
        source=source,
        kinds=lexicon.detect_kinds(question),
        time=hint,
        wants_past=bool(lexicon.PAST.search(question)) and follow == "none",
        intent=intent,
        follow_up=follow,
    )

"""Search lexicons (§8.1): sources, kinds and stopwords. Code only, no AI."""

import re

SOURCE_WORDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:insta|instagram|ig|reels?)\b", re.I), "instagram"),
    (re.compile(r"\b(?:youtube|yt)\b", re.I), "youtube"),
    (re.compile(r"\b(?:github|repo|gh)\b", re.I), "github"),
    (re.compile(r"\b(?:tweet|twitter|x\.com)\b", re.I), "x"),
    (re.compile(r"\btiktok\b", re.I), "tiktok"),
    (re.compile(r"\bscreen ?shots?\b", re.I), "screenshot"),
    (re.compile(r"\bvoice notes?\b|\bvoice\b|\bi said\b", re.I), "voice"),
    (re.compile(r"\b(?:article|blog|site|page|website)\b", re.I), "web"),
)
KIND_WORDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:email|mail|number|phone|contact)\b", re.I), "person"),
    (re.compile(r"\b(?:todo|to-do|task|remind(?:er)?)\b", re.I), "todo"),
    (re.compile(r"\bideas?\b", re.I), "idea"),
)
PAST = re.compile(r"\b(?:used to|before|earlier|old|previous(?:ly)?|formerly|was my)\b", re.I)
LIST = re.compile(r"\b(?:all my|list|every|all the)\b", re.I)
COUNT = re.compile(r"\bhow many\b", re.I)
BEFORE_THAT = re.compile(r"\b(?:the one )?before that\b|\bprevious one\b", re.I)
AFTER_THAT = re.compile(r"\b(?:the one )?after that\b|\bnext one\b", re.I)

_STOPWORDS = """
a about above after again against all am an and any are as at be because been before
being below between both but by can could did do does doing down during each few for
from further had has have having he her here hers herself him himself his how i if in
into is it its itself just me more most my myself no nor not now of off on once only or
other our ours out over own same she should so some such than that the their theirs
them then there these they this those through to too under until up very was we were
what when where which while who whom why will with would you your yours yourself what's
whats who's i'm im it's remember saved save sent send gave give link thing things stuff
something approximately roughly like maybe find show tell one ~ please ask
"""
STOPWORDS = frozenset(_STOPWORDS.split())


def detect_source(text: str) -> str | None:
    for pattern, source in SOURCE_WORDS:
        if pattern.search(text):
            return source
    return None


def strip_source_words(text: str) -> str:
    for pattern, _ in SOURCE_WORDS:
        text = pattern.sub(" ", text)
    return text


def detect_kinds(text: str) -> list[str]:
    return [kind for pattern, kind in KIND_WORDS if pattern.search(text)]

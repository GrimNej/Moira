"""FakeLLM (§9.7): deterministic, rule-based outputs so the pipeline runs offline and in CI.

It reads the same tagged blocks the real prompts get. ENRICH picks a shelf by keyword, files
"my favorite X is Y" into a fact hub and uses ``replace`` when a change cue appears; ANSWER
cites the first candidate; PLAN detects list/count. Tests can queue exact outputs with
``FakeLLM.queue(kind, output)``.
"""

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from moira.ai.client import Effort, InputPart, ResearchRaw, Transcript
from moira.ai.prompts import Prompt
from moira.ai.schemas import (
    AnswerOutput,
    Citation,
    EnrichOutput,
    HubAction,
    NowOutput,
    PersonOut,
    PlanOutput,
    TidyOutput,
)

T = TypeVar("T", bound=BaseModel)

CHANGE_CUES = re.compile(
    r"(?i)\b(?:now|anymore|any more|no longer|switched|changed|instead|actually|these days)\b"
)
FAV = re.compile(r"(?i)\bmy (?:favou?rite) ([a-z ]+?) (?:is|are)(?: now)? (.+?)(?:\s+now)?[.!]?$")
ALSO = re.compile(r"(?i)\bi also (?:like|love) (.+?)[.!]?$")
EMAIL_OF = re.compile(r"(?i)\b([A-Z][a-z]+)(?:'s| has a)(?: new)? email (?:is )?(\S+@\S+)")
STOP = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "my",
    "i",
    "me",
    "to",
    "of",
    "and",
    "or",
    "in",
    "on",
    "at",
    "it",
    "this",
    "that",
    "for",
    "with",
    "was",
    "be",
}


def block(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>\n?(.*?)\n?</{tag}>", text, re.S)
    return m.group(1).strip() if m else ""


def plural(word: str) -> str:
    return word if word.endswith("s") else word + "s"


def parse_hubs(text: str) -> list[dict[str, Any]]:
    """``- id=h_x kind=fact name="Favorite fruits" now="..." members: n_1 "t" (current); ...``"""
    hubs = []
    for line in block(text, "candidate_hubs").splitlines():
        m = re.match(r'- id=(\S+) kind=(\S+) name="([^"]*)" now="([^"]*)"(?: members: (.*))?', line)
        if not m:
            continue
        members = re.findall(r'(n_[\w-]+) "[^"]*"(?: \((\w+)\))?', m.group(5) or "")
        hubs.append(
            {
                "id": m.group(1),
                "kind": m.group(2),
                "name": m.group(3),
                "now": m.group(4),
                "members": [(mid, role or "member") for mid, role in members],
            }
        )
    return hubs


def parse_shelves(text: str) -> dict[str, str]:
    return {
        name.strip(): hid for hid, name in re.findall(r"id=(\S+) ([^·\n]+)", block(text, "shelves"))
    }


def action(**kw: Any) -> HubAction:
    base: dict[str, Any] = {
        "hub_id": "",
        "new_hub_name": "",
        "new_hub_kind": "",
        "also_add_nugget_ids": [],
        "role": "member",
        "fact_op": "none",
        "replaces_nugget_ids": [],
        "new_now_line": "",
        "evidence": "",
        "confidence": 0.9,
    }
    base.update(kw)
    return HubAction(**base)


def fake_enrich(text: str, images: int) -> EnrichOutput:
    words = block(text, "user_words")
    found = block(text, "found_content")
    url = re.search(r'url="([^"]+)"', text)
    source = re.search(r'source="([^"]+)"', text)
    src = source.group(1) if source else "typed"
    from moira.memory.shelf import shelf_name_for

    bare = bool(url) and words.strip() in ("", url.group(1) if url else "")
    kind = "note"
    if url:
        kind = "link"
    if re.search(r"(?i)^(?:todo|remind|buy|call|book|submit|finish)\b", words):
        kind = "todo"
    if re.search(r"(?i)\bidea\b", words):
        kind = "idea"
    hubs = parse_hubs(text)
    shelves = parse_shelves(text)
    actions: list[HubAction] = []
    people: list[PersonOut] = []

    fav = FAV.search(words)
    also = ALSO.search(words)
    mail = EMAIL_OF.search(words)
    if fav:
        kind = "fact"
        thing, value = fav.group(1).strip(), fav.group(2).strip()
        name = f"Favorite {plural(thing)}"
        hub = next((h for h in hubs if h["name"].lower() == name.lower()), None)
        if hub is None:
            actions.append(
                action(
                    new_hub_name=name,
                    new_hub_kind="fact",
                    role="current",
                    fact_op="add",
                    new_now_line=f"{name}: {value}.",
                    evidence=fav.group(0).rstrip(".!"),
                )
            )
        elif CHANGE_CUES.search(words):
            current = [m for m, r in hub["members"] if r == "current"]
            actions.append(
                action(
                    hub_id=hub["id"],
                    role="current",
                    fact_op="replace",
                    replaces_nugget_ids=current,
                    new_now_line=f"{name}: {value}.",
                    evidence=fav.group(0).rstrip(".!"),
                )
            )
        else:
            prior = hub["now"].split(":", 1)[-1].strip().rstrip(".")
            line = f"{name}: {prior} and {value}." if prior else f"{name}: {value}."
            actions.append(
                action(
                    hub_id=hub["id"],
                    role="current",
                    fact_op="add",
                    new_now_line=line,
                    evidence=fav.group(0).rstrip(".!"),
                )
            )
    elif also:
        hub = next((h for h in hubs if h["kind"] == "fact"), None)
        if hub is not None:
            kind = "fact"
            prior = hub["now"].split(":", 1)[-1].strip().rstrip(".")
            value = also.group(1).strip()
            actions.append(
                action(
                    hub_id=hub["id"],
                    role="current",
                    fact_op="add",
                    new_now_line=f"{hub['name']}: {prior} and {value}.",
                    evidence=also.group(0).rstrip(".!"),
                )
            )
    elif mail:
        kind = "person"
        person = mail.group(1)
        people.append(PersonOut(name=person, person_id="", hint=""))
        hub = next((h for h in hubs if h["kind"] == "person" and h["name"] == person), None)
        op = "replace" if (hub and CHANGE_CUES.search(words)) or (hub and "new" in words) else "add"
        replaces = (
            [m for m, r in hub["members"] if r == "current"] if hub and op == "replace" else []
        )
        line = f"Email: {mail.group(2).rstrip('.')}"
        if hub is None:
            actions.append(
                action(
                    new_hub_name=person,
                    new_hub_kind="person",
                    role="current",
                    fact_op="add",
                    new_now_line=line,
                    evidence=mail.group(0),
                )
            )
        else:
            actions.append(
                action(
                    hub_id=hub["id"],
                    role="current",
                    fact_op=op,
                    replaces_nugget_ids=replaces,
                    new_now_line=line,
                    evidence=mail.group(0),
                )
            )
    else:
        topic = next(
            (
                h
                for h in hubs
                if h["kind"] == "topic"
                and any(w in words.lower() for w in h["name"].lower().split() if len(w) > 2)
            ),
            None,
        )
        if topic is not None:
            actions.append(action(hub_id=topic["id"], role="member"))
    shelf = shelf_name_for(kind, src, words + " " + found)
    if not actions and shelf in shelves:
        actions.append(action(hub_id=shelves[shelf], role="member"))

    title_src = words or found or "Saved item"
    if bare and url:
        platform = {
            "instagram": "Instagram reel",
            "youtube": "YouTube video",
            "x": "Post on X",
            "tiktok": "TikTok video",
        }.get(src, "Link")
        title = f"{platform}, saved with no note"
        topic_line = re.search(r"TOPIC: ([^·\n]+)", found)
        if topic_line:
            title = f"{platform}: {topic_line.group(1).strip()}"
    else:
        title = title_src.splitlines()[0][:80]
    content_words = [
        w
        for w in re.findall(r"[a-z0-9]+", (words + " " + found).lower())
        if w not in STOP and len(w) > 2
    ]
    tags = list(dict.fromkeys(content_words))[:5]
    items: list[str] = []
    lst = re.search(
        r"(?i)\bmy ([a-z ]+) are ([A-Z][\w]*(?:, [A-Z][\w]*)*(?:,? and [A-Z][\w]*))", words
    )
    if lst:
        items = re.split(r",\s*|\s+and\s+", lst.group(2))
    return EnrichOutput(
        title=title,
        summary=(found or words)[:200],
        kind=kind,
        tags=tags,
        search_questions=[
            f"that {' '.join(tags[:3])}".strip(),
            title.lower()[:60],
            "what did i save",
        ],
        image_text="SCREENSHOT TEXT" if images else "",
        structured_list_title=lst.group(1).strip().capitalize() if lst else "",
        structured_list_items=items,
        people=people,
        guess="",
        needs_research=bare and not found,
        hub_actions=actions,
    )


def fake_answer(text: str) -> AnswerOutput:
    cands = re.findall(
        r"^\[\d+\] id=(n_[\w-]+)[^\n]*title=\"([^\"]*)\"", block(text, "candidates"), re.M
    )
    if not cands:
        return AnswerOutput(
            answer="I couldn't find that.",
            citations=[],
            also_relevant=[],
            confidence="not_found",
            needs_more=False,
        )
    nid, title = cands[0]
    return AnswerOutput(
        answer=f"You saved it: {title}.",
        citations=[Citation(id=nid, why="best match")],
        also_relevant=[c[0] for c in cands[1:4]],
        confidence="high",
        needs_more=False,
    )


def fake_plan(text: str) -> PlanOutput:
    q = block(text, "question").lower() or text.lower()
    mode = (
        "count"
        if "how many" in q
        else "list"
        if re.search(r"\b(all my|list|every)\b", q)
        else "lookup"
    )
    words = [w for w in re.findall(r"[a-z0-9]+", q) if w not in STOP and len(w) > 2]
    time = re.search(r"(this year|last year|last month|this month|last week|\d+ \w+ ago)", q)
    return PlanOutput(
        mode=mode,
        keywords=words[:8],
        exact_phrases=[],
        sources=[],
        kinds=[],
        people=[],
        hub_names=[],
        time_text=time.group(1) if time else "",
        sort="relevance",
        include_earlier=False,
    )


class FakeLLM:
    def __init__(self) -> None:
        self.queued: dict[str, list[Any]] = defaultdict(list)
        self.calls: list[tuple[str, str]] = []
        self.research_text: str | None = None
        self.research_sources: list[dict[str, str]] = []
        self.transcripts: list[str] = []

    def queue(self, kind: str, output: Any) -> None:
        self.queued[kind].append(output)

    async def structured(
        self,
        *,
        prompt: Prompt,
        inputs: list[InputPart],
        schema: type[T],
        effort: Effort,
        max_output_tokens: int,
        timeout_s: float,
        user_id: int | None,
        kind: str,
        model: str | None = None,
    ) -> T:
        text = "\n".join(p.text for p in inputs if p.text)
        images = sum(1 for p in inputs if p.image_data_url)
        self.calls.append((kind, text))
        if self.queued[kind]:
            out = self.queued[kind].pop(0)
            if isinstance(out, Exception):
                raise out
            return schema.model_validate(out) if isinstance(out, dict) else out
        if schema is EnrichOutput:
            return fake_enrich(text, images)  # type: ignore[return-value]
        if schema is AnswerOutput:
            return fake_answer(text)  # type: ignore[return-value]
        if schema is PlanOutput:
            return fake_plan(text)  # type: ignore[return-value]
        if schema is NowOutput:
            items = re.findall(r'"([^"]+)"', block(text, "current"))
            hub = block(text, "hub") or "Now"
            return NowOutput(now_line=f"{hub}: {', '.join(items)}."[:200] if items else "")  # type: ignore[return-value]
        if schema is TidyOutput:
            return TidyOutput(merges=[], renames=[])  # type: ignore[return-value]
        raise NotImplementedError(schema.__name__)

    async def research(self, *, prompt: Prompt, text: str, user_id: int | None) -> ResearchRaw:
        self.calls.append(("research", text))
        if self.queued["research"]:
            out = self.queued["research"].pop(0)
            if isinstance(out, Exception):
                raise out
            return out  # type: ignore[no-any-return]
        if self.research_text is not None:
            return ResearchRaw(self.research_text, self.research_sources, 1)
        url = re.search(r"Post URL: (\S+)", text)
        return ResearchRaw(
            "CREATOR: @editlab.demo\nTITLE: 5 AI tools for editing\n"
            "TOPIC: five AI tools for video editing\n"
            "SUMMARY: The caption lists five AI tools that cut, caption and color-grade videos.\n"
            "MATCH: exact",
            [{"url": url.group(1) if url else "https://example.com", "title": "post"}],
            1,
        )

    async def video(self, *, prompt: Prompt, path: Path, user_id: int | None) -> str:
        self.calls.append(("video", str(path)))
        return (
            "SPEECH: here are five tools\nON_SCREEN_TEXT: 5 AI TOOLS\nCREATOR: @editlab.demo\n"
            "PLATFORM: Instagram\nTOPIC: AI tools for editing"
        )

    async def transcribe(
        self, *, wav: Path, keywords: list[str], user_id: int | None
    ) -> Transcript:
        self.calls.append(("asr", ",".join(keywords)))
        text = (
            self.transcripts.pop(0) if self.transcripts else "remember to call Josh about the logo"
        )
        return Transcript(text, 3000)

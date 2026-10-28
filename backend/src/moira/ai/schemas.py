"""Output schemas (§9.9): the JSON Schema sent to the API and the pydantic model that parses it.

The JSON schemas are written by hand, exactly as the blueprint gives them: plain object roots,
``additionalProperties: false`` everywhere, every key required, no ``null`` unions and no
recursion, so they satisfy ``strict: true`` (§9.2).
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


def _obj(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


STR: dict[str, Any] = {"type": "string"}
STRS: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
KINDS = ["link", "idea", "fact", "person", "todo", "note"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ENRICH ---------------------------------------------------------------------------


class PersonOut(Strict):
    name: str
    person_id: str
    hint: str


class HubAction(Strict):
    hub_id: str
    new_hub_name: str
    new_hub_kind: Literal["", "topic", "person", "fact"]
    also_add_nugget_ids: list[str]
    role: Literal["member", "current", "related"]
    fact_op: Literal["none", "add", "replace", "remove", "correct"]
    replaces_nugget_ids: list[str]
    new_now_line: str
    evidence: str
    confidence: float


class EnrichOutput(Strict):
    title: str
    summary: str
    kind: Literal["link", "idea", "fact", "person", "todo", "note"]
    tags: list[str]
    search_questions: list[str]
    image_text: str
    structured_list_title: str
    structured_list_items: list[str]
    people: list[PersonOut]
    guess: str
    needs_research: bool
    hub_actions: list[HubAction]


ENRICH_SCHEMA = _obj(
    [
        "title",
        "summary",
        "kind",
        "tags",
        "search_questions",
        "image_text",
        "structured_list_title",
        "structured_list_items",
        "people",
        "guess",
        "needs_research",
        "hub_actions",
    ],
    {
        "title": STR,
        "summary": STR,
        "kind": {"type": "string", "enum": KINDS},
        "tags": STRS,
        "search_questions": STRS,
        "image_text": STR,
        "structured_list_title": STR,
        "structured_list_items": STRS,
        "people": {
            "type": "array",
            "items": _obj(
                ["name", "person_id", "hint"], {"name": STR, "person_id": STR, "hint": STR}
            ),
        },
        "guess": STR,
        "needs_research": {"type": "boolean"},
        "hub_actions": {
            "type": "array",
            "items": _obj(
                [
                    "hub_id",
                    "new_hub_name",
                    "new_hub_kind",
                    "also_add_nugget_ids",
                    "role",
                    "fact_op",
                    "replaces_nugget_ids",
                    "new_now_line",
                    "evidence",
                    "confidence",
                ],
                {
                    "hub_id": STR,
                    "new_hub_name": STR,
                    "new_hub_kind": {"type": "string", "enum": ["", "topic", "person", "fact"]},
                    "also_add_nugget_ids": STRS,
                    "role": {"type": "string", "enum": ["member", "current", "related"]},
                    "fact_op": {
                        "type": "string",
                        "enum": ["none", "add", "replace", "remove", "correct"],
                    },
                    "replaces_nugget_ids": STRS,
                    "new_now_line": STR,
                    "evidence": STR,
                    "confidence": {"type": "number"},
                },
            ),
        },
    },
)

# ANSWER ---------------------------------------------------------------------------


class Citation(Strict):
    id: str
    why: str


class AnswerOutput(Strict):
    answer: str
    citations: list[Citation]
    also_relevant: list[str]
    confidence: Literal["high", "medium", "low", "not_found"]
    needs_more: bool


ANSWER_SCHEMA = _obj(
    ["answer", "citations", "also_relevant", "confidence", "needs_more"],
    {
        "answer": STR,
        "citations": {"type": "array", "items": _obj(["id", "why"], {"id": STR, "why": STR})},
        "also_relevant": STRS,
        "confidence": {"type": "string", "enum": ["high", "medium", "low", "not_found"]},
        "needs_more": {"type": "boolean"},
    },
)

# PLAN -----------------------------------------------------------------------------

PLAN_SOURCES = [
    "typed",
    "voice",
    "screenshot",
    "instagram",
    "youtube",
    "github",
    "web",
    "x",
    "tiktok",
    "facebook",
    "threads",
    "video",
    "forward",
]


class PlanOutput(Strict):
    mode: Literal["lookup", "list", "count"]
    keywords: list[str]
    exact_phrases: list[str]
    sources: list[str]
    kinds: list[str]
    people: list[str]
    hub_names: list[str]
    time_text: str
    sort: Literal["relevance", "newest", "oldest"]
    include_earlier: bool


PLAN_SCHEMA = _obj(
    [
        "mode",
        "keywords",
        "exact_phrases",
        "sources",
        "kinds",
        "people",
        "hub_names",
        "time_text",
        "sort",
        "include_earlier",
    ],
    {
        "mode": {"type": "string", "enum": ["lookup", "list", "count"]},
        "keywords": STRS,
        "exact_phrases": STRS,
        "sources": {"type": "array", "items": {"type": "string", "enum": PLAN_SOURCES}},
        "kinds": {"type": "array", "items": {"type": "string", "enum": KINDS}},
        "people": STRS,
        "hub_names": STRS,
        "time_text": STR,
        "sort": {"type": "string", "enum": ["relevance", "newest", "oldest"]},
        "include_earlier": {"type": "boolean"},
    },
)

# TIDY, NOW, DEMO_GEN ----------------------------------------------------------------


class Merge(Strict):
    keep_hub_id: str
    merge_hub_ids: list[str]
    new_name: str
    reason: str
    confidence: float


class Rename(Strict):
    hub_id: str
    new_name: str
    reason: str
    confidence: float


class TidyOutput(Strict):
    merges: list[Merge]
    renames: list[Rename]


TIDY_SCHEMA = _obj(
    ["merges", "renames"],
    {
        "merges": {
            "type": "array",
            "items": _obj(
                ["keep_hub_id", "merge_hub_ids", "new_name", "reason", "confidence"],
                {
                    "keep_hub_id": STR,
                    "merge_hub_ids": STRS,
                    "new_name": STR,
                    "reason": STR,
                    "confidence": {"type": "number"},
                },
            ),
        },
        "renames": {
            "type": "array",
            "items": _obj(
                ["hub_id", "new_name", "reason", "confidence"],
                {"hub_id": STR, "new_name": STR, "reason": STR, "confidence": {"type": "number"}},
            ),
        },
    },
)


class NowOutput(Strict):
    now_line: str


NOW_SCHEMA = _obj(["now_line"], {"now_line": STR})


class DemoItem(Strict):
    text: str
    source: Literal["typed", "voice", "screenshot", "instagram", "youtube", "github", "web"]
    day: int
    hour: int
    minute: int


class DemoGenOutput(Strict):
    items: list[DemoItem]


DEMO_GEN_SCHEMA = _obj(
    ["items"],
    {
        "items": {
            "type": "array",
            "items": _obj(
                ["text", "source", "day", "hour", "minute"],
                {
                    "text": STR,
                    "source": {
                        "type": "string",
                        "enum": [
                            "typed",
                            "voice",
                            "screenshot",
                            "instagram",
                            "youtube",
                            "github",
                            "web",
                        ],
                    },
                    "day": {"type": "integer"},
                    "hour": {"type": "integer"},
                    "minute": {"type": "integer"},
                },
            ),
        }
    },
)

SCHEMAS: dict[type[BaseModel], dict[str, Any]] = {
    EnrichOutput: ENRICH_SCHEMA,
    AnswerOutput: ANSWER_SCHEMA,
    PlanOutput: PLAN_SCHEMA,
    TidyOutput: TIDY_SCHEMA,
    NowOutput: NOW_SCHEMA,
    DemoGenOutput: DEMO_GEN_SCHEMA,
}

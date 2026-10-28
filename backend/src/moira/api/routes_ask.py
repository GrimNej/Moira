"""Ask (App. B): POST /api/ask streams SSE; feedback and save-instead on turns."""

from typing import Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from moira.api.deps import ServicesDep, UserDep, csrf, rate
from moira.api.sse import Emit, stream
from moira.capture.service import CaptureInput
from moira.db.repos import events
from moira.errors import NotFound
from moira.search.ask import AskService

router = APIRouter(prefix="/api", dependencies=[Depends(csrf)])


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    conversation_id: str | None = None


class FeedbackIn(BaseModel):
    value: Literal["found", "not_it"]


class SavedOut(BaseModel):
    nugget_id: str


@router.post("/ask", dependencies=[Depends(rate("ask", 10, 60))])
async def ask(body: AskIn, user: UserDep, services: ServicesDep) -> StreamingResponse:
    svc = AskService(services)

    async def work(emit: Emit) -> None:
        await svc.ask(user, body.question, conversation_id=body.conversation_id, emit=emit)

    return stream(work)


@router.post(
    "/turns/{turn_id}/feedback",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(rate("feedback", 30, 60))],
)
async def feedback(
    turn_id: int, body: FeedbackIn, user: UserDep, services: ServicesDep
) -> Response:
    conn = services.memories.open(user.memory_path)
    if events.turn(conn, turn_id) is None:
        raise NotFound("No such answer.")
    events.set_feedback(conn, turn_id, body.value)
    return Response(status_code=204)


@router.post("/turns/{turn_id}/save-instead", dependencies=[Depends(rate("save_instead", 10, 60))])
async def save_instead(turn_id: int, user: UserDep, services: ServicesDep) -> SavedOut:
    """A misread question becomes a memory (§4.2.3)."""
    conn = services.memories.open(user.memory_path)
    turn = events.turn(conn, turn_id)
    if turn is None:
        raise NotFound("No such answer.")
    r = services.capture.capture(
        CaptureInput(channel="web", text=turn["question"], force_save=True), user
    )
    assert r.nugget is not None
    return SavedOut(nugget_id=r.nugget.public_id)

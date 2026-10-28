"""GET /api/health (blueprint §13.11, Appendix B). The owner-only detail comes with T34."""

from fastapi import APIRouter
from pydantic import BaseModel

from moira.config import app_version

router = APIRouter()


class Health(BaseModel):
    ok: bool
    version: str


@router.get("/api/health")
async def health() -> Health:
    return Health(ok=True, version=app_version())

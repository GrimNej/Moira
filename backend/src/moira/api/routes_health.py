"""GET /api/health (blueprint §13.11, Appendix B). The owner-only detail comes with T34."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from moira.api.deps import rate
from moira.config import app_version

router = APIRouter()


class Health(BaseModel):
    ok: bool
    version: str


@router.get("/api/health", dependencies=[Depends(rate("health", 60, 60, by="ip"))])
async def health() -> Health:
    return Health(ok=True, version=app_version())

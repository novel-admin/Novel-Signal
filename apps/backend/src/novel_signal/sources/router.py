from fastapi import APIRouter
from pydantic import BaseModel

from novel_signal.sources.base import SourceType
from novel_signal.sources.registry import source_definitions

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceStatus(BaseModel):
    source_type: SourceType
    owner: str
    purpose: str
    configured: bool


@router.get("", response_model=list[SourceStatus])
def list_sources() -> list[SourceStatus]:
    return [SourceStatus(**definition.__dict__) for definition in source_definitions()]

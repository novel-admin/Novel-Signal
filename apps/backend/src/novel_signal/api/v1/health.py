from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/health")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "novel-signal-api"


@router.get("/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", response_model=HealthResponse)
def ready() -> HealthResponse:
    return HealthResponse()

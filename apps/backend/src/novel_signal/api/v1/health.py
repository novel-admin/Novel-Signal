from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/health")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "novel-signal-api"


@router.api_route("/live", methods=["GET", "HEAD"], response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse()


@router.api_route("/ready", methods=["GET", "HEAD"], response_model=HealthResponse)
def ready() -> HealthResponse:
    return HealthResponse()

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CaptureCreate(BaseModel):
    source: str = "amazon_in_public"
    page_type: Literal["search", "product"]
    url: str
    target_id: str
    content_hash: str = Field(min_length=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    status: Literal["captured", "failed", "challenged"] = "captured"
    failure_reason: str | None = None


class ObservationCreate(BaseModel):
    capture_id: str
    target_type: str
    target_id: str
    observation_type: str
    value: dict[str, Any]
    measured_status: Literal["measured", "derived"] = "measured"
    parser_version: str
    publication_status: Literal["published", "quarantined"] = "published"
    quarantine_reason: str | None = None


class CaptureRead(CaptureCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    captured_at: datetime


class ObservationRead(ObservationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    observed_at: datetime


class CollectionJobCreate(BaseModel):
    job_key: str
    page_type: Literal["search", "product"]
    target_id: str
    scheduled_at: datetime


class CollectionJobRead(CollectionJobCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    attempts: int
    failure_reason: str | None
    completed_at: datetime | None

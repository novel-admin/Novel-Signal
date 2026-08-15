from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["open", "in_progress", "done", "dismissed"]
Severity = Literal["info", "warning", "critical"]


class ChangeEventCreate(BaseModel):
    target_type: str
    target_id: str
    event_type: str
    fingerprint: str = Field(min_length=1, max_length=255)
    old_observation_type: str | None = None
    old_observation_id: str | None = None
    new_observation_type: str | None = None
    new_observation_id: str | None = None
    field_name: str | None = None
    old_value: Any = None
    new_value: Any = None
    detected_at: datetime | None = None
    severity: Severity = "info"


class ChangeEventRead(ChangeEventCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    detected_at: datetime


class ActionCreate(BaseModel):
    change_event_id: str
    title: str = Field(min_length=1, max_length=255)
    reason: str | None = None
    owner_user_id: str | None = None
    due_at: datetime | None = None


class ActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    change_event_id: str
    title: str
    reason: str | None
    owner_user_id: str | None
    due_at: datetime | None
    status: Status
    outcome_note: str | None
    created_at: datetime
    closed_at: datetime | None


class ActionTransition(BaseModel):
    status: Status
    note: str | None = None
    changed_by: str | None = None


class StatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    from_status: str | None
    to_status: str
    changed_by: str | None
    changed_at: datetime
    note: str | None


class ActionDetail(ActionRead):
    history: list[StatusHistoryRead] = []


class Page(BaseModel):
    items: list[Any]
    next_cursor: str | None = None

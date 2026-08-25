from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    change_event_id: str | None = None
    gap_id: str | None = None
    title: str = Field(min_length=1, max_length=255)
    reason: str | None = None
    owner_user_id: str | None = None
    due_at: datetime | None = None
    playbook_entry: str | None = None

    @model_validator(mode="after")
    def origin_is_present(self) -> "ActionCreate":
        if not self.change_event_id and not self.gap_id:
            raise ValueError("change_event_id or gap_id is required")
        return self


class ActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    change_event_id: str | None
    gap_id: str | None
    title: str
    reason: str | None
    owner_user_id: str | None
    due_at: datetime | None
    playbook_entry: str | None
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


class GapCreate(BaseModel):
    fingerprint: str = Field(min_length=1, max_length=255)
    dimension: str
    entity_id: str
    keyword_id: str | None = None
    benchmark_value: Any = None
    current_value: Any = None
    gap_size: float | None = None
    revenue_at_stake: float | None = Field(default=None, ge=0)
    root_cause: str | None = None
    confidence: Literal["measured", "derived", "estimated", "unknown"] = "derived"
    evidence: dict[str, Any] = Field(default_factory=dict)


class GapRead(GapCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    created_at: datetime


class ImpactCreate(BaseModel):
    days_after: Literal[7, 14, 30]
    metric: str
    baseline: float | None = None
    observed: float | None = None
    outcome: Literal["improved", "no_change", "worsened"]

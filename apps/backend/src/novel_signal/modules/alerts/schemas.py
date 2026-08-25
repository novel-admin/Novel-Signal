from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AlertStatus = Literal["open", "acknowledged", "resolved"]
AlertSeverity = Literal["info", "warning", "critical"]


class AlertRuleCreate(BaseModel):
    rule_key: str = Field(min_length=1, max_length=120)
    alert_type: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=40)
    severity: AlertSeverity
    threshold: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class AlertRuleRead(AlertRuleCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime


class AlertEventCreate(BaseModel):
    rule_id: str
    alert_type: str
    severity: AlertSeverity
    target_type: str
    target_id: str
    competitor_id: str | None = None
    keyword_id: str | None = None
    gap_id: str | None = None
    action_id: str | None = None
    title: str = Field(min_length=1, max_length=255)
    detail: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def evidence_is_present(self) -> "AlertEventCreate":
        if not self.evidence:
            raise ValueError("alerts require evidence")
        return self


class AlertEventRead(AlertEventCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: AlertStatus
    opened_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class AlertTransition(BaseModel):
    status: Literal["acknowledged", "resolved"]


class AlertPage(BaseModel):
    items: list[AlertEventRead]
    next_cursor: str | None = None


from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from novel_signal.modules.evidence import require_published_lineage


class AdObservationCreate(BaseModel):
    platform: str
    marketplace: str
    competitor_id: str | None = None
    product_id: str | None = None
    keyword_id: str | None = None
    capture_id: str | None = None
    raw_capture_id: str | None = None
    parse_run_id: str | None = None
    ad_type: str
    sponsored_position: int | None = Field(default=None, ge=1)
    captured_at: datetime
    evidence_ref: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    fingerprint: str
    publication_status: str = "published"
    quarantine_reason: str | None = None

    @model_validator(mode="after")
    def published_evidence_is_complete(self) -> "AdObservationCreate":
        require_published_lineage(
            self.publication_status,
            self.raw_capture_id,
            self.parse_run_id,
            self.quarantine_reason,
        )
        return self


class PresenceUpsert(BaseModel):
    competitor_id: str
    keyword_id: str
    day: date
    observed_slots: int = Field(ge=0)
    total_slots: int = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_ref: str | None = None


class PresenceDerive(BaseModel):
    competitor_id: str
    keyword_id: str
    day: date
    successful_capture_ids: list[str] = Field(min_length=1)


class SpendEstimateCreate(BaseModel):
    competitor_id: str
    keyword_id: str | None = None
    period_start: date
    period_end: date
    low: float = Field(ge=0)
    expected: float = Field(ge=0)
    high: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    method: str
    model_version: str
    input_coverage: float = Field(ge=0, le=1)
    backtest_ref: str | None = None


class OwnPerformanceCreate(BaseModel):
    platform: str
    account_id: str
    campaign_id: str | None = None
    period_start: date
    period_end: date
    impressions: int | None = Field(default=None, ge=0)
    clicks: int | None = Field(default=None, ge=0)
    spend: float | None = Field(default=None, ge=0)
    sales: float | None = Field(default=None, ge=0)
    conversions: int | None = Field(default=None, ge=0)
    payload: dict[str, Any] = {}
    evidence_ref: str | None = None


class AdObservationRead(AdObservationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str


class AdPresenceRead(PresenceUpsert):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ad_days: int


class SpendEstimateRead(SpendEstimateCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str


class OwnPerformanceRead(OwnPerformanceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str

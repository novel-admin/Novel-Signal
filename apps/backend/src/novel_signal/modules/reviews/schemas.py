from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from novel_signal.modules.evidence import require_published_lineage


class ReviewCreate(BaseModel):
    target_id: str = Field(min_length=1, max_length=36)
    platform: str = Field(min_length=1, max_length=40)
    source: str = Field(min_length=1, max_length=80)
    source_review_id: str | None = Field(default=None, max_length=255)
    fingerprint: str = Field(min_length=1, max_length=64)
    rating: float = Field(ge=1, le=5)
    title: str | None = Field(default=None, max_length=500)
    text: str | None = Field(default=None, max_length=10000)
    captured_at: datetime
    raw_capture_id: str | None = None
    parse_run_id: str | None = None
    publication_status: str = "published"
    quarantine_reason: str | None = None
    published_on: date | None = None
    evidence: dict[str, Any] | None = None

    @model_validator(mode="after")
    def published_evidence_is_complete(self) -> "ReviewCreate":
        require_published_lineage(
            self.publication_status,
            self.raw_capture_id,
            self.parse_run_id,
            self.quarantine_reason,
        )
        return self

    @field_validator("text", "title")
    @classmethod
    def remove_personal_data(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # Keep evidence useful while rejecting common contact and profile identifiers.
        import re

        value = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[redacted-email]", value)
        value = re.sub(r"\+?\d[\d\s().-]{8,}\d", "[redacted-phone]", value)
        return value[:10000]


class ReviewRead(ReviewCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    topic_type: str | None
    sample_size: int
    confidence: str
    created_at: datetime


class TopicSummary(BaseModel):
    topic: str
    topic_type: str
    review_count: int
    average_rating: float | None
    sample_size: int
    confidence: str


class ReviewMetrics(BaseModel):
    target_id: str
    review_count: int
    average_rating: float | None
    review_velocity_per_day: float | None
    rating_change: float | None
    period_start: date | None
    period_end: date | None
    sample_size: int
    confidence: str


class TrendRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    target_id: str
    period_start: date
    topic: str
    topic_type: str
    review_count: int
    average_rating: float | None
    sample_size: int
    confidence: str


class Page(BaseModel):
    items: list[Any]
    next_cursor: str | None = None

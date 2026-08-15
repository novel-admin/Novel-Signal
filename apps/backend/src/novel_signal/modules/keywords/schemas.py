from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from novel_signal.modules.keywords.models import (
    IntentCluster,
    KeywordSourceType,
    KeywordTrackingStatus,
)
from novel_signal.modules.universe.models import Marketplace, TrackingTier


def normalize_keyword(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def clean_required(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    if not value:
        raise ValueError("must not be blank")
    return value


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    return clean_required(value)


class SourceWrite(BaseModel):
    source_type: KeywordSourceType
    source_reference: str = Field(default="", max_length=500)
    source_metadata: dict[str, Any] | None = None

    @field_validator("source_reference")
    @classmethod
    def clean_reference(cls, value: str) -> str:
        return value.strip()


class SourceRead(SourceWrite):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    discovered_at: datetime


class KeywordFields(BaseModel):
    keyword_text: str = Field(min_length=1, max_length=500)
    marketplace: Marketplace = Marketplace.AMAZON_IN
    category: str | None = Field(default=None, max_length=255)
    tier: TrackingTier
    tracking_status: KeywordTrackingStatus = KeywordTrackingStatus.ACTIVE
    intent_cluster: IntentCluster = IntentCluster.UNCLASSIFIED
    volume_estimate: int | None = Field(default=None, ge=0)
    trend_metadata: dict[str, Any] | None = None
    seasonality_index: int | None = Field(default=None, ge=0)
    notes: str | None = None
    sources: list[SourceWrite] = Field(min_length=1)

    @field_validator("keyword_text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return clean_required(value)

    @field_validator("category", "notes")
    @classmethod
    def clean_text_optional(cls, value: str | None) -> str | None:
        return clean_optional(value)

    @field_validator("sources")
    @classmethod
    def unique_sources(cls, sources: list[SourceWrite]) -> list[SourceWrite]:
        identities = [(source.source_type, source.source_reference) for source in sources]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate source provenance")
        return sources


class KeywordCreate(KeywordFields):
    pass


class KeywordUpdate(BaseModel):
    keyword_text: str | None = Field(default=None, min_length=1, max_length=500)
    marketplace: Marketplace | None = None
    category: str | None = Field(default=None, max_length=255)
    tier: TrackingTier | None = None
    tracking_status: KeywordTrackingStatus | None = None
    intent_cluster: IntentCluster | None = None
    volume_estimate: int | None = Field(default=None, ge=0)
    trend_metadata: dict[str, Any] | None = None
    seasonality_index: int | None = Field(default=None, ge=0)
    notes: str | None = None
    sources: list[SourceWrite] | None = None

    @field_validator("keyword_text")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return clean_optional(value)

    @field_validator("category", "notes")
    @classmethod
    def clean_text_optional(cls, value: str | None) -> str | None:
        return clean_optional(value)

    @field_validator("sources")
    @classmethod
    def unique_sources(cls, sources: list[SourceWrite] | None) -> list[SourceWrite] | None:
        if sources is None:
            return None
        identities = [(source.source_type, source.source_reference) for source in sources]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate source provenance")
        return sources


class KeywordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    keyword_text: str
    normalized_text: str
    marketplace: Marketplace
    category: str | None
    tier: TrackingTier
    tracking_status: KeywordTrackingStatus
    intent_cluster: IntentCluster
    volume_estimate: int | None
    trend_metadata: dict[str, Any] | None
    seasonality_index: int | None
    notes: str | None
    sources: list[SourceRead]
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class KeywordList(BaseModel):
    items: list[KeywordRead]
    total: int
    limit: int
    offset: int


class TrackingTargetFields(BaseModel):
    keyword_id: uuid.UUID
    product_id: uuid.UUID | None = None
    competitor_product_id: uuid.UUID | None = None
    cadence_minutes: int = Field(default=240, gt=0)
    enabled: bool = True

    @model_validator(mode="after")
    def exactly_one_target(self) -> TrackingTargetFields:
        if (self.product_id is None) == (self.competitor_product_id is None):
            raise ValueError("exactly one of product_id or competitor_product_id must be set")
        return self


class TrackingTargetCreate(TrackingTargetFields):
    pass


class TrackingTargetUpdate(BaseModel):
    keyword_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    competitor_product_id: uuid.UUID | None = None
    cadence_minutes: int | None = Field(default=None, gt=0)
    enabled: bool | None = None


class TrackingTargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    keyword_id: uuid.UUID
    product_id: uuid.UUID | None
    competitor_product_id: uuid.UUID | None
    cadence_minutes: int
    enabled: bool
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class TrackingTargetList(BaseModel):
    items: list[TrackingTargetRead]
    total: int
    limit: int
    offset: int


class BulkKeywordUpdate(BaseModel):
    keyword_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    tier: TrackingTier | None = None
    tracking_status: KeywordTrackingStatus | None = None

    @model_validator(mode="after")
    def has_change(self) -> BulkKeywordUpdate:
        if self.tier is None and self.tracking_status is None:
            raise ValueError("tier or tracking_status is required")
        if len(self.keyword_ids) != len(set(self.keyword_ids)):
            raise ValueError("keyword_ids must be unique")
        return self


class BulkResult(BaseModel):
    updated: int


class CsvImportRequest(BaseModel):
    csv_text: str = Field(min_length=1)


class CsvRowError(BaseModel):
    row: int
    field: str
    message: str


class CsvValidationResult(BaseModel):
    valid: bool
    total_rows: int
    valid_rows: int
    invalid_rows: int
    errors: list[CsvRowError]


class CsvImportResult(BaseModel):
    imported_rows: int
    entity: str

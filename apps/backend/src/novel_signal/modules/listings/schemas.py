from __future__ import annotations

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from novel_signal.modules.listings.models import ListingChangeType
from novel_signal.modules.universe.models import Marketplace


class Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SnapshotIn(BaseModel):
    marketplace: Marketplace = Marketplace.AMAZON_IN
    marketplace_product_id: str = Field(min_length=1, max_length=255)
    captured_at: datetime
    geo_code: str | None = None
    device_profile: str | None = None
    source_job_id: uuid.UUID | None = None
    parser_version: str | None = None
    ingestion_key: str | None = Field(default=None, min_length=1)
    source_url: str | None = None
    title: str | None = None
    brand: str | None = None
    category_path: str | None = None
    description: str | None = None
    bullets: list[str] = Field(default_factory=list)
    key_features: list[str] = Field(default_factory=list)
    a_plus_present: bool = False
    a_plus_sections: list[object] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)
    image_hashes: list[str] = Field(default_factory=list)
    image_count: int | None = Field(default=None, ge=0)
    video_present: bool = False
    video_count: int | None = Field(default=None, ge=0)
    variation_count: int | None = Field(default=None, ge=0)
    variation_metadata: dict[str, object] | None = None
    storefront_text: str | None = None
    content_metadata: dict[str, object] | None = None

    @field_validator("marketplace_product_id")
    @classmethod
    def identity(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("marketplace_product_id must not be blank")
        return v.strip()

    @model_validator(mode="after")
    def counts(self) -> Self:
        if self.image_count is not None and self.image_count != len(
            set(self.image_hashes or self.image_urls)
        ):
            raise ValueError("image_count must match normalized images")
        if self.video_count is not None and self.video_present != (self.video_count > 0):
            raise ValueError("video_present must match video_count")
        return self


class SnapshotRead(Read):
    id: uuid.UUID
    marketplace: Marketplace
    marketplace_product_id: str
    product_id: uuid.UUID | None
    competitor_product_id: uuid.UUID | None
    captured_at: datetime
    geo_code: str | None
    device_profile: str | None
    source_job_id: uuid.UUID | None
    parser_version: str | None
    ingestion_key: str | None
    source_url: str | None
    title: str | None
    brand: str | None
    category_path: str | None
    description: str | None
    bullets: list[str]
    key_features: list[str]
    a_plus_present: bool
    a_plus_sections: list[object]
    image_urls: list[str]
    image_hashes: list[str]
    image_count: int
    video_present: bool
    video_count: int
    variation_count: int | None
    variation_metadata: dict[str, object] | None
    storefront_text: str | None
    content_metadata: dict[str, object] | None
    completeness_score: int
    completeness_breakdown: dict[str, int]
    created_at: datetime
    updated_at: datetime


class SnapshotList(BaseModel):
    items: list[SnapshotRead]
    total: int
    limit: int
    offset: int


class HistoryRow(BaseModel):
    id: uuid.UUID
    captured_at: datetime
    title: str | None
    bullet_count: int
    image_count: int
    a_plus_present: bool
    video_present: bool
    variation_count: int | None
    completeness_score: int


class HistoryList(BaseModel):
    items: list[HistoryRow]
    total: int
    limit: int
    offset: int


class ChangeRead(Read):
    id: uuid.UUID
    snapshot_id: uuid.UUID
    previous_snapshot_id: uuid.UUID | None
    marketplace_product_id: str
    product_id: uuid.UUID | None
    competitor_product_id: uuid.UUID | None
    field_name: str
    change_type: ListingChangeType
    old_value: object | None
    new_value: object | None
    observed_at: datetime


class ChangeList(BaseModel):
    items: list[ChangeRead]
    total: int
    limit: int
    offset: int


class Completeness(BaseModel):
    score: int
    breakdown: dict[str, int]
    achieved_components: list[str]
    missing_components: list[str]


class Stats(BaseModel):
    title_length: int
    bullet_count: int
    description_length: int
    image_count: int
    a_plus_present: bool
    video_present: bool
    variation_count: int
    completeness_score: int


class Comparison(BaseModel):
    owned: Stats
    competitor: Stats
    deltas: dict[str, int | bool]
    gaps: list[str]

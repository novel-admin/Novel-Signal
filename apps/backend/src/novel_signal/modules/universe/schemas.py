from __future__ import annotations

import re
import uuid
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from novel_signal.modules.universe.models import (
    BattleCardStatus,
    Marketplace,
    PositioningTier,
    TrackingTier,
)

AMAZON_ASIN_PATTERN = re.compile(r"^[A-Z0-9]{10}$")


def validate_optional_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("must be a valid http or https URL")
    return normalized


def validate_marketplace_product_id(
    marketplace: Marketplace, marketplace_product_id: str | None
) -> None:
    if marketplace_product_id is None:
        return
    if marketplace is Marketplace.AMAZON_IN and not AMAZON_ASIN_PATTERN.fullmatch(
        marketplace_product_id
    ):
        raise ValueError("Amazon.in marketplace product ID must be a 10-character ASIN")


def strip_required(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("must not be blank")
    return normalized


def strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    return strip_required(value)


def normalize_identity(value: str | None) -> str | None:
    normalized = strip_optional(value)
    return normalized.upper() if normalized is not None else None


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TimestampedRead(ReadModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class CompetitorFields(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_company: str | None = Field(default=None, max_length=255)
    amazon_store_url: str | None = Field(default=None, max_length=2048)
    amazon_seller_id: str | None = Field(default=None, max_length=255)
    category_presence: str | None = None
    positioning_tier: PositioningTier = PositioningTier.UNKNOWN
    threat_rating: int | None = Field(default=None, ge=1, le=5)
    analyst_owner: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    @field_validator(
        "name",
        "parent_company",
        "amazon_seller_id",
        "category_presence",
        "analyst_owner",
        "notes",
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("amazon_store_url")
    @classmethod
    def valid_store_url(cls, value: str | None) -> str | None:
        return validate_optional_url(value)


class CompetitorCreate(CompetitorFields):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Acme Baby Care",
                "parent_company": "Acme Consumer Products",
                "amazon_store_url": "https://www.amazon.in/stores/acme",
                "amazon_seller_id": "A1EXAMPLESELLER",
                "category_presence": "Baby Care",
                "positioning_tier": "mid",
                "threat_rating": 4,
                "analyst_owner": "Analyst One",
            }
        }
    )


class CompetitorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_company: str | None = Field(default=None, max_length=255)
    amazon_store_url: str | None = Field(default=None, max_length=2048)
    amazon_seller_id: str | None = Field(default=None, max_length=255)
    category_presence: str | None = None
    positioning_tier: PositioningTier | None = None
    threat_rating: int | None = Field(default=None, ge=1, le=5)
    analyst_owner: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("amazon_store_url")
    @classmethod
    def valid_store_url(cls, value: str | None) -> str | None:
        return validate_optional_url(value)


class CompetitorRead(CompetitorFields, TimestampedRead):
    pass


class ProductFields(BaseModel):
    internal_sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=500)
    brand: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=255)
    marketplace: Marketplace = Marketplace.AMAZON_IN
    marketplace_product_id: str | None = Field(default=None, max_length=255)
    product_url: str | None = Field(default=None, max_length=2048)
    pack_quantity: int | None = Field(default=None, gt=0)
    pack_unit: str | None = Field(default=None, max_length=50)
    tracking_tier: TrackingTier

    @field_validator(
        "internal_sku", "name", "brand", "category", "marketplace_product_id", "pack_unit"
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("marketplace_product_id")
    @classmethod
    def uppercase_identity(cls, value: str | None) -> str | None:
        normalized = normalize_identity(value)
        if normalized is not None and not AMAZON_ASIN_PATTERN.fullmatch(normalized):
            raise ValueError("Amazon.in ASIN must be exactly 10 alphanumeric characters")
        return normalized

    @field_validator("product_url")
    @classmethod
    def valid_product_url(cls, value: str | None) -> str | None:
        return validate_optional_url(value)

    @model_validator(mode="after")
    def valid_identity(self) -> ProductFields:
        validate_marketplace_product_id(self.marketplace, self.marketplace_product_id)
        return self


class ProductCreate(ProductFields):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "internal_sku": "NOV-WIPES-80X4",
                "name": "Baby Wipes 80 x 4",
                "brand": "NOVEL",
                "category": "Baby Wipes",
                "marketplace": "amazon_in",
                "marketplace_product_id": "B09GP975ZQ",
                "product_url": "https://www.amazon.in/dp/B09GP975ZQ",
                "pack_quantity": 4,
                "pack_unit": "packs",
                "tracking_tier": "T1",
            }
        }
    )


class ProductUpdate(BaseModel):
    internal_sku: str | None = Field(default=None, min_length=1, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=500)
    brand: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=255)
    marketplace: Marketplace | None = None
    marketplace_product_id: str | None = Field(default=None, max_length=255)
    product_url: str | None = Field(default=None, max_length=2048)
    pack_quantity: int | None = Field(default=None, gt=0)
    pack_unit: str | None = Field(default=None, max_length=50)
    tracking_tier: TrackingTier | None = None

    @field_validator("product_url")
    @classmethod
    def valid_product_url(cls, value: str | None) -> str | None:
        return validate_optional_url(value)

    @field_validator("internal_sku", "name", "brand", "category", "pack_unit")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return strip_optional(value)

    @field_validator("marketplace_product_id")
    @classmethod
    def uppercase_identity(cls, value: str | None) -> str | None:
        normalized = normalize_identity(value)
        if normalized is not None and not AMAZON_ASIN_PATTERN.fullmatch(normalized):
            raise ValueError("Amazon.in ASIN must be exactly 10 alphanumeric characters")
        return normalized


class ProductRead(ProductFields, TimestampedRead):
    pass


class CompetitorProductFields(BaseModel):
    competitor_id: uuid.UUID
    name: str = Field(min_length=1, max_length=500)
    brand: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=255)
    marketplace: Marketplace = Marketplace.AMAZON_IN
    marketplace_product_id: str | None = Field(default=None, max_length=255)
    product_url: str | None = Field(default=None, max_length=2048)
    pack_quantity: int | None = Field(default=None, gt=0)
    pack_unit: str | None = Field(default=None, max_length=50)
    tracking_tier: TrackingTier

    @field_validator("name", "brand", "category", "marketplace_product_id", "pack_unit")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("marketplace_product_id")
    @classmethod
    def uppercase_identity(cls, value: str | None) -> str | None:
        normalized = normalize_identity(value)
        if normalized is not None and not AMAZON_ASIN_PATTERN.fullmatch(normalized):
            raise ValueError("Amazon.in ASIN must be exactly 10 alphanumeric characters")
        return normalized

    @field_validator("product_url")
    @classmethod
    def valid_product_url(cls, value: str | None) -> str | None:
        return validate_optional_url(value)

    @model_validator(mode="after")
    def valid_identity(self) -> CompetitorProductFields:
        validate_marketplace_product_id(self.marketplace, self.marketplace_product_id)
        return self


class CompetitorProductCreate(CompetitorProductFields):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "competitor_id": "11111111-1111-4111-8111-111111111111",
                "name": "Acme Baby Wipes 80 x 4",
                "brand": "Acme",
                "category": "Baby Wipes",
                "marketplace": "amazon_in",
                "marketplace_product_id": "B0EXAMPLE1",
                "product_url": "https://www.amazon.in/dp/B0EXAMPLE1",
                "pack_quantity": 4,
                "pack_unit": "packs",
                "tracking_tier": "T1",
            }
        }
    )


class CompetitorProductUpdate(BaseModel):
    competitor_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=500)
    brand: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=255)
    marketplace: Marketplace | None = None
    marketplace_product_id: str | None = Field(default=None, max_length=255)
    product_url: str | None = Field(default=None, max_length=2048)
    pack_quantity: int | None = Field(default=None, gt=0)
    pack_unit: str | None = Field(default=None, max_length=50)
    tracking_tier: TrackingTier | None = None

    @field_validator("product_url")
    @classmethod
    def valid_product_url(cls, value: str | None) -> str | None:
        return validate_optional_url(value)

    @field_validator("name", "brand", "category", "pack_unit")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return strip_optional(value)

    @field_validator("marketplace_product_id")
    @classmethod
    def uppercase_identity(cls, value: str | None) -> str | None:
        normalized = normalize_identity(value)
        if normalized is not None and not AMAZON_ASIN_PATTERN.fullmatch(normalized):
            raise ValueError("Amazon.in ASIN must be exactly 10 alphanumeric characters")
        return normalized


class CompetitorProductRead(CompetitorProductFields, TimestampedRead):
    pass


class BattleCardItemFields(BaseModel):
    competitor_product_id: uuid.UUID
    priority_order: int | None = Field(default=None, ge=0)
    same_pack_basis: bool = False
    same_price_band: bool = False
    same_category: bool = False
    same_use_case: bool = False
    notes: str | None = None


class BattleCardItemWrite(BattleCardItemFields):
    pass


class BattleCardItemCreate(BattleCardItemFields):
    battle_card_id: uuid.UUID
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "battle_card_id": "22222222-2222-4222-8222-222222222222",
                "competitor_product_id": "33333333-3333-4333-8333-333333333333",
                "priority_order": 0,
                "same_pack_basis": True,
                "same_category": True,
                "same_price_band": False,
                "same_use_case": True,
                "notes": "Direct pack-size comparison",
            }
        }
    )


class BattleCardItemUpdate(BaseModel):
    battle_card_id: uuid.UUID | None = None
    competitor_product_id: uuid.UUID | None = None
    priority_order: int | None = Field(default=None, ge=0)
    same_pack_basis: bool | None = None
    same_price_band: bool | None = None
    same_category: bool | None = None
    same_use_case: bool | None = None
    notes: str | None = None


class BattleCardItemRead(BattleCardItemFields, TimestampedRead):
    battle_card_id: uuid.UUID
    competitor_product: CompetitorProductRead


class BattleCardFields(BaseModel):
    product_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    status: BattleCardStatus = BattleCardStatus.DRAFT
    comparison_notes: str | None = None

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class BattleCardCreate(BattleCardFields):
    items: list[BattleCardItemWrite] = Field(default_factory=list)

    @field_validator("items")
    @classmethod
    def unique_items(cls, items: list[BattleCardItemWrite]) -> list[BattleCardItemWrite]:
        product_ids = [item.competitor_product_id for item in items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("a competitor product may appear only once in a battle card")
        return items

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "product_id": "44444444-4444-4444-8444-444444444444",
                "name": "Baby wipes direct comparison",
                "status": "draft",
                "comparison_notes": "Week 1 comparison configuration",
                "items": [],
            }
        }
    )


class BattleCardUpdate(BaseModel):
    product_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: BattleCardStatus | None = None
    comparison_notes: str | None = None
    items: list[BattleCardItemWrite] | None = None

    @field_validator("items")
    @classmethod
    def unique_items(
        cls, items: list[BattleCardItemWrite] | None
    ) -> list[BattleCardItemWrite] | None:
        if items is None:
            return None
        product_ids = [item.competitor_product_id for item in items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("a competitor product may appear only once in a battle card")
        return items

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Updated comparison",
                "status": "approved",
                "comparison_notes": "Approved configuration",
            }
        }
    )


class BattleCardRead(BattleCardFields, TimestampedRead):
    product: ProductRead
    items: list[BattleCardItemRead]


class CompetitorList(ReadModel):
    items: list[CompetitorRead]
    total: int
    limit: int
    offset: int


class ProductList(ReadModel):
    items: list[ProductRead]
    total: int
    limit: int
    offset: int


class CompetitorProductList(ReadModel):
    items: list[CompetitorProductRead]
    total: int
    limit: int
    offset: int


class BattleCardList(ReadModel):
    items: list[BattleCardRead]
    total: int
    limit: int
    offset: int


class BattleCardItemList(ReadModel):
    items: list[BattleCardItemRead]
    total: int
    limit: int
    offset: int


class CsvImportRequest(BaseModel):
    csv_text: str = Field(min_length=1, description="UTF-8 CSV content including header row")


class CsvRowError(BaseModel):
    row: int
    field: str
    code: str
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

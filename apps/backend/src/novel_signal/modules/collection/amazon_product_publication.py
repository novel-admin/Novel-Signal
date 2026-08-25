"""Publish one validated Amazon product record into S5 and S6 with shared lineage."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from novel_signal.db import SessionLocal
from novel_signal.modules.collection.models import ParserVersion, RawEvidence
from novel_signal.modules.collection.pipeline import PublishContext
from novel_signal.modules.listings.models import ListingSnapshot
from novel_signal.modules.listings.repository import ListingRepository
from novel_signal.modules.listings.schemas import SnapshotIn
from novel_signal.modules.listings.service import ListingService
from novel_signal.modules.price_monitoring.models import PriceObservation
from novel_signal.modules.price_monitoring.repository import PriceRepository
from novel_signal.modules.price_monitoring.schemas import PriceObservationIn
from novel_signal.modules.price_monitoring.service import PriceService
from novel_signal.modules.universe.models import Marketplace

_ASIN = re.compile(r"^[A-Z0-9]{10}$")


@dataclass(frozen=True)
class AmazonProductPublicationConfig:
    marketplace_product_id: str
    geo_code: str | None
    device_profile: str | None
    product_id: UUID | None = None
    competitor_product_id: UUID | None = None
    profile_id: str | None = None
    pincode: str | None = None
    location_label: str | None = None
    marketplace: Marketplace = Marketplace.AMAZON_IN

    def __post_init__(self) -> None:
        if self.product_id is not None and self.competitor_product_id is not None:
            raise ValueError("Amazon product publication cannot target both product identities")
        normalized = self.marketplace_product_id.strip().upper()
        if not _ASIN.fullmatch(normalized):
            raise ValueError("Amazon product publication requires a valid ASIN")
        object.__setattr__(self, "marketplace_product_id", normalized)


class AmazonProductPublisher:
    """Use existing S5/S6 services without duplicating their business logic."""

    def __init__(
        self,
        *,
        config: AmazonProductPublicationConfig,
        session_factory: sessionmaker[Session] = SessionLocal,
    ) -> None:
        self.config = config
        self.session_factory = session_factory

    def publish(
        self, context: PublishContext, records: tuple[dict[str, Any], ...]
    ) -> dict[str, Any]:
        if len(records) != 1:
            raise ValueError("Amazon product publication requires exactly one record")
        record = records[0]
        identity = _record_asin(record)
        if identity != self.config.marketplace_product_id:
            raise ValueError("Amazon product publication identity does not match configured ASIN")

        with self.session_factory() as session:
            raw, parser = _lineage(session, context)
            owned, competitor = ListingRepository(session).mappings(
                self.config.marketplace, self.config.marketplace_product_id
            )
            _validate_context(self.config, owned, competitor)
            metadata = _lineage_metadata(context, self.config, raw)
            source_url = _source_url(raw)
            listing_key = _key("listing", context, self.config)
            price_key = _key("price", context, self.config)

            listing, listing_status = self._listing(
                session, record, context, parser, metadata, source_url, listing_key
            )
            price, price_status = self._price(
                session, record, context, parser, metadata, source_url, price_key
            )
            _validate_context(self.config, listing.product_id, listing.competitor_product_id)
            _validate_context(self.config, price.product_id, price.competitor_product_id)
            return {
                "listing_snapshot_id": str(listing.id),
                "price_observation_id": str(price.id),
                "listing_ingestion_key": listing_key,
                "price_ingestion_key": price_key,
                "listing_publication": listing_status,
                "price_publication": price_status,
                "marketplace_product_id": self.config.marketplace_product_id,
                "published_records": 1,
            }

    def _listing(
        self,
        session: Session,
        record: dict[str, Any],
        context: PublishContext,
        parser: ParserVersion,
        metadata: dict[str, object],
        source_url: str | None,
        key: str,
    ) -> tuple[ListingSnapshot, str]:
        repo = ListingRepository(session)
        payload = SnapshotIn(
            marketplace=self.config.marketplace,
            marketplace_product_id=self.config.marketplace_product_id,
            captured_at=context.captured_at,
            geo_code=self.config.geo_code,
            device_profile=self.config.device_profile,
            source_job_id=context.job_id,
            parser_version=parser.version,
            ingestion_key=key,
            source_url=source_url,
            title=record.get("title"),
            brand=record.get("brand"),
            category_path=record.get("category_path"),
            description=record.get("description"),
            bullets=record.get("bullets", []),
            key_features=record.get("key_features", []),
            a_plus_present=record.get("a_plus_present", False),
            a_plus_sections=record.get("a_plus_sections", []),
            image_urls=record.get("image_urls", []),
            image_hashes=record.get("image_hashes", []),
            image_count=record.get("image_count"),
            video_present=record.get("video_present", False),
            video_count=record.get("video_count"),
            variation_count=record.get("variation_count"),
            variation_metadata=record.get("variation_metadata"),
            storefront_text=record.get("storefront_text"),
            content_metadata=_merge_metadata(record.get("content_metadata"), metadata),
        )
        existing = repo.by_key(key)
        if existing is not None:
            _verify_listing(existing, payload)
            return existing, "existing"
        return ListingService(session).ingest(payload), "created"

    def _price(
        self,
        session: Session,
        record: dict[str, Any],
        context: PublishContext,
        parser: ParserVersion,
        metadata: dict[str, object],
        source_url: str | None,
        key: str,
    ) -> tuple[PriceObservation, str]:
        repo = PriceRepository(session)
        payload = PriceObservationIn(
            marketplace=self.config.marketplace,
            marketplace_product_id=self.config.marketplace_product_id,
            observed_at=context.captured_at,
            geo_code=self.config.geo_code,
            device_profile=self.config.device_profile,
            currency="INR",
            availability_status=record.get("availability_status", "unknown"),
            primary_price=record.get("primary_price"),
            mrp=record.get("mrp"),
            discount_percent=record.get("discount_percent"),
            coupon_text=record.get("coupon_text"),
            coupon_value=record.get("coupon_value"),
            coupon_type=record.get("coupon_type"),
            shipping_amount=record.get("shipping_amount"),
            effective_price=record.get("effective_price"),
            primary_seller_name=record.get("primary_seller_name"),
            primary_seller_id=record.get("primary_seller_id"),
            is_featured_offer=record.get("is_featured_offer"),
            seller_count=record.get("seller_count"),
            offers=record.get("offers", []),
            source_job_id=context.job_id,
            parser_version=parser.version,
            source_url=source_url,
            ingestion_key=key,
            provider="amazon_public_page",
            source_metadata=metadata,
        )
        existing = repo.by_key(key)
        if existing is not None:
            _verify_price(existing, payload)
            return existing, "existing"
        return PriceService(session).ingest(payload), "created"


def _record_asin(record: dict[str, Any]) -> str:
    value = record.get("marketplace_product_id")
    if not isinstance(value, str):
        raise ValueError("Amazon product publication record identity is invalid")
    normalized = value.strip().upper()
    if not _ASIN.fullmatch(normalized):
        raise ValueError("Amazon product publication record identity is invalid")
    return normalized


def _lineage(session: Session, context: PublishContext) -> tuple[RawEvidence, ParserVersion]:
    raw = session.get(RawEvidence, context.raw_evidence_id)
    parser = session.get(ParserVersion, context.parser_version_id)
    if (
        raw is None
        or parser is None
        or raw.job_id != context.job_id
        or raw.attempt_id != context.attempt_id
        or context.platform != "amazon_in"
        or context.page_type != "product_detail"
        or parser.platform != context.platform
        or parser.page_type != context.page_type
    ):
        raise ValueError("Amazon product publication lineage is unavailable")
    return raw, parser


def _lineage_metadata(
    context: PublishContext, config: AmazonProductPublicationConfig, raw: RawEvidence
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "raw_evidence_id": str(context.raw_evidence_id),
        "parser_version_id": str(context.parser_version_id),
        "platform": context.platform,
        "page_type": context.page_type,
        "source_job_id": str(context.job_id),
        "marketplace_product_id": config.marketplace_product_id,
    }
    for field, value in (
        ("requested_url", _safe_url((raw.capture_metadata or {}).get("requested_url"))),
        ("final_url", _safe_url(raw.final_url)),
        ("profile_id", config.profile_id),
        ("pincode", config.pincode),
        ("location_label", config.location_label),
    ):
        if isinstance(value, str) and value:
            metadata[field] = value
    return metadata


def _source_url(raw: RawEvidence) -> str | None:
    return _safe_url(raw.final_url) or _safe_url((raw.capture_metadata or {}).get("requested_url"))


def _safe_url(value: object) -> str | None:
    """Retain a source locator without query parameters that could contain secrets."""
    if not isinstance(value, str) or not value:
        return None
    parsed = urlsplit(value)
    host = parsed.hostname.casefold() if parsed.hostname else ""
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or (host != "amazon.in" and not host.endswith(".amazon.in"))
    ):
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _merge_metadata(parser_metadata: object, lineage: dict[str, object]) -> dict[str, object]:
    base = dict(parser_metadata) if isinstance(parser_metadata, dict) else {}
    return {**base, **lineage}


def _key(sink: str, context: PublishContext, config: AmazonProductPublicationConfig) -> str:
    payload = {
        "sink": sink,
        "raw_evidence_id": str(context.raw_evidence_id),
        "parser_version_id": str(context.parser_version_id),
        "marketplace_product_id": config.marketplace_product_id,
        "page_type": context.page_type,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"amazon-product-{sink}:{digest}"


def _conflict() -> None:
    raise ValueError("Amazon product publication conflicts with existing ingestion identity")


def _verify_listing(existing: ListingSnapshot, expected: SnapshotIn) -> None:
    fields = (
        ("marketplace", expected.marketplace),
        ("marketplace_product_id", expected.marketplace_product_id),
        ("captured_at", expected.captured_at),
        ("geo_code", expected.geo_code),
        ("device_profile", expected.device_profile),
        ("source_job_id", expected.source_job_id),
        ("parser_version", expected.parser_version),
        ("source_url", expected.source_url),
        ("title", expected.title),
        ("brand", expected.brand),
        ("category_path", expected.category_path),
        ("description", expected.description),
        ("bullets", expected.bullets),
        ("key_features", expected.key_features),
        ("a_plus_present", expected.a_plus_present),
        ("a_plus_sections", expected.a_plus_sections),
        ("image_urls", expected.image_urls),
        ("image_hashes", expected.image_hashes),
        ("image_count", expected.image_count),
        ("video_present", expected.video_present),
        ("video_count", expected.video_count),
        ("variation_count", expected.variation_count),
        ("variation_metadata", expected.variation_metadata),
        ("storefront_text", expected.storefront_text),
        ("content_metadata", expected.content_metadata),
    )
    if any(not _equal(getattr(existing, field), value) for field, value in fields):
        _conflict()


def _verify_price(existing: PriceObservation, expected: PriceObservationIn) -> None:
    fields = (
        ("marketplace", expected.marketplace),
        ("marketplace_product_id", expected.marketplace_product_id),
        ("observed_at", expected.observed_at),
        ("geo_code", expected.geo_code),
        ("device_profile", expected.device_profile),
        ("currency", expected.currency),
        ("availability_status", expected.availability_status),
        ("primary_price", expected.primary_price),
        ("list_price", expected.mrp),
        ("discount_percent", expected.discount_percent),
        ("coupon_text", expected.coupon_text),
        ("coupon_value", expected.coupon_value),
        ("coupon_type", expected.coupon_type),
        ("shipping_amount", expected.shipping_amount),
        ("effective_price", expected.effective_price),
        ("primary_seller_name", expected.primary_seller_name),
        ("primary_seller_id", expected.primary_seller_id),
        ("is_featured_offer", expected.is_featured_offer),
        ("seller_count", expected.seller_count),
        ("source_job_id", expected.source_job_id),
        ("parser_version", expected.parser_version),
        ("source_url", expected.source_url),
        ("provider", expected.provider),
        ("source_metadata", expected.source_metadata),
    )
    if any(not _equal(getattr(existing, field), value) for field, value in fields):
        _conflict()
    if _offers(existing) != _offers(expected):
        _conflict()


def _offers(value: PriceObservation | PriceObservationIn) -> list[tuple[object, ...]]:
    offers = value.offers
    comparisons = [
        (
            offer.seller_name,
            offer.seller_id,
            offer.offer_price,
            offer.list_price,
            offer.shipping_amount,
            offer.coupon_text,
            offer.coupon_value,
            offer.effective_price,
            offer.availability_status,
            offer.fulfillment_type,
            offer.is_featured_offer,
            offer.prime_eligible,
            _canonical_json(offer.offer_metadata),
        )
        for offer in offers
    ]
    return sorted(comparisons, key=lambda offer: json.dumps(offer, default=str, sort_keys=True))


def _canonical_json(value: object) -> str:
    return json.dumps(value, default=str, separators=(",", ":"), sort_keys=True)


def _equal(left: object, right: object) -> bool:
    if isinstance(left, datetime) and isinstance(right, datetime):
        return _utc(left) == _utc(right)
    if isinstance(left, Enum):
        left = left.value
    if isinstance(right, Enum):
        right = right.value
    return left == right


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _validate_context(
    config: AmazonProductPublicationConfig, product_id: UUID | None, competitor_id: UUID | None
) -> None:
    if config.product_id is not None and product_id != config.product_id:
        raise ValueError("Amazon product publication owned-product context conflicts with mapping")
    if config.competitor_product_id is not None and competitor_id != config.competitor_product_id:
        raise ValueError("Amazon product publication competitor context conflicts with mapping")

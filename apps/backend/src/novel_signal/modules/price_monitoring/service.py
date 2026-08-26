from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from novel_signal.modules.price_monitoring.errors import (
    PriceConflict,
    PriceNotFound,
    PriceValidation,
)
from novel_signal.modules.price_monitoring.models import (
    AvailabilityStatus,
    CouponType,
    PriceChangeEvent,
    PriceEventType,
    PriceObservation,
    SellerOffer,
)
from novel_signal.modules.price_monitoring.repository import PriceRepository
from novel_signal.modules.price_monitoring.schemas import (
    Freshness,
    FreshnessStatus,
    PriceComparison,
    PriceMetrics,
    PriceObservationIn,
    PricePerUnitComparison,
    PricePerUnitSide,
    PriceSide,
)
from novel_signal.modules.universe.models import CompetitorProduct, Product

CENT = Decimal("0.01")
FRESHNESS_MINUTES = 240


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized or None


def money(value: Decimal | None) -> Decimal | None:
    return value.quantize(CENT, rounding=ROUND_HALF_UP) if value is not None else None


class PriceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = PriceRepository(session)

    def identity(
        self,
        product_id: uuid.UUID | None,
        competitor_product_id: uuid.UUID | None,
        marketplace_product_id: str | None,
    ) -> None:
        if (
            sum(
                x is not None and str(x).strip() != ""
                for x in (product_id, competitor_product_id, marketplace_product_id)
            )
            != 1
        ):
            raise PriceValidation("Provide exactly one price identity")

    def _discount(self, payload: PriceObservationIn) -> Decimal | None:
        if payload.discount_percent is not None:
            return money(payload.discount_percent)
        if (
            payload.mrp
            and payload.primary_price is not None
            and payload.primary_price <= payload.mrp
        ):
            return money((payload.mrp - payload.primary_price) * Decimal(100) / payload.mrp)
        return None

    def _effective(
        self,
        price: Decimal | None,
        shipping: Decimal | None,
        coupon: Decimal | None,
        coupon_type: CouponType | None,
        explicit: Decimal | None,
    ) -> Decimal | None:
        if explicit is not None:
            return money(explicit)
        if price is None:
            return None
        total = price + (shipping or Decimal(0))
        if coupon is not None and coupon_type == CouponType.ABSOLUTE:
            total -= coupon
        return money(max(total, Decimal(0)))

    def ingest(self, payload: PriceObservationIn) -> PriceObservation:
        if payload.ingestion_key and self.repo.by_key(payload.ingestion_key):
            raise PriceConflict("An observation with this ingestion key already exists")
        owned, competitor = self.repo.mappings(payload.marketplace, payload.marketplace_product_id)
        if owned and competitor:
            raise PriceValidation("Marketplace identity maps ambiguously")
        offer_count = len({(x.seller_id or x.seller_name).casefold() for x in payload.offers})
        seller_count = (
            payload.seller_count
            if payload.seller_count is not None
            else (offer_count if payload.offers else None)
        )
        observation = PriceObservation(
            marketplace=payload.marketplace,
            marketplace_product_id=payload.marketplace_product_id,
            product_id=owned,
            competitor_product_id=competitor,
            observed_at=payload.observed_at,
            geo_code=clean(payload.geo_code),
            device_profile=clean(payload.device_profile),
            currency=payload.currency.upper(),
            availability_status=payload.availability_status,
            primary_price=money(payload.primary_price),
            list_price=money(payload.mrp),
            discount_percent=self._discount(payload),
            coupon_text=clean(payload.coupon_text),
            coupon_value=money(payload.coupon_value),
            coupon_type=payload.coupon_type,
            shipping_amount=money(payload.shipping_amount),
            effective_price=self._effective(
                payload.primary_price,
                payload.shipping_amount,
                payload.coupon_value,
                payload.coupon_type,
                payload.effective_price,
            ),
            primary_seller_name=clean(payload.primary_seller_name),
            primary_seller_id=clean(payload.primary_seller_id),
            is_featured_offer=payload.is_featured_offer,
            seller_count=seller_count,
            source_job_id=payload.source_job_id,
            parser_version=clean(payload.parser_version),
            source_url=clean(payload.source_url),
            ingestion_key=payload.ingestion_key,
            provider=clean(payload.provider),
            source_metadata=payload.source_metadata,
        )
        for item in payload.offers:
            observation.offers.append(
                SellerOffer(
                    seller_name=item.seller_name,
                    seller_id=clean(item.seller_id),
                    offer_price=money(item.offer_price),
                    list_price=money(item.list_price),
                    shipping_amount=money(item.shipping_amount),
                    coupon_text=clean(item.coupon_text),
                    coupon_value=money(item.coupon_value),
                    effective_price=self._effective(
                        item.offer_price,
                        item.shipping_amount,
                        item.coupon_value,
                        CouponType.ABSOLUTE if item.coupon_value is not None else None,
                        item.effective_price,
                    ),
                    availability_status=item.availability_status,
                    fulfillment_type=clean(item.fulfillment_type),
                    is_featured_offer=item.is_featured_offer,
                    prime_eligible=item.prime_eligible,
                    offer_metadata=item.offer_metadata,
                )
            )
        previous = self.repo.latest(
            product_id=owned,
            competitor_product_id=competitor,
            marketplace_product_id=None if owned or competitor else payload.marketplace_product_id,
            marketplace=payload.marketplace,
            geo_code=observation.geo_code,
            before=payload.observed_at,
        )
        self.session.add(observation)
        try:
            self.session.flush()
            if previous:
                self._events(previous, observation)
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise PriceConflict("Price observation conflicts with existing data") from error
        except Exception:
            self.session.rollback()
            raise
        return observation

    def _event(
        self,
        old: PriceObservation,
        new: PriceObservation,
        kind: PriceEventType,
        absolute: Decimal | None = None,
        percent: Decimal | None = None,
    ) -> None:
        self.session.add(
            PriceChangeEvent(
                observation_id=new.id,
                previous_observation_id=old.id,
                marketplace=new.marketplace,
                marketplace_product_id=new.marketplace_product_id,
                product_id=new.product_id,
                competitor_product_id=new.competitor_product_id,
                event_type=kind,
                previous_price=old.primary_price,
                new_price=new.primary_price,
                absolute_change=absolute,
                percent_change=percent,
                geo_code=new.geo_code,
                currency=new.currency,
                observed_at=new.observed_at,
            )
        )

    def _events(self, old: PriceObservation, new: PriceObservation) -> None:
        if (
            old.primary_price is not None
            and new.primary_price is not None
            and old.primary_price != new.primary_price
        ):
            change = (new.primary_price - old.primary_price).quantize(CENT, rounding=ROUND_HALF_UP)
            percent = (
                money(change * Decimal(100) / old.primary_price) if old.primary_price else None
            )
            self._event(
                old,
                new,
                PriceEventType.PRICE_INCREASE
                if change and change > 0
                else PriceEventType.PRICE_DECREASE,
                change,
                percent,
            )
        old_available = old.availability_status in {
            AvailabilityStatus.AVAILABLE,
            AvailabilityStatus.LIMITED,
        }
        new_available = new.availability_status in {
            AvailabilityStatus.AVAILABLE,
            AvailabilityStatus.LIMITED,
        }
        if (
            old_available
            and not new_available
            and new.availability_status
            in {AvailabilityStatus.UNAVAILABLE, AvailabilityStatus.OUT_OF_STOCK}
        ):
            self._event(old, new, PriceEventType.BECAME_UNAVAILABLE)
        elif (
            not old_available
            and old.availability_status
            in {AvailabilityStatus.UNAVAILABLE, AvailabilityStatus.OUT_OF_STOCK}
            and new_available
        ):
            self._event(old, new, PriceEventType.BECAME_AVAILABLE)

    def get(self, id: uuid.UUID) -> PriceObservation:
        item = self.repo.get(id)
        if not item:
            raise PriceNotFound("Price observation not found")
        return item

    def latest(
        self,
        product_id: uuid.UUID | None,
        competitor_product_id: uuid.UUID | None,
        marketplace_product_id: str | None,
        geo_code: str | None = None,
    ) -> PriceObservation:
        self.identity(product_id, competitor_product_id, marketplace_product_id)
        item = self.repo.latest(
            product_id=product_id,
            competitor_product_id=competitor_product_id,
            marketplace_product_id=marketplace_product_id,
            geo_code=geo_code,
        )
        if not item:
            raise PriceNotFound("No price observation found")
        return item

    def freshness(self, item: PriceObservation, now: datetime | None = None) -> Freshness:
        current = now or datetime.now(UTC)
        observed = (
            item.observed_at if item.observed_at.tzinfo else item.observed_at.replace(tzinfo=UTC)
        )
        age = max(0, int((current - observed).total_seconds() // 60))
        return Freshness(
            observed_at=item.observed_at,
            age_minutes=age,
            freshness_status=FreshnessStatus.FRESH
            if age <= FRESHNESS_MINUTES
            else FreshnessStatus.STALE,
        )

    def metrics(
        self,
        *,
        product_id: uuid.UUID | None,
        competitor_product_id: uuid.UUID | None,
        marketplace_product_id: str | None,
        geo_code: str | None,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> PriceMetrics:
        self.identity(product_id, competitor_product_id, marketplace_product_id)
        if from_at and to_at and from_at > to_at:
            raise PriceValidation("from must not be after to")
        rows, _ = self.repo.observations(
            limit=10000,
            offset=0,
            product_id=product_id,
            competitor_product_id=competitor_product_id,
            marketplace_product_id=marketplace_product_id,
            geo_code=geo_code,
            from_at=from_at,
            to_at=to_at,
            ascending=True,
        )
        if not rows:
            raise PriceNotFound("No price observations found")
        values = [x.primary_price for x in rows if x.primary_price is not None]
        last_event = next(
            (
                e
                for row in reversed(rows)
                for e in row.events
                if e.event_type in {PriceEventType.PRICE_INCREASE, PriceEventType.PRICE_DECREASE}
            ),
            None,
        )
        latest = rows[-1]
        return PriceMetrics(
            latest_price=latest.primary_price,
            minimum_price=min(values) if values else None,
            maximum_price=max(values) if values else None,
            average_price=money(sum(values, Decimal(0)) / len(values)) if values else None,
            observation_count=len(rows),
            latest_mrp=latest.list_price,
            latest_discount=latest.discount_percent,
            latest_effective_price=latest.effective_price,
            last_movement_amount=last_event.absolute_change if last_event else None,
            last_movement_percent=last_event.percent_change if last_event else None,
        )

    def comparison(
        self, product_id: uuid.UUID, competitor_product_id: uuid.UUID, geo_code: str | None
    ) -> PriceComparison:
        owned_item = self.latest(product_id, None, None, geo_code)
        competitor_item = self.latest(None, competitor_product_id, None, geo_code)

        def side(item: PriceObservation) -> PriceSide:
            return PriceSide(
                primary_price=item.primary_price,
                effective_price=item.effective_price,
                mrp=item.list_price,
                discount_percent=item.discount_percent,
                seller_count=item.seller_count,
                availability_status=item.availability_status,
                freshness=self.freshness(item),
            )

        owned, competitor = side(owned_item), side(competitor_item)
        signals: list[str] = []
        if owned.availability_status in {
            AvailabilityStatus.UNAVAILABLE,
            AvailabilityStatus.OUT_OF_STOCK,
        }:
            signals.append("owned_unavailable")
        if competitor.availability_status in {
            AvailabilityStatus.UNAVAILABLE,
            AvailabilityStatus.OUT_OF_STOCK,
        }:
            signals.append("competitor_unavailable")
        if owned.primary_price is not None and competitor.primary_price is not None:
            signals.append(
                "owned_cheaper"
                if owned.primary_price < competitor.primary_price
                else "owned_more_expensive"
                if owned.primary_price > competitor.primary_price
                else "same_price"
            )
        if owned.freshness.freshness_status == FreshnessStatus.STALE:
            signals.append("owned_stale")
        if competitor.freshness.freshness_status == FreshnessStatus.STALE:
            signals.append("competitor_stale")

        def delta(a: Decimal | int | None, b: Decimal | int | None) -> Decimal | int | None:
            return a - b if a is not None and b is not None else None

        return PriceComparison(
            owned=owned,
            competitor=competitor,
            deltas={
                "primary_price_difference": delta(owned.primary_price, competitor.primary_price),
                "effective_price_difference": delta(
                    owned.effective_price, competitor.effective_price
                ),
                "discount_difference": delta(owned.discount_percent, competitor.discount_percent),
                "seller_count_difference": delta(owned.seller_count, competitor.seller_count),
            },
            signals=signals,
        )

    def price_per_unit_comparison(
        self, product_id: uuid.UUID, competitor_product_id: uuid.UUID, geo_code: str | None
    ) -> PricePerUnitComparison:
        product = self.session.get(Product, product_id)
        competitor = self.session.get(CompetitorProduct, competitor_product_id)
        if product is None or product.archived_at is not None:
            raise PriceNotFound("Owned product not found")
        if competitor is None or competitor.archived_at is not None:
            raise PriceNotFound("Competitor product not found")
        owned_observation = self.latest(product_id, None, None, geo_code)
        competitor_observation = self.latest(None, competitor_product_id, None, geo_code)

        def side(
            observation: PriceObservation, quantity: int | None, unit: str | None
        ) -> PricePerUnitSide:
            normalized_unit = clean(unit)
            per_unit = (
                money(observation.primary_price / Decimal(quantity))
                if observation.primary_price is not None and quantity is not None and quantity > 0
                else None
            )
            return PricePerUnitSide(
                observation_id=observation.id,
                price=observation.primary_price,
                pack_quantity=quantity,
                pack_unit=normalized_unit.casefold() if normalized_unit else None,
                price_per_unit=per_unit,
            )

        owned = side(owned_observation, product.pack_quantity, product.pack_unit)
        competing = side(competitor_observation, competitor.pack_quantity, competitor.pack_unit)
        comparable = (
            owned.price_per_unit is not None
            and competing.price_per_unit is not None
            and owned.pack_unit is not None
            and owned.pack_unit == competing.pack_unit
        )
        return PricePerUnitComparison(
            owned=owned,
            competitor=competing,
            comparable=comparable,
            unit=owned.pack_unit if comparable else None,
            difference=money(owned.price_per_unit - competing.price_per_unit)
            if comparable
            and owned.price_per_unit is not None
            and competing.price_per_unit is not None
            else None,
        )

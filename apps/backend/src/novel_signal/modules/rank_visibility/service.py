from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from novel_signal.modules.rank_visibility.errors import (
    RankVisibilityConflictError,
    RankVisibilityNotFoundError,
    RankVisibilityValidationError,
)
from novel_signal.modules.rank_visibility.models import (
    BadgeEvent,
    BadgeEventType,
    BadgeType,
    DeviceProfile,
    NewEntrantEvent,
    PlacementType,
    SerpCapture,
    SerpResult,
)
from novel_signal.modules.rank_visibility.repository import RankVisibilityRepository
from novel_signal.modules.rank_visibility.schemas import (
    BrandPresence,
    BrandPresenceRow,
    CaptureIngest,
    RankHistory,
    RankObservation,
    VisibilityMetrics,
)
from novel_signal.modules.universe.models import Marketplace


class RankVisibilityService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = RankVisibilityRepository(session)

    def ingest(self, payload: CaptureIngest) -> SerpCapture:
        if not self.repository.keyword_exists(payload.keyword_id):
            raise RankVisibilityNotFoundError("Keyword does not exist", code="keyword_not_found")
        if payload.ingestion_key and self.repository.capture_by_ingestion_key(
            payload.ingestion_key
        ):
            raise RankVisibilityConflictError("A capture with this ingestion key already exists")

        ordered = sorted(payload.results, key=lambda item: item.absolute_position)
        counters: Counter[PlacementType] = Counter()
        for row in ordered:
            counters[row.placement_type] += 1
            if (
                row.within_type_position is not None
                and row.within_type_position != counters[row.placement_type]
            ):
                raise RankVisibilityValidationError(
                    f"within_type_position for absolute position {row.absolute_position} "
                    f"must be {counters[row.placement_type]}"
                )

        ids = {row.marketplace_product_id for row in ordered}
        owned, competitors = self.repository.product_mappings(payload.marketplace, ids)
        capture = SerpCapture(
            keyword_id=payload.keyword_id,
            marketplace=payload.marketplace,
            geo_code=payload.geo_code,
            device_profile=payload.device_profile,
            captured_at=payload.captured_at,
            page_count=max(row.page_number for row in ordered),
            result_count=len(ordered),
            source_job_id=payload.source_job_id,
            parser_version=payload.parser_version,
            ingestion_key=payload.ingestion_key,
            capture_metadata=payload.capture_metadata,
        )
        self.session.add(capture)
        try:
            self.session.flush()
            counters.clear()
            for item in ordered:
                counters[item.placement_type] += 1
                owned_id = owned.get(item.marketplace_product_id)
                competitor_id = competitors.get(item.marketplace_product_id)
                # Cross-table identity collisions are retained as unmapped instead of creating
                # an impossible dual mapping or making the entire capture fail.
                if owned_id and competitor_id:
                    owned_id = None
                    competitor_id = None
                result = SerpResult(
                    capture_id=capture.id,
                    absolute_position=item.absolute_position,
                    within_type_position=item.within_type_position or counters[item.placement_type],
                    page_number=item.page_number,
                    marketplace_product_id=item.marketplace_product_id,
                    product_id=owned_id,
                    competitor_product_id=competitor_id,
                    brand=item.brand,
                    placement_type=item.placement_type,
                    badges=[badge.value for badge in item.badges],
                    amazons_choice_term=item.amazons_choice_term,
                    displayed_price=item.displayed_price,
                    mrp=item.mrp,
                    discount_percent=item.discount_percent,
                    coupon=item.coupon,
                    delivery_promise=item.delivery_promise,
                    rating=item.rating,
                    review_count=item.review_count,
                    thumbnail_hash=item.thumbnail_hash,
                    result_metadata=item.result_metadata,
                )
                self.session.add(result)
                self.session.flush()
                self._record_badge_changes(capture, result)
                self._record_new_entrant(capture, result)
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            if payload.ingestion_key:
                raise RankVisibilityConflictError(
                    "A capture with this ingestion key already exists"
                ) from error
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_capture(capture.id)

    def _record_badge_changes(self, capture: SerpCapture, result: SerpResult) -> None:
        previous = self.repository.previous_result(capture, result.marketplace_product_id)
        old = set(previous.badges if previous else [])
        new = set(result.badges)
        for badge, event_type in [
            *((badge, BadgeEventType.ACQUIRED) for badge in sorted(new - old)),
            *((badge, BadgeEventType.LOST) for badge in sorted(old - new)),
        ]:
            self.session.add(
                BadgeEvent(
                    keyword_id=capture.keyword_id,
                    capture_id=capture.id,
                    result_id=result.id,
                    marketplace_product_id=result.marketplace_product_id,
                    product_id=result.product_id,
                    competitor_product_id=result.competitor_product_id,
                    brand=result.brand,
                    badge_type=BadgeType(badge),
                    event_type=event_type,
                    observed_at=capture.captured_at,
                )
            )

    def _record_new_entrant(self, capture: SerpCapture, result: SerpResult) -> None:
        if result.page_number != 1 or self.repository.entrant_exists(
            capture, result.marketplace_product_id
        ):
            return
        self.session.add(
            NewEntrantEvent(
                keyword_id=capture.keyword_id,
                marketplace=capture.marketplace,
                marketplace_product_id=result.marketplace_product_id,
                product_id=result.product_id,
                competitor_product_id=result.competitor_product_id,
                first_seen_capture_id=capture.id,
                first_seen_at=capture.captured_at,
                rank=result.absolute_position,
                brand=result.brand,
                geo_code=capture.geo_code,
                device_profile=capture.device_profile,
            )
        )
        self.session.flush()

    def get_capture(self, capture_id: uuid.UUID) -> SerpCapture:
        capture = self.repository.capture(capture_id, with_results=True)
        if capture is None:
            raise RankVisibilityNotFoundError("SERP capture not found")
        return capture

    def validate_identity(
        self,
        product_id: uuid.UUID | None,
        competitor_product_id: uuid.UUID | None,
        marketplace_product_id: str | None,
    ) -> str:
        identities = [
            str(value)
            for value in (product_id, competitor_product_id, marketplace_product_id)
            if value is not None and str(value).strip()
        ]
        if len(identities) != 1:
            raise RankVisibilityValidationError(
                "Provide exactly one of product_id, competitor_product_id, "
                "or marketplace_product_id"
            )
        return identities[0]

    def rank_history(
        self,
        *,
        keyword_id: uuid.UUID,
        product_id: uuid.UUID | None,
        competitor_product_id: uuid.UUID | None,
        marketplace_product_id: str | None,
        marketplace: Marketplace | None,
        geo_code: str | None,
        device_profile: DeviceProfile | None,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> RankHistory:
        identity = self.validate_identity(product_id, competitor_product_id, marketplace_product_id)
        rows = self.repository.result_history(
            keyword_id=keyword_id,
            product_id=product_id,
            competitor_product_id=competitor_product_id,
            marketplace_product_id=marketplace_product_id,
            marketplace=marketplace,
            geo_code=geo_code,
            device_profile=device_profile,
            from_at=from_at,
            to_at=to_at,
        )
        return RankHistory(
            keyword_id=keyword_id,
            identity=identity,
            observations=[
                RankObservation(
                    capture_id=capture.id,
                    captured_at=capture.captured_at,
                    absolute_position=result.absolute_position,
                    organic_rank=result.within_type_position
                    if result.placement_type == PlacementType.ORGANIC
                    else None,
                    placement_type=result.placement_type,
                    page_number=result.page_number,
                    displayed_price=result.displayed_price,
                    rating=result.rating,
                    review_count=result.review_count,
                )
                for result, capture in rows
            ],
        )

    def visibility(self, **filters: object) -> VisibilityMetrics:
        history = self.rank_history(**filters)  # type: ignore[arg-type]
        grouped: dict[uuid.UUID, list[RankObservation]] = defaultdict(list)
        for observation in history.observations:
            grouped[observation.capture_id].append(observation)
        capture_rows = [
            min(rows, key=lambda row: row.absolute_position) for rows in grouped.values()
        ]
        organic = [
            min((row.organic_rank for row in rows if row.organic_rank is not None), default=None)
            for rows in grouped.values()
        ]
        moves = [
            abs(current.absolute_position - previous.absolute_position)
            for previous, current in zip(capture_rows, capture_rows[1:], strict=False)
        ]
        denominator = len(capture_rows)
        return VisibilityMetrics(
            keyword_id=history.keyword_id,
            identity=history.identity,
            latest_rank=capture_rows[-1].absolute_position if capture_rows else None,
            best_rank=min((row.absolute_position for row in capture_rows), default=None),
            latest_organic_rank=organic[-1] if organic else None,
            observation_count=denominator,
            rank_volatility=round(sum(moves) / len(moves), 2) if moves else 0.0,
            time_in_top_3_percent=round(
                sum(rank is not None and rank <= 3 for rank in organic) / denominator * 100, 2
            )
            if denominator
            else 0.0,
            time_in_top_10_percent=round(
                sum(rank is not None and rank <= 10 for rank in organic) / denominator * 100, 2
            )
            if denominator
            else 0.0,
        )

    def brand_presence(
        self,
        *,
        capture_id: uuid.UUID | None,
        keyword_id: uuid.UUID | None,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> BrandPresence:
        if capture_id and self.repository.capture(capture_id) is None:
            raise RankVisibilityNotFoundError("SERP capture not found")
        if not capture_id and not keyword_id:
            raise RankVisibilityValidationError("Provide capture_id or keyword_id")
        rows = self.repository.brand_results(
            capture_id=capture_id, keyword_id=keyword_id, from_at=from_at, to_at=to_at
        )
        by_brand: dict[str, list[SerpResult]] = defaultdict(list)
        for row in rows:
            by_brand[(row.brand or "Unknown").strip() or "Unknown"].append(row)
        total = len(rows)
        brands = []
        for brand, results in sorted(by_brand.items(), key=lambda item: (-len(item[1]), item[0])):
            organic = sum(row.placement_type == PlacementType.ORGANIC for row in results)
            brands.append(
                BrandPresenceRow(
                    brand=brand,
                    page_1_slot_count=len(results),
                    page_1_share_percent=round(len(results) / total * 100, 2) if total else 0.0,
                    organic_slots=organic,
                    sponsored_slots=len(results) - organic,
                )
            )
        return BrandPresence(total_page_1_results=total, brands=brands)

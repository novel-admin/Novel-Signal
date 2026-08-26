from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from collections.abc import Callable
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
    AmazonShareOfVoice,
    BrandPresence,
    BrandPresenceRow,
    CaptureIngest,
    KeywordGapAnalysis,
    KeywordGapRow,
    RankHistory,
    RankObservation,
    ReverseAsinIntelligence,
    ReverseAsinKeyword,
    ShareOfVoiceMetric,
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

    def reverse_asin(
        self,
        *,
        product_id: uuid.UUID | None,
        competitor_product_id: uuid.UUID | None,
        marketplace_product_id: str | None,
        marketplace: Marketplace | None,
        geo_code: str | None,
        device_profile: DeviceProfile | None,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> ReverseAsinIntelligence:
        identity = self.validate_identity(product_id, competitor_product_id, marketplace_product_id)
        rows = self.repository.identity_history(
            product_id=product_id,
            competitor_product_id=competitor_product_id,
            marketplace_product_id=marketplace_product_id,
            marketplace=marketplace,
            geo_code=geo_code,
            device_profile=device_profile,
            from_at=from_at,
            to_at=to_at,
        )
        grouped: dict[
            tuple[uuid.UUID, str, DeviceProfile],
            list[tuple[SerpResult, SerpCapture, object]],
        ] = defaultdict(list)
        keyword_names: dict[uuid.UUID, str] = {}
        for result, capture, keyword in rows:
            grouped[(capture.keyword_id, capture.geo_code, capture.device_profile)].append(
                (result, capture, keyword)
            )
            keyword_names[capture.keyword_id] = keyword.keyword_text
        output: list[ReverseAsinKeyword] = []
        for (keyword_id, _, _), observations in grouped.items():
            latest_at = max(capture.captured_at for _, capture, _ in observations)
            latest = [
                (result, capture)
                for result, capture, _ in observations
                if capture.captured_at == latest_at
            ]
            best_latest = min(latest, key=lambda row: row[0].absolute_position)
            organic = [
                result.within_type_position
                for result, _ in latest
                if result.placement_type == PlacementType.ORGANIC
            ]
            output.append(
                ReverseAsinKeyword(
                    keyword_id=keyword_id,
                    keyword_text=keyword_names[keyword_id],
                    latest_position=best_latest[0].absolute_position,
                    latest_organic_position=min(organic, default=None),
                    sponsored_present=any(_is_paid(result) for result, _ in latest),
                    first_observed_at=min(capture.captured_at for _, capture, _ in observations),
                    latest_observed_at=latest_at,
                    latest_capture_id=best_latest[1].id,
                    latest_result_ids=sorted((result.id for result, _ in latest), key=str),
                    marketplace=best_latest[1].marketplace,
                    geo_code=best_latest[1].geo_code,
                    device_profile=best_latest[1].device_profile,
                    source_job_id=best_latest[1].source_job_id,
                    parser_version=best_latest[1].parser_version,
                )
            )
        output.sort(key=lambda row: (row.latest_position, row.keyword_text, str(row.keyword_id)))
        return ReverseAsinIntelligence(
            identity=identity,
            keyword_count=len({row.keyword_id for row in output}),
            context_count=len(output),
            keywords=output,
        )

    def share_of_voice(
        self,
        *,
        capture_id: uuid.UUID,
        brand: str | None,
        product_id: uuid.UUID | None,
        competitor_product_id: uuid.UUID | None,
        marketplace_product_id: str | None,
    ) -> AmazonShareOfVoice:
        selectors = [
            value
            for value in (brand, product_id, competitor_product_id, marketplace_product_id)
            if value is not None and str(value).strip()
        ]
        if len(selectors) != 1:
            raise RankVisibilityValidationError(
                "Provide exactly one of brand, product_id, competitor_product_id, "
                "or marketplace_product_id"
            )
        capture = self.get_capture(capture_id)

        def matches(result: SerpResult) -> bool:
            if brand is not None:
                return (result.brand or "").strip().casefold() == brand.strip().casefold()
            if product_id is not None:
                return result.product_id == product_id
            if competitor_product_id is not None:
                return result.competitor_product_id == competitor_product_id
            return result.marketplace_product_id == marketplace_product_id

        organic = [row for row in capture.results if row.placement_type == PlacementType.ORGANIC]
        paid = [row for row in capture.results if _is_paid(row)]
        eligible = [*organic, *paid]
        matched = [row for row in eligible if matches(row)]
        identity = str(selectors[0]).strip()
        return AmazonShareOfVoice(
            capture_id=capture.id,
            keyword_id=capture.keyword_id,
            captured_at=capture.captured_at,
            marketplace=capture.marketplace,
            geo_code=capture.geo_code,
            device_profile=capture.device_profile,
            identity=identity,
            organic=_share(organic, matches),
            paid=_share(paid, matches),
            total=_share(eligible, matches),
            matched_result_ids=sorted((row.id for row in matched), key=str),
            source_job_id=capture.source_job_id,
            parser_version=capture.parser_version,
        )

    def keyword_gaps(
        self,
        *,
        owned_product_id: uuid.UUID,
        competitor_product_id: uuid.UUID,
        geo_code: str | None,
        device_profile: DeviceProfile | None,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> KeywordGapAnalysis:
        captures = self.repository.filtered_captures_with_results(
            marketplace=Marketplace.AMAZON_IN,
            geo_code=geo_code,
            device_profile=device_profile,
            from_at=from_at,
            to_at=to_at,
        )
        latest: dict[tuple[uuid.UUID, str, DeviceProfile], SerpCapture] = {}
        for capture in captures:
            latest[(capture.keyword_id, capture.geo_code, capture.device_profile)] = capture
        gaps: list[KeywordGapRow] = []
        for capture in latest.values():
            owned = [row for row in capture.results if row.product_id == owned_product_id]
            competitor = [
                row for row in capture.results if row.competitor_product_id == competitor_product_id
            ]
            owned_organic = any(row.placement_type == PlacementType.ORGANIC for row in owned)
            competitor_organic = any(
                row.placement_type == PlacementType.ORGANIC for row in competitor
            )
            owned_paid = any(_is_paid(row) for row in owned)
            competitor_paid = any(_is_paid(row) for row in competitor)
            types = []
            if competitor and not owned:
                types.append("competitor_present_owned_absent")
            if competitor_organic and not owned_organic:
                types.append("owned_organic_gap")
            if competitor_paid and not owned_paid:
                types.append("owned_paid_gap")
            if not types:
                continue
            gaps.append(
                KeywordGapRow(
                    keyword_id=capture.keyword_id,
                    capture_id=capture.id,
                    captured_at=capture.captured_at,
                    geo_code=capture.geo_code,
                    device_profile=capture.device_profile,
                    owned_present=bool(owned),
                    competitor_present=bool(competitor),
                    owned_organic_present=owned_organic,
                    competitor_organic_present=competitor_organic,
                    owned_paid_present=owned_paid,
                    competitor_paid_present=competitor_paid,
                    gap_types=types,
                    competitor_result_ids=sorted((row.id for row in competitor), key=str),
                    source_job_id=capture.source_job_id,
                    parser_version=capture.parser_version,
                )
            )
        gaps.sort(key=lambda row: (row.captured_at, str(row.keyword_id), row.geo_code))
        return KeywordGapAnalysis(
            owned_product_id=owned_product_id,
            competitor_product_id=competitor_product_id,
            contexts_checked=len(latest),
            gap_count=len(gaps),
            gaps=gaps,
        )


def _is_paid(result: SerpResult) -> bool:
    return result.placement_type in {
        PlacementType.SPONSORED_PRODUCT,
        PlacementType.SPONSORED_BRAND,
        PlacementType.SPONSORED_BRAND_VIDEO,
        PlacementType.SPONSORED_DISPLAY,
    }


def _share(rows: list[SerpResult], matches: Callable[[SerpResult], bool]) -> ShareOfVoiceMetric:
    matched = sum(matches(row) for row in rows)
    total = len(rows)
    return ShareOfVoiceMetric(
        matched_slots=matched,
        eligible_slots=total,
        share_percent=round(matched / total * 100, 2) if total else 0.0,
    )

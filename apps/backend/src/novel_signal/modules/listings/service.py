from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from novel_signal.modules.listings.errors import ListingConflict, ListingNotFound, ListingValidation
from novel_signal.modules.listings.models import (
    ListingChangeEvent,
    ListingChangeType,
    ListingSnapshot,
)
from novel_signal.modules.listings.repository import ListingRepository
from novel_signal.modules.listings.schemas import Comparison, Completeness, SnapshotIn, Stats

WEIGHTS = {
    "title": 15,
    "brand": 5,
    "bullets_3": 20,
    "description": 10,
    "a_plus": 15,
    "images_5": 20,
    "video": 5,
    "variations": 10,
}
FIELDS = (
    "title",
    "brand",
    "category_path",
    "bullets",
    "description",
    "a_plus_present",
    "a_plus_sections",
    "image_urls",
    "image_hashes",
    "image_count",
    "video_present",
    "video_count",
    "variation_count",
    "variation_metadata",
)


def text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized or None


def texts(values: list[str]) -> list[str]:
    return list(dict.fromkeys(v for x in values if (v := text(x))))


def quality(snapshot: ListingSnapshot) -> Completeness:
    achieved = {
        "title": bool(snapshot.title),
        "brand": bool(snapshot.brand),
        "bullets_3": len(snapshot.bullets) >= 3,
        "description": bool(snapshot.description),
        "a_plus": snapshot.a_plus_present,
        "images_5": snapshot.image_count >= 5,
        "video": snapshot.video_present,
        "variations": bool(snapshot.variation_count or snapshot.variation_metadata),
    }
    breakdown = {k: (WEIGHTS[k] if v else 0) for k, v in achieved.items()}
    return Completeness(
        score=sum(breakdown.values()),
        breakdown=breakdown,
        achieved_components=[k for k, v in achieved.items() if v],
        missing_components=[k for k, v in achieved.items() if not v],
    )


class ListingService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ListingRepository(session)

    def identity(self, p: uuid.UUID | None, c: uuid.UUID | None, m: str | None) -> str:
        values = [str(x) for x in (p, c, m) if x is not None and str(x).strip()]
        if len(values) != 1:
            raise ListingValidation("Provide exactly one listing identity")
        return values[0]

    def ingest(self, payload: SnapshotIn) -> ListingSnapshot:
        if payload.ingestion_key and self.repo.by_key(payload.ingestion_key):
            raise ListingConflict("A snapshot with this ingestion key already exists")
        owned, competitor = self.repo.mappings(payload.marketplace, payload.marketplace_product_id)
        if owned and competitor:
            raise ListingValidation("Marketplace identity maps ambiguously")
        bullets = texts(payload.bullets)
        features = texts(payload.key_features)
        urls = texts(payload.image_urls)
        hashes = texts(payload.image_hashes)
        images = hashes or urls
        video_count = (
            payload.video_count
            if payload.video_count is not None
            else (1 if payload.video_present else 0)
        )
        snapshot = ListingSnapshot(
            marketplace=payload.marketplace,
            marketplace_product_id=payload.marketplace_product_id,
            product_id=owned,
            competitor_product_id=competitor,
            captured_at=payload.captured_at,
            geo_code=text(payload.geo_code),
            device_profile=text(payload.device_profile),
            source_job_id=payload.source_job_id,
            parser_version=text(payload.parser_version),
            ingestion_key=payload.ingestion_key,
            source_url=text(payload.source_url),
            title=text(payload.title),
            brand=text(payload.brand),
            category_path=text(payload.category_path),
            description=text(payload.description),
            bullets=bullets,
            key_features=features,
            a_plus_present=payload.a_plus_present,
            a_plus_sections=payload.a_plus_sections,
            image_urls=urls,
            image_hashes=hashes,
            image_count=len(images),
            video_present=video_count > 0,
            video_count=video_count,
            variation_count=payload.variation_count,
            variation_metadata=payload.variation_metadata,
            storefront_text=text(payload.storefront_text),
            content_metadata=payload.content_metadata,
            completeness_score=0,
            completeness_breakdown={},
        )
        q = quality(snapshot)
        snapshot.completeness_score = q.score
        snapshot.completeness_breakdown = q.breakdown
        previous = self.repo.latest(
            product_id=owned,
            competitor_product_id=competitor,
            marketplace_product_id=None if owned or competitor else payload.marketplace_product_id,
            marketplace=payload.marketplace,
            before=payload.captured_at,
        )
        self.session.add(snapshot)
        try:
            self.session.flush()
            if previous:
                self._diff(previous, snapshot)
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise ListingConflict("Snapshot ingestion conflicts with existing data") from error
        except Exception:
            self.session.rollback()
            raise
        return snapshot

    def _diff(self, old: ListingSnapshot, new: ListingSnapshot) -> None:
        for field in FIELDS:
            before = getattr(old, field)
            after = getattr(new, field)
            if before == after:
                continue
            if before in (None, "", [], {}) and after not in (None, "", [], {}):
                kind = ListingChangeType.ADDED
            elif after in (None, "", [], {}) and before not in (None, "", [], {}):
                kind = ListingChangeType.REMOVED
            else:
                kind = ListingChangeType.MODIFIED
            self.session.add(
                ListingChangeEvent(
                    snapshot_id=new.id,
                    previous_snapshot_id=old.id,
                    marketplace=new.marketplace,
                    marketplace_product_id=new.marketplace_product_id,
                    product_id=new.product_id,
                    competitor_product_id=new.competitor_product_id,
                    field_name=field,
                    change_type=kind,
                    old_value=before,
                    new_value=after,
                    observed_at=new.captured_at,
                )
            )
        old_ids = old.image_hashes or old.image_urls
        new_ids = new.image_hashes or new.image_urls
        for field, before, after in (
            ("image_added", [], sorted(set(new_ids) - set(old_ids))),
            ("image_removed", sorted(set(old_ids) - set(new_ids)), []),
            ("main_image", old_ids[:1], new_ids[:1]),
        ):
            if before != after and (before or after):
                self.session.add(
                    ListingChangeEvent(
                        snapshot_id=new.id,
                        previous_snapshot_id=old.id,
                        marketplace=new.marketplace,
                        marketplace_product_id=new.marketplace_product_id,
                        product_id=new.product_id,
                        competitor_product_id=new.competitor_product_id,
                        field_name=field,
                        change_type=ListingChangeType.MODIFIED,
                        old_value=before,
                        new_value=after,
                        observed_at=new.captured_at,
                    )
                )

    def get(self, id: uuid.UUID) -> ListingSnapshot:
        item = self.repo.get(id)
        if not item:
            raise ListingNotFound("Listing snapshot not found")
        return item

    def latest(
        self,
        product_id: uuid.UUID | None,
        competitor_product_id: uuid.UUID | None,
        marketplace_product_id: str | None,
    ) -> ListingSnapshot:
        self.identity(product_id, competitor_product_id, marketplace_product_id)
        item = self.repo.latest(
            product_id=product_id,
            competitor_product_id=competitor_product_id,
            marketplace_product_id=marketplace_product_id,
        )
        if not item:
            raise ListingNotFound("No listing snapshot found")
        return item

    def completeness(self, **identity: Any) -> Completeness:
        return quality(self.latest(**identity))

    def stats(self, s: ListingSnapshot) -> Stats:
        return Stats(
            title_length=len(s.title or ""),
            bullet_count=len(s.bullets),
            description_length=len(s.description or ""),
            image_count=s.image_count,
            a_plus_present=s.a_plus_present,
            video_present=s.video_present,
            variation_count=s.variation_count or 0,
            completeness_score=s.completeness_score,
        )

    def comparison(self, product_id: uuid.UUID, competitor_product_id: uuid.UUID) -> Comparison:
        owned = self.stats(self.latest(product_id, None, None))
        competitor = self.stats(self.latest(None, competitor_product_id, None))
        d = {
            "score_difference": owned.completeness_score - competitor.completeness_score,
            "image_count_difference": owned.image_count - competitor.image_count,
            "bullet_count_difference": owned.bullet_count - competitor.bullet_count,
            "title_length_difference": owned.title_length - competitor.title_length,
            "a_plus_gap": competitor.a_plus_present and not owned.a_plus_present,
            "video_gap": competitor.video_present and not owned.video_present,
            "variation_count_difference": owned.variation_count - competitor.variation_count,
        }
        gaps = []
        if d["a_plus_gap"]:
            gaps.append("owned_missing_a_plus")
        if owned.image_count < competitor.image_count:
            gaps.append("owned_has_fewer_images")
        if owned.bullet_count < competitor.bullet_count:
            gaps.append("owned_has_fewer_bullets")
        if d["video_gap"]:
            gaps.append("owned_missing_video")
        if owned.completeness_score < competitor.completeness_score:
            gaps.append("owned_lower_completeness")
        return Comparison(owned=owned, competitor=competitor, deltas=d, gaps=gaps)

"""Automatic keyword seeding for the §1A CSV workflow.

CSV upload -> import products -> generate/score keywords -> collect rank and
product data. Generation is deterministic and idempotent: re-running never
duplicates keywords or tracking targets.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from novel_signal.modules.collection.service import CollectionPlanningService
from novel_signal.modules.keywords.intent import classify_keyword_intent
from novel_signal.modules.keywords.models import (
    Keyword,
    KeywordSource,
    KeywordSourceType,
    TrackingTarget,
)
from novel_signal.modules.keywords.schemas import normalize_keyword
from novel_signal.modules.universe.errors import UniverseNotFoundError
from novel_signal.modules.universe.models import Competitor, Product, TrackingTier

CADENCE_BY_TIER: dict[TrackingTier, int] = {
    TrackingTier.T1: 60,
    TrackingTier.T2: 240,
    TrackingTier.T3: 1440,
}

_STOPWORDS = frozenset(
    {
        "with", "from", "that", "this", "pack", "combo", "plus",
        "for", "and", "the", "set", "new",
    }
)


def candidate_keywords_for_product(product: Product) -> list[str]:
    """Build 3-8 scored keyword candidates from product identity fields."""
    candidates: list[str] = []
    category = (product.category or "").strip()
    brand = (product.brand or "").strip()
    name = (product.name or "").strip()
    if category and category.lower() != "unclassified":
        candidates.append(category)
    if brand and category:
        candidates.append(f"{brand} {category}")
    if name:
        candidates.append(name)
        tokens = [t for t in re.split(r"[^A-Za-z0-9]+", name) if t and t.lower() not in _STOPWORDS]
        for size in (3, 2):
            for index in range(len(tokens) - size + 1):
                phrase = " ".join(tokens[index : index + size])
                if phrase and phrase not in candidates:
                    candidates.append(phrase)
                if len(candidates) >= 8:
                    break
            if len(candidates) >= 8:
                break
    # Preserve order, enforce 3-8, drop blanks/duplicates (normalised).
    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        cleaned = re.sub(r"\s+", " ", candidate).strip()
        if not cleaned or len(cleaned) > 500:
            continue
        key = normalize_keyword(cleaned)
        if key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
        if len(unique) >= 8:
            break
    return unique[:8]


class KeywordGenerationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def generate_for_product(self, product_id: uuid.UUID) -> dict[str, object]:
        product = self.session.get(Product, product_id)
        if product is None:
            raise UniverseNotFoundError("product not found")
        competitors = list(
            self.session.scalars(
                select(Competitor.name).where(Competitor.archived_at.is_(None))
            )
        )
        candidates = candidate_keywords_for_product(product)
        created: list[dict[str, object]] = []
        reused: list[dict[str, object]] = []
        targets_created = 0
        cadence = CADENCE_BY_TIER.get(product.tracking_tier, 240)
        for text in candidates:
            normalized = normalize_keyword(text)
            keyword = self.session.scalar(
                select(Keyword).where(
                    Keyword.marketplace == product.marketplace,
                    Keyword.normalized_text == normalized,
                    Keyword.archived_at.is_(None),
                )
            )
            is_new = False
            if keyword is None:
                intent = classify_keyword_intent(
                    text,
                    owned_brands=[product.brand],
                    competitor_brands=competitors,
                    categories=[product.category],
                )
                keyword = Keyword(
                    keyword_text=text,
                    normalized_text=normalized,
                    marketplace=product.marketplace,
                    category=product.category,
                    tier=product.tracking_tier,
                    intent_cluster=intent,
                    sources=[
                        KeywordSource(
                            source_type=KeywordSourceType.MANUAL,
                            source_reference=f"product:{product.internal_sku}",
                        )
                    ],
                )
                self.session.add(keyword)
                self.session.flush()
                is_new = True
            summary = {"keyword_id": keyword.id, "keyword_text": keyword.keyword_text,
                       "created": is_new}
            (created if is_new else reused).append(summary)
            target = self.session.scalar(
                select(TrackingTarget).where(
                    TrackingTarget.keyword_id == keyword.id,
                    TrackingTarget.product_id == product.id,
                    TrackingTarget.archived_at.is_(None),
                )
            )
            if target is None:
                self.session.add(
                    TrackingTarget(
                        keyword_id=keyword.id,
                        product_id=product.id,
                        cadence_minutes=cadence,
                        enabled=True,
                    )
                )
                targets_created += 1
        self.session.commit()
        return {
            "product_id": product.id,
            "created_keywords": created,
            "reused_keywords": reused,
            "tracking_targets_created": targets_created,
        }

    def search_competitors(self, product_id: uuid.UUID, phrases: list[str]) -> dict[str, object]:
        """Create product targets and queue public Amazon SERP jobs for selected phrases."""
        product = self.session.get(Product, product_id)
        if product is None:
            raise UniverseNotFoundError("product not found")
        keyword_ids: set[uuid.UUID] = set()
        cadence = CADENCE_BY_TIER.get(product.tracking_tier, 240)
        for text in phrases:
            normalized = normalize_keyword(text)
            keyword = self.session.scalar(
                select(Keyword).where(
                    Keyword.marketplace == product.marketplace,
                    Keyword.normalized_text == normalized,
                    Keyword.archived_at.is_(None),
                )
            )
            if keyword is None:
                keyword = Keyword(
                    keyword_text=text,
                    normalized_text=normalized,
                    marketplace=product.marketplace,
                    category=product.category,
                    tier=product.tracking_tier,
                    intent_cluster=classify_keyword_intent(
                        text,
                        owned_brands=[product.brand],
                        categories=[product.category],
                    ),
                    sources=[
                        KeywordSource(
                            source_type=KeywordSourceType.MANUAL,
                            source_reference=f"competitor-search:{product.internal_sku}",
                        )
                    ],
                )
                self.session.add(keyword)
                self.session.flush()
            keyword_ids.add(keyword.id)
            target = self.session.scalar(
                select(TrackingTarget).where(
                    TrackingTarget.keyword_id == keyword.id,
                    TrackingTarget.product_id == product.id,
                    TrackingTarget.archived_at.is_(None),
                )
            )
            if target is None:
                self.session.add(
                    TrackingTarget(
                        keyword_id=keyword.id,
                        product_id=product.id,
                        cadence_minutes=cadence,
                        enabled=True,
                    )
                )
        self.session.flush()
        plan = CollectionPlanningService(self.session).plan_due(
            platforms={"amazon_in"}, entity_ids=keyword_ids
        )
        self.session.commit()
        return {
            "product_id": product.id,
            "keywords": phrases,
            "job_ids": [job.id for job in plan.jobs],
            "created_jobs": plan.created,
            "existing_jobs": plan.existing,
        }

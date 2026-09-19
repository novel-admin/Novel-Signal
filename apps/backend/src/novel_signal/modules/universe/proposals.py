"""Competitor discovery proposals (PM Phase 4).

Repeated keyword / related-product appearances that are not yet tracked are
proposed with evidence and stay inactive until an analyst approves them.
Unapproved proposals never reach scorecards, gaps, or alerts because those
read only from approved Competitor / CompetitorProduct rows.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from novel_signal.modules.keywords.models import TrackingTarget
from novel_signal.modules.rank_visibility.models import NewEntrantEvent
from novel_signal.modules.universe.errors import (
    UniverseConflictError,
    UniverseNotFoundError,
    UniverseValidationError,
)
from novel_signal.modules.universe.models import (
    BattleCard,
    BattleCardItem,
    Competitor,
    CompetitorProduct,
    CompetitorProposal,
    Marketplace,
    ProposalStatus,
    TrackingTier,
)
from novel_signal.modules.universe.repository import UniverseRepository


def proposal_fingerprint(
    marketplace: Marketplace, marketplace_product_id: str,
    discovered_for_product_id: uuid.UUID | None = None,
) -> str:
    scope = f":{discovered_for_product_id}" if discovered_for_product_id else ""
    raw = f"{marketplace.value}:{marketplace_product_id.strip().upper()}{scope}"
    return hashlib.sha256(raw.encode()).hexdigest()


def score_candidate(
    *,
    appearances: int,
    best_rank: int | None,
    category_match: bool = False,
    sku_overlap: bool = False,
) -> tuple[float, dict[str, float]]:
    """Score 0-100: recurrence 40 + rank strength 30 + category 15 + overlap 15."""
    recurrence = min(max(appearances, 0) / 5.0, 1.0) * 40.0
    if best_rank and best_rank > 0:
        rank_strength = max(0.0, (11 - min(best_rank, 10)) / 10.0) * 30.0
    else:
        rank_strength = 0.0
    category_score = 15.0 if category_match else 0.0
    overlap_score = 15.0 if sku_overlap else 0.0
    total = round(recurrence + rank_strength + category_score + overlap_score, 2)
    return total, {
        "recurrence": round(recurrence, 2),
        "rank_strength": round(rank_strength, 2),
        "category_match": category_score,
        "sku_overlap": overlap_score,
    }


def _is_high_confidence(score: float) -> bool:
    return score >= 70.0


class ProposalService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = UniverseRepository(session)

    def list_proposals(
        self,
        *,
        status: ProposalStatus | None = None,
        limit: int = 50,
        offset: int = 0,
        product_id: uuid.UUID | None = None,
    ) -> tuple[list[CompetitorProposal], int]:
        statement = select(CompetitorProposal).order_by(
            CompetitorProposal.score.desc().nulls_last(),
            CompetitorProposal.created_at,
            CompetitorProposal.id,
        )
        count_statement = select(func.count()).select_from(CompetitorProposal)
        if status is not None:
            statement = statement.where(CompetitorProposal.status == status)
            count_statement = count_statement.where(CompetitorProposal.status == status)
        if product_id is not None:
            product_filter = CompetitorProposal.discovered_for_product_id == product_id
            statement = statement.where(product_filter)
            count_statement = count_statement.where(product_filter)
        items = list(self.session.scalars(statement.limit(limit).offset(offset)))
        total = self.session.scalar(count_statement) or 0
        return items, total

    def get_proposal(self, proposal_id: uuid.UUID) -> CompetitorProposal:
        proposal = self.session.get(CompetitorProposal, proposal_id)
        if proposal is None:
            raise UniverseNotFoundError("competitor proposal not found")
        return proposal

    def build_from_new_entrants(self, product_id: uuid.UUID | None = None) -> dict[str, int]:
        """Aggregate unmapped NewEntrantEvents into pending proposals (idempotent)."""
        statement = select(NewEntrantEvent).where(
                    NewEntrantEvent.product_id.is_(None),
                    NewEntrantEvent.competitor_product_id.is_(None),
                )
        if product_id is not None:
            keyword_ids = select(TrackingTarget.keyword_id).where(
                TrackingTarget.product_id == product_id,
                TrackingTarget.archived_at.is_(None),
                TrackingTarget.enabled.is_(True),
            )
            statement = statement.where(NewEntrantEvent.keyword_id.in_(keyword_ids))
        events = list(self.session.scalars(statement))
        grouped: dict[tuple[str, str], list[NewEntrantEvent]] = {}
        for event in events:
            marketplace_value = (
                event.marketplace.value
                if isinstance(event.marketplace, Marketplace)
                else str(event.marketplace)
            )
            key = (marketplace_value, event.marketplace_product_id.strip().upper())
            grouped.setdefault(key, []).append(event)
        created = 0
        updated = 0
        for (marketplace_value, asin), items in grouped.items():
            marketplace = Marketplace(marketplace_value)
            if self.repository.active_competitor_product_identity_exists(marketplace, asin):
                continue
            fingerprint = proposal_fingerprint(marketplace, asin, product_id)
            existing = self.session.scalar(
                select(CompetitorProposal).where(CompetitorProposal.fingerprint == fingerprint)
            )
            appearances = len(items)
            best_rank = min((item.rank for item in items if item.rank), default=None)
            brand = next((item.brand for item in items if item.brand), None)
            first = min(items, key=lambda item: item.first_seen_at)
            score, breakdown = score_candidate(
                appearances=appearances, best_rank=best_rank
            )
            device_values = [
                item.device_profile.value
                if hasattr(item.device_profile, "value")
                else str(item.device_profile)
                for item in items
            ]
            evidence: dict[str, Any] = {
                "appearances": appearances,
                "best_rank": best_rank,
                "brand": brand,
                "keyword_ids": sorted({str(item.keyword_id) for item in items}),
                "first_seen_capture_id": str(first.first_seen_capture_id),
                "first_seen_at": first.first_seen_at.isoformat(),
                "geo_device": sorted(
                    {
                        f"{item.geo_code}:{device}"
                        for item, device in zip(items, device_values, strict=True)
                    }
                ),
            }
            if existing is None:
                self.session.add(
                    CompetitorProposal(
                        fingerprint=fingerprint,
                        marketplace=marketplace,
                        marketplace_product_id=asin,
                        discovered_for_product_id=product_id,
                        brand=brand,
                        status=ProposalStatus.PENDING,
                        score=score,
                        score_breakdown=breakdown,
                        appearances=appearances,
                        best_rank=best_rank,
                        first_seen_keyword_id=first.keyword_id,
                        first_seen_at=first.first_seen_at,
                        evidence=evidence,
                    )
                )
                created += 1
            elif existing.status == ProposalStatus.PENDING:
                existing.appearances = appearances
                existing.best_rank = best_rank
                existing.score = score
                existing.score_breakdown = breakdown
                existing.evidence = evidence
                if brand and not existing.brand:
                    existing.brand = brand
                updated += 1
        self.session.commit()
        pending = (
            self.session.scalar(
                select(func.count())
                .select_from(CompetitorProposal)
                .where(CompetitorProposal.status == ProposalStatus.PENDING)
            )
            or 0
        )
        return {"created": created, "updated": updated, "pending": pending}

    def approve(
        self,
        proposal_id: uuid.UUID,
        *,
        competitor_id: uuid.UUID | None = None,
        competitor_name: str | None = None,
        battle_card_id: uuid.UUID | None = None,
        category: str | None = None,
        tracking_tier: TrackingTier = TrackingTier.T3,
    ) -> CompetitorProposal:
        proposal = self.get_proposal(proposal_id)
        if proposal.status != ProposalStatus.PENDING:
            raise UniverseValidationError("only pending proposals can be approved")
        if proposal.linked_competitor_product_id is not None:
            linked = self.session.get(
                CompetitorProduct, proposal.linked_competitor_product_id
            )
            if linked is not None and linked.archived_at is None:
                raise UniverseConflictError(
                    "proposal is already linked to an active competitor product"
                )
        existing_product = self.session.scalar(
            select(CompetitorProduct).where(
                CompetitorProduct.marketplace == proposal.marketplace,
                CompetitorProduct.marketplace_product_id == proposal.marketplace_product_id,
                CompetitorProduct.archived_at.is_(None),
            )
        )
        if existing_product is not None:
            product = existing_product
        else:
            product = None

        competitor: Competitor | None = None
        if product is not None:
            competitor = self.repository.get_competitor(product.competitor_id)
        else:
            if competitor_id is not None:
                competitor = self.repository.get_competitor(competitor_id)
                if competitor is None or competitor.archived_at is not None:
                    raise UniverseValidationError("an active competitor is required")
            else:
                fallback = f"Unidentified {proposal.marketplace_product_id}"
                name = (competitor_name or proposal.brand or fallback).strip()
                competitor = self.repository.get_active_competitor_by_name(name)
                if competitor is None:
                    competitor = Competitor(name=name)
                    self.session.add(competitor)
                    self.session.flush()

        if product is None:
            if competitor is None:
                raise UniverseValidationError("an active competitor is required")
            product = CompetitorProduct(
                competitor_id=competitor.id,
                name=proposal.title or proposal.marketplace_product_id,
                brand=proposal.brand or competitor.name,
                category=(category or "Unclassified").strip(),
                marketplace=proposal.marketplace,
                marketplace_product_id=proposal.marketplace_product_id,
                product_url=f"https://www.amazon.in/dp/{proposal.marketplace_product_id}",
                tracking_tier=tracking_tier,
            )
            self.session.add(product)
            self.session.flush()

        if battle_card_id is None and proposal.discovered_for_product_id is not None:
            card = self.session.scalar(
                select(BattleCard).where(
                    BattleCard.product_id == proposal.discovered_for_product_id,
                    BattleCard.archived_at.is_(None),
                ).order_by(BattleCard.created_at)
            )
            if card is None:
                card = BattleCard(
                    product_id=proposal.discovered_for_product_id,
                    name="Competitor comparison",
                    comparison_notes="Competitors approved from public Amazon search results.",
                )
                self.session.add(card)
                self.session.flush()
            battle_card_id = card.id

        if battle_card_id is not None:
            battle_card = self.repository.get_battle_card(battle_card_id)
            if battle_card is None or battle_card.archived_at is not None:
                raise UniverseValidationError("an active battle card is required")
            if (
                proposal.discovered_for_product_id is not None
                and battle_card.product_id != proposal.discovered_for_product_id
            ):
                raise UniverseValidationError(
                    "a product search candidate can only be added to that product's battle card"
                )
            if not self.repository.active_battle_card_item_exists(battle_card.id, product.id):
                self.session.add(
                    BattleCardItem(
                        battle_card_id=battle_card.id,
                        competitor_product_id=product.id,
                        same_category=True,
                    )
                )

        proposal.status = ProposalStatus.APPROVED
        proposal.linked_competitor_product_id = product.id
        proposal.decided_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(proposal)
        return proposal

    def reject(self, proposal_id: uuid.UUID) -> CompetitorProposal:
        proposal = self.get_proposal(proposal_id)
        if proposal.status != ProposalStatus.PENDING:
            raise UniverseValidationError("only pending proposals can be rejected")
        proposal.status = ProposalStatus.REJECTED
        proposal.decided_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(proposal)
        return proposal

    def archive(self, proposal_id: uuid.UUID) -> CompetitorProposal:
        proposal = self.get_proposal(proposal_id)
        if proposal.status == ProposalStatus.APPROVED:
            raise UniverseValidationError("approved proposals cannot be archived")
        proposal.status = ProposalStatus.ARCHIVED
        proposal.decided_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(proposal)
        return proposal

    def auto_approve_high_confidence(
        self, *, limit: int = 50
    ) -> list[CompetitorProposal]:
        """Activate only high-confidence matches; uncertain ones stay pending."""
        pending = list(
            self.session.scalars(
                select(CompetitorProposal)
                .where(CompetitorProposal.status == ProposalStatus.PENDING)
                .order_by(CompetitorProposal.score.desc().nulls_last())
                .limit(limit)
            )
        )
        approved: list[CompetitorProposal] = []
        for proposal in pending:
            if proposal.score is not None and _is_high_confidence(proposal.score):
                try:
                    approved.append(self.approve(proposal.id))
                except (UniverseConflictError, UniverseValidationError):
                    continue
        return approved

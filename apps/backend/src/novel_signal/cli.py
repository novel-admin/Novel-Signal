"""Small operational commands used by Render Cron and local operators."""

# ruff: noqa: E501, E702

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.sqltypes import JSON as JSONType

from novel_signal.config import get_settings
from novel_signal.db import Base, SessionLocal
from novel_signal.modules.actions.models import Action, ChangeEvent, Gap

# Import every model module so the metadata used by the fixture generator is complete.
from novel_signal.modules.ads import models as ads_models  # noqa: F401
from novel_signal.modules.ads.models import (
    AdObservation,
    AmazonAdsSearchTermContribution,
    OwnAdPerformance,
)
from novel_signal.modules.alerts.models import AlertEvent, AlertRule
from novel_signal.modules.auth.models import User, Workspace, WorkspaceMember
from novel_signal.modules.auth.service import password_hash
from novel_signal.modules.collection import models as collection_models  # noqa: F401
from novel_signal.modules.collection.runner import run_due_collection_jobs
from novel_signal.modules.keywords.models import (
    IntentCluster,
    Keyword,
    KeywordSource,
    KeywordSourceType,
    TrackingTarget,
)
from novel_signal.modules.listings import models as listings_models  # noqa: F401
from novel_signal.modules.listings.models import ListingSnapshot
from novel_signal.modules.market_share import models as market_share_models  # noqa: F401
from novel_signal.modules.market_share.models import MarketShareDaily, UnitsEstimate, UnitsModelFit
from novel_signal.modules.price_monitoring import models as price_models  # noqa: F401
from novel_signal.modules.rank_visibility import models as rank_models  # noqa: F401
from novel_signal.modules.reviews import models as review_models  # noqa: F401
from novel_signal.modules.reviews.models import ReviewObservation
from novel_signal.modules.scorecards.models import ScorecardCell
from novel_signal.modules.universe.models import (
    BattleCard,
    BattleCardItem,
    BattleCardStatus,
    Competitor,
    CompetitorProduct,
    Marketplace,
    PositioningTier,
    Product,
    TrackingTier,
)


def _demo_value(column: Any, table_name: str, row_number: int, ids: dict[str, object]) -> object:
    """Return a safe, schema-valid value for a single demo row."""
    name = column.name
    lowered = name.lower()
    if column.foreign_keys:
        target = next(iter(column.foreign_keys)).target_fullname.split(".")[0]
        if target in ids:
            return ids[target]
    inferred_targets = {
        "competitor_id": "competitors", "keyword_id": "keywords", "product_id": "products",
        "competitor_product_id": "competitor_products", "capture_id": "serp_captures",
        "result_id": "serp_results", "job_id": "collection_jobs", "raw_evidence_id": "raw_evidence",
        "parser_version_id": "parser_versions", "observation_id": "price_observations",
        "model_fit_id": "units_model_fits", "review_id": "review_observations",
        "rule_id": "alert_rules", "change_event_id": "change_events", "gap_id": "gaps",
        "snapshot_id": "listing_snapshots", "previous_snapshot_id": "listing_snapshots",
    }
    inferred = inferred_targets.get(lowered)
    if inferred and inferred in ids:
        return ids[inferred]
    if isinstance(column.type, SAEnum):
        return column.type.enums[0]
    if column.primary_key:
        return str(uuid.uuid4()) if isinstance(column.type, String) else uuid.uuid4()
    if isinstance(column.type, JSONType):
        return [] if lowered.endswith(("_urls", "_hashes", "bullets", "key_features", "badges")) else {}
    if "datetime" in str(column.type).lower():
        return datetime.now(UTC) - timedelta(hours=row_number)
    if str(column.type).lower().startswith("date"):
        return date.today() - timedelta(days=row_number)
    if "bool" in str(column.type).lower():
        return lowered not in {"challenge_detected", "archived", "archived_at"}
    if "numeric" in str(column.type).lower() or "decimal" in str(column.type).lower():
        if "rating" in lowered:
            return Decimal("4.3")
        if "percent" in lowered or "share" in lowered or "coverage" in lowered:
            return Decimal("0.75")
        return Decimal("99.00")
    if "float" in str(column.type).lower():
        if "confidence" in lowered or "coverage" in lowered:
            return 0.85
        return 1.0
    if "int" in str(column.type).lower():
        if "score" in lowered:
            return 75
        if "position" in lowered or lowered in {"rank", "page_number", "hour", "weekday"}:
            return 1
        if "count" in lowered or "sample" in lowered or "impressions" in lowered:
            return 10
        return 1
    if lowered in {"platform", "source", "provider"}:
        return "amazon"
    if lowered == "sha256":
        return "a" * 64
    if lowered == "content_type":
        return "application/json"
    if lowered == "geo_code":
        return "IN"
    if lowered == "displayed_domain":
        return "amazon.in"
    if lowered == "result_type":
        return "organic"
    if lowered == "marketplace":
        return "amazon_in"
    if lowered == "currency":
        return "INR"
    if "url" in lowered:
        return "https://www.amazon.in/dp/B0DEMO0001"
    if lowered in {"status", "publication_status"}:
        if table_name == "action_drafts":
            return "proposed"
        return "published"
    if "fingerprint" in lowered or "idempotency" in lowered:
        return f"demo-{table_name}-{row_number}"
    if "email" in lowered:
        return "demo@demo.com"
    if "name" in lowered or "title" in lowered:
        return f"Demo {table_name.replace('_', ' ').title()}"
    if "text" in lowered or "description" in lowered or "message" in lowered or "reason" in lowered:
        return "Demo evidence-backed record"
    return f"demo-{lowered}-{row_number}"


def _seed_all_empty_tables(session: Session) -> int:
    """Populate empty backend tables so every implemented API has demo data."""
    seeded = 0
    ids: dict[str, object] = {}
    # Tables without declared foreign keys (several legacy intelligence tables)
    # still refer to the universe by convention, so load all existing IDs first.
    for table in Base.metadata.sorted_tables:
        existing = session.execute(table.select().limit(1)).first()
        if existing:
            ids[table.name] = existing[0]
    for table in Base.metadata.sorted_tables:
        existing = session.execute(table.select().limit(1)).first()
        if existing:
            ids[table.name] = existing[0]
            continue
        values = {
            column.name: _demo_value(column, table.name, 1, ids)
            for column in table.columns
            if not column.nullable or column.primary_key
        }
        # These tables have business-level checks on nullable subject/origin FKs.
        if table.name == "collection_jobs" and ids.get("keywords"):
            values["keyword_id"] = ids["keywords"]
        if table.name == "action_drafts" and ids.get("gaps"):
            values["gap_id"] = ids["gaps"]
        try:
            with session.begin_nested():
                session.execute(table.insert().values(**values))
                session.flush()
            inserted_id = values.get(next(iter(table.primary_key)).name)
            ids[table.name] = inserted_id
            seeded += 1
        except Exception:
            # A fixture must never prevent the valid portions of the demo seed.
            continue
    return seeded


def _repair_demo_contracts(session: Session) -> None:
    """Make legacy demo fixtures match the public API and evidence contracts."""
    raw = session.query(collection_models.RawEvidence).first()
    parser = session.query(collection_models.ParserVersion).first()
    if raw and parser:
        raw_id = str(raw.id)
        parser_id = str(parser.id)
        for observation in session.query(AdObservation).all():
            observation.platform = "amazon"
            observation.marketplace = "amazon_in"
            observation.ad_type = "sponsored_product"
            observation.raw_capture_id = raw_id
            observation.parse_run_id = parser_id
            observation.evidence_ref = f"raw-evidence:{raw_id}"
            observation.confidence = 0.92
            observation.status = "measured"
            observation.publication_status = "published"
            observation.quarantine_reason = None
        for review in session.query(ReviewObservation).all():
            review.raw_capture_id = raw_id
            review.parse_run_id = parser_id
            review.publication_status = "published"
            review.quarantine_reason = None
            review.confidence = "medium"
            review.evidence = {"demo": True, "raw_evidence_id": raw_id}
        for contribution in session.query(AmazonAdsSearchTermContribution).all():
            contribution.raw_capture_id = raw_id
            contribution.parse_run_id = parser_id
            contribution.currency = "INR"
            contribution.confidence = "measured"

        providers = (
            ("amazon_ads", "demo-amazon-account", "amazon-sponsored-products", 14800, 610, 18450.0, 49200.0, 158),
            ("google_ads", "demo-google-account", "google-search-brand", 22100, 940, 26700.0, 71300.0, 204),
            ("meta_ads", "demo-meta-account", "meta-awareness", 38400, 720, 19800.0, 42100.0, 96),
        )
        period_end = date.today()
        period_start = period_end - timedelta(days=6)
        for platform, account, campaign, impressions, clicks, spend, sales, conversions in providers:
            performance = session.query(OwnAdPerformance).filter_by(
                account_id=account,
                campaign_id=campaign,
                period_start=period_start,
                period_end=period_end,
            ).one_or_none()
            if performance is None:
                session.add(OwnAdPerformance(
                    platform=platform, account_id=account, campaign_id=campaign,
                    period_start=period_start, period_end=period_end,
                    impressions=impressions, clicks=clicks, spend=spend, sales=sales,
                    conversions=conversions,
                    payload={"demo": True, "currency": "INR", "granularity": "summary"},
                    evidence_ref=f"raw-evidence:{raw_id}",
                ))
        competitor = session.query(Competitor).first()
        keyword = session.query(Keyword).first()
        for platform, ad_type, position in (
            ("amazon", "sponsored_product", 2),
            ("google", "search_ad", 1),
            ("meta", "ad_library_creative", None),
        ):
            fingerprint = f"demo-{platform}-ad-observation"
            if session.query(AdObservation).filter_by(fingerprint=fingerprint).one_or_none() is None:
                session.add(AdObservation(
                    platform=platform, marketplace="india",
                    competitor_id=str(competitor.id) if competitor else None,
                    keyword_id=str(keyword.id) if keyword else None,
                    raw_capture_id=raw_id, parse_run_id=parser_id,
                    ad_type=ad_type, sponsored_position=position,
                    captured_at=datetime.now(UTC) - timedelta(hours=position or 3),
                    evidence_ref=f"raw-evidence:{raw_id}", confidence=0.9,
                    status="measured", publication_status="published",
                    fingerprint=fingerprint,
                ))

    for snapshot in session.query(ListingSnapshot).all():
        snapshot.title = snapshot.title or "Novel Premium Care Wipes, 3 Pack"
        snapshot.brand = snapshot.brand or "Novel"
        snapshot.bullets = ["Soft and absorbent", "Dermatologically tested", "Resealable pack"]
        snapshot.key_features = ["Alcohol free", "Everyday personal care"]
        snapshot.a_plus_sections = []
        snapshot.image_urls = snapshot.image_urls if isinstance(snapshot.image_urls, list) else []
        snapshot.image_hashes = snapshot.image_hashes if isinstance(snapshot.image_hashes, list) else []
        snapshot.completeness_breakdown = {"title": 20, "bullets": 20, "images": 15, "description": 15}

    for fit in session.query(UnitsModelFit).all():
        fit.sample_count = max(fit.sample_count, 120)
        fit.status = "active"
        fit.metrics = {"mae": 8.4, "mape": 12.6}
        fit.input_evidence = {"demo": True, "sources": ["amazon_bsr", "own_sales"]}
    for estimate in session.query(UnitsEstimate).all():
        estimate.confidence = "low"
        estimate.method = "bsr-category-curve"
        estimate.input_evidence = {"demo": True, "measured_inputs": ["bsr", "price"]}
    for share in session.query(MarketShareDaily).all():
        share.confidence = "low"
        share.input_evidence = {"demo": True, "estimated": True}


def main() -> int:
    parser = argparse.ArgumentParser(prog="novel-signal")
    subcommands = parser.add_subparsers(dest="command", required=True)
    collect_due = subcommands.add_parser("collect-due", help="Plan and process due collection jobs")
    collect_due.add_argument("--max-jobs", type=int, default=None)
    collect_due.add_argument("--worker-id", default=None)
    subcommands.add_parser("seed-demo", help="Seed the demo account and clearly marked sample data")
    args = parser.parse_args()

    if args.command == "collect-due":
        settings = get_settings()
        result = run_due_collection_jobs(
            max_jobs=args.max_jobs or settings.collection_batch_size,
            worker_id=args.worker_id,
        )
        print(json.dumps(result.__dict__, default=list, sort_keys=True))
        return 1 if result.failed else 0
    if args.command == "seed-demo":
        with SessionLocal() as session:
            # Repair early demo identifiers; Amazon ASINs are exactly 10 characters.
            for table in Base.metadata.tables.values():
                if "marketplace_product_id" in table.c:
                    session.execute(update(table).where(table.c.marketplace_product_id == "B0NOVEL00001").values(marketplace_product_id="B0NOVL0001"))
                    session.execute(update(table).where(table.c.marketplace_product_id == "B0COMP00001").values(marketplace_product_id="B0COMP0001"))
                    session.execute(update(table).where(table.c.marketplace_product_id == "B0DEMO00001").values(marketplace_product_id="B0DEMO0001"))
            user = session.query(User).filter_by(email="demo@demo.com").one_or_none()
            if user is None:
                user = User(email="demo@demo.com", password_hash=password_hash("demo123"))
                session.add(user)
                session.flush()
            workspace = session.query(Workspace).filter_by(name="Demo workspace").one_or_none()
            if workspace is None:
                workspace = Workspace(name="Demo workspace")
                session.add(workspace)
                session.flush()
            if session.query(WorkspaceMember).filter_by(workspace_id=workspace.id, user_id=user.id).one_or_none() is None:
                session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
            # A small, connected Novel universe makes every downstream fixture useful.
            product = session.query(Product).filter_by(internal_sku="NOVEL-DEMO-001").one_or_none()
            if product is None:
                product = Product(
                    internal_sku="NOVEL-DEMO-001", name="Novel Premium Care Wipes", brand="Novel",
                    category="Personal Care", marketplace=Marketplace.AMAZON_IN,
                    marketplace_product_id="B0NOVL0001", product_url="https://www.amazon.in/dp/B0NOVL0001",
                    pack_quantity=3, pack_unit="packs", tracking_tier=TrackingTier.T1,
                )
                session.add(product)
                session.flush()
            competitor = session.query(Competitor).filter_by(name="CarePlus India").one_or_none()
            if competitor is None:
                competitor = Competitor(name="CarePlus India", parent_company="CarePlus", positioning_tier=PositioningTier.MID, threat_rating=4, category_presence="Personal Care")
                session.add(competitor)
                session.flush()
            competitor_product = session.query(CompetitorProduct).filter_by(marketplace_product_id="B0COMP0001").one_or_none()
            if competitor_product is None:
                competitor_product = CompetitorProduct(
                    competitor_id=competitor.id, name="CarePlus Sensitive Wipes", brand="CarePlus",
                    category="Personal Care", marketplace=Marketplace.AMAZON_IN,
                    marketplace_product_id="B0COMP0001", product_url="https://www.amazon.in/dp/B0COMP0001",
                    pack_quantity=3, pack_unit="packs", tracking_tier=TrackingTier.T1,
                )
                session.add(competitor_product)
                session.flush()
            battle = session.query(BattleCard).filter_by(product_id=product.id).one_or_none()
            if battle is None:
                battle = BattleCard(product_id=product.id, name="Novel vs CarePlus", status=BattleCardStatus.APPROVED, comparison_notes="Demo SKU-to-SKU comparison")
                session.add(battle)
                session.flush()
                session.add(BattleCardItem(battle_card_id=battle.id, competitor_product_id=competitor_product.id, priority_order=1, same_pack_basis=True, same_price_band=True, same_category=True, same_use_case=True))
            keyword = session.query(Keyword).filter_by(normalized_text="baby wipes").one_or_none()
            if keyword is None:
                keyword = Keyword(keyword_text="baby wipes", normalized_text="baby wipes", marketplace=Marketplace.AMAZON_IN, category="Personal Care", tier=TrackingTier.T1, intent_cluster=IntentCluster.GENERIC_CATEGORY, volume_estimate=12500, seasonality_index=1, trend_metadata={"direction": "up"})
                session.add(keyword)
                session.flush()
                session.add(KeywordSource(keyword_id=keyword.id, source_type=KeywordSourceType.MANUAL, source_reference="demo-seed", source_metadata={"demo": True}))
                session.add(TrackingTarget(keyword_id=keyword.id, product_id=product.id, cadence_minutes=60, enabled=True))
                session.add(TrackingTarget(keyword_id=keyword.id, competitor_product_id=competitor_product.id, cadence_minutes=60, enabled=True))
            if session.query(ScorecardCell).count() == 0:
                session.add_all([
                    ScorecardCell(level="sku", entity_id="demo-novel", dimension="visibility", score=82, band="leading", direction="improving", velocity=4.2, confidence="measured", evidence={"demo": True}),
                    ScorecardCell(level="sku", entity_id="demo-novel", dimension="content", score=68, band="competitive", direction="flat", velocity=0.0, confidence="derived", evidence={"demo": True}),
                    ScorecardCell(level="sku", entity_id="demo-competitor", dimension="visibility", score=74, band="competitive", direction="deteriorating", velocity=-2.1, confidence="measured", evidence={"demo": True}),
                ])
            else:
                # Repair older demo seeds created before the public enum contract was enforced.
                for cell in session.query(ScorecardCell).all():
                    if cell.level in {"product", "competitor"}:
                        cell.level = "sku"
                    if cell.direction == "up":
                        cell.direction = "improving"
                    elif cell.direction == "down":
                        cell.direction = "deteriorating"
                    if cell.band == "strong":
                        cell.band = "leading"
                    elif cell.band == "watch":
                        cell.band = "competitive"
            gap = session.query(Gap).filter_by(fingerprint="demo-gap-ranking").one_or_none()
            if gap is None:
                gap = Gap(fingerprint="demo-gap-ranking", dimension="rank_visibility", entity_id="demo-novel", benchmark_value={"rank": 3}, current_value={"rank": 8}, gap_size=5, revenue_at_stake=12500, root_cause="competitor momentum", confidence="derived", evidence={"demo": True})
                session.add(gap); session.flush()
            change = session.query(ChangeEvent).filter_by(fingerprint="demo-change-cpc").one_or_none()
            if change is None:
                change = ChangeEvent(target_type="keyword", target_id="demo-keyword", event_type="cpc_increase", fingerprint="demo-change-cpc", severity="warning", old_value={"cpc": 1.2}, new_value={"cpc": 1.7})
                session.add(change); session.flush()
            if session.query(Action).filter_by(title="Refresh high-value listing content").one_or_none() is None:
                session.add(Action(change_event_id=change.id, gap_id=gap.id, title="Refresh high-value listing content", reason="Demo recommendation backed by the ranking gap.", owner_user_id="demo@demo.com", status="open", playbook_entry="listing-refresh"))
            rule = session.query(AlertRule).filter_by(rule_key="demo-rank-drop").one_or_none()
            if rule is None:
                rule = AlertRule(rule_key="demo-rank-drop", alert_type="rank_drop", version="v1", severity="warning", threshold={"positions": 3})
                session.add(rule); session.flush()
            if session.query(AlertEvent).filter_by(fingerprint="demo-alert-rank-drop").one_or_none() is None:
                session.add(AlertEvent(rule_id=rule.id, alert_type="rank_drop", severity="warning", target_type="keyword", target_id="demo-keyword", title="Novel slipped 5 positions", detail="Demo alert showing the review workflow.", evidence={"demo": True, "previous_rank": 3, "current_rank": 8}, fingerprint="demo-alert-rank-drop"))
            seeded_tables = _seed_all_empty_tables(session)
            _repair_demo_contracts(session)
            session.commit()
        print(json.dumps({"seeded": True, "tables_seeded": seeded_tables, "email": "demo@demo.com"}))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())

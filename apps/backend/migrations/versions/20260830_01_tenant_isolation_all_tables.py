"""Tenant isolation for every tenant-owned table.

Revision ID: 20260830_01
Revises: 20260829_01

- Adds ``workspace_id VARCHAR(36)`` (nullable for backfill) plus a
  per-table index to all 49 tenant-owned tables that lack it.
  (``collection_jobs``/``raw_evidence`` already carry the column.)
- Backfills NULL ownership to the earliest workspace when one exists.
  Rows stay invisible under RLS until owned (fail closed).
- Enables PostgreSQL Row Level Security with a strict
  ``workspace_id = app.current_workspace_id`` policy (no NULL allowance)
  on all 51 tenant-owned tables, replacing the lenient collection/raw
  policies from 20260829_01.
- Deliberately excluded: ``users`` (identity keyed by supabase_user_id,
  reached only through membership-checked endpoints), ``workspaces`` /
  ``workspace_members`` (already protected), ``source_credentials`` (child
  isolated through its parent connection), ``parser_versions`` (global code
  metadata identical for every tenant), ``auth_audit_events`` (append-only
  audit that must never block, keeps its NULL-allowing policy).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_01"
down_revision: str = "20260829_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables gaining workspace_id in this migration.
NEW_COLUMNS = [
    "competitors",
    "products",
    "competitor_products",
    "battle_cards",
    "competitor_proposals",
    "battle_card_items",
    "keywords",
    "keyword_sources",
    "tracking_targets",
    "serp_captures",
    "serp_results",
    "google_serp_captures",
    "google_serp_results",
    "badge_events",
    "new_entrant_events",
    "ad_observations",
    "ad_presence_daily",
    "ad_daypart_profiles",
    "ad_creatives",
    "external_ad_records",
    "spend_estimates",
    "own_ad_performance",
    "amazon_ads_search_term_contributions",
    "listing_snapshots",
    "listing_change_events",
    "price_observations",
    "seller_offers",
    "price_change_events",
    "review_observations",
    "review_topics",
    "review_topic_trends",
    "units_model_fits",
    "units_estimates",
    "market_share_daily",
    "units_model_backtests",
    "scorecard_cells",
    "scorecard_history",
    "change_events",
    "actions",
    "action_status_history",
    "gaps",
    "action_impact",
    "action_drafts",
    "alert_rules",
    "alert_events",
    "collection_attempts",
    "collection_failures",
    "quarantine_records",
    "data_quality_checks",
]

# Every table under strict workspace RLS after this migration.
RLS_TABLES = NEW_COLUMNS + ["collection_jobs", "raw_evidence"]

# Pre-existing lenient policies replaced by strict ones.
LEGACY_POLICIES = {
    "collection_jobs": ["collection_jobs_isolation"],
    "raw_evidence": ["raw_evidence_isolation"],
}


def upgrade() -> None:
    for table in NEW_COLUMNS:
        op.add_column(table, sa.Column("workspace_id", sa.String(length=36), nullable=True))
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])

    bind = op.get_bind()
    has_workspace = bind.execute(sa.text("SELECT COUNT(*) FROM workspaces")).scalar()
    if has_workspace:
        for table in RLS_TABLES:
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET workspace_id = "
                    "(SELECT id FROM workspaces ORDER BY id LIMIT 1) "
                    "WHERE workspace_id IS NULL"
                )
            )

    if bind.dialect.name == "postgresql":
        for table in RLS_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            for legacy in LEGACY_POLICIES.get(table, []):
                op.execute(f"DROP POLICY IF EXISTS {legacy} ON {table};")
            op.execute(f"DROP POLICY IF EXISTS {table}_workspace_isolation ON {table};")
            op.execute(
                f"CREATE POLICY {table}_workspace_isolation ON {table} FOR ALL "
                "USING (workspace_id::TEXT = app_current_workspace_id()) "
                "WITH CHECK (workspace_id::TEXT = app_current_workspace_id());"
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in RLS_TABLES:
            op.execute(f"DROP POLICY IF EXISTS {table}_workspace_isolation ON {table};")
        # Restore the lenient collection/raw policies from 20260829_01.
        op.execute(
            "CREATE POLICY collection_jobs_isolation ON collection_jobs FOR ALL "
            "USING (workspace_id IS NULL OR workspace_id::TEXT = app_current_workspace_id()) "
            "WITH CHECK (workspace_id::TEXT = app_current_workspace_id());"
        )
        op.execute(
            "CREATE POLICY raw_evidence_isolation ON raw_evidence FOR ALL "
            "USING (workspace_id IS NULL OR workspace_id::TEXT = app_current_workspace_id()) "
            "WITH CHECK (workspace_id::TEXT = app_current_workspace_id());"
        )
        for table in NEW_COLUMNS:
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
    for table in NEW_COLUMNS:
        op.drop_index(f"ix_{table}_workspace_id", table_name=table)
        op.drop_column(table, "workspace_id")

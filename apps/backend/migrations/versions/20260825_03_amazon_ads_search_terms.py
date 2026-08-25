"""Add idempotent Amazon Ads search-term handoff records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20260825_03"
down_revision = "20260825_02"
branch_labels: str | Sequence[str] | None = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "amazon_ads_search_term_contributions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(120), nullable=False),
        sa.Column("campaign_id", sa.String(120), nullable=False),
        sa.Column("ad_group_id", sa.String(120)),
        sa.Column("search_term", sa.String(500), nullable=False),
        sa.Column("matched_keyword", sa.String(500)),
        sa.Column("match_type", sa.String(40)),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.Column("spend", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("orders", sa.Integer(), nullable=False),
        sa.Column("sales", sa.Float(), nullable=False),
        sa.Column("raw_capture_id", sa.String(36), nullable=False),
        sa.Column("parse_run_id", sa.String(36), nullable=False),
        sa.Column("report_id", sa.String(120), nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.UniqueConstraint("fingerprint", name="uq_amazon_ads_search_term_fingerprint"),
    )
    op.create_index(
        "ix_amazon_ads_search_term_period",
        "amazon_ads_search_term_contributions",
        ["period_start", "period_end"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_amazon_ads_search_term_period",
        table_name="amazon_ads_search_term_contributions",
    )
    op.drop_table("amazon_ads_search_term_contributions")

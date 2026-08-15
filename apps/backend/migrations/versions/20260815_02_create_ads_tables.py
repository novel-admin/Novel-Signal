"""Create S4 ad intelligence tables."""

import sqlalchemy as sa
from alembic import op

revision = "20260815_ads"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    def ident() -> sa.Column:
        return sa.Column("id", sa.String(36), primary_key=True)

    op.create_table(
        "ad_observations",
        ident(),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("marketplace", sa.String(40), nullable=False),
        sa.Column("competitor_id", sa.String(36)),
        sa.Column("product_id", sa.String(36)),
        sa.Column("keyword_id", sa.String(36)),
        sa.Column("capture_id", sa.String(36)),
        sa.Column("ad_type", sa.String(40), nullable=False),
        sa.Column("sponsored_position", sa.Integer),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_ref", sa.Text),
        sa.Column("confidence", sa.Float),
        sa.Column("status", sa.String(20), nullable=False, server_default="measured"),
        sa.Column("fingerprint", sa.String(255), nullable=False),
        sa.UniqueConstraint("fingerprint", name="uq_ad_observations_fingerprint"),
    )
    op.create_index(
        "ix_ad_observations_competitor_captured",
        "ad_observations",
        ["competitor_id", "captured_at"],
    )
    op.create_table(
        "ad_presence_daily",
        ident(),
        sa.Column("competitor_id", sa.String(36), nullable=False),
        sa.Column("keyword_id", sa.String(36), nullable=False),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("ad_days", sa.Integer, nullable=False, server_default="1"),
        sa.Column("observed_slots", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_slots", sa.Integer, nullable=False, server_default="0"),
        sa.Column("coverage", sa.Float),
        sa.Column("confidence", sa.Float),
        sa.Column("evidence_ref", sa.Text),
        sa.UniqueConstraint(
            "competitor_id", "keyword_id", "day", name="uq_ad_presence_daily_target"
        ),
    )
    op.create_table(
        "ad_daypart_profiles",
        ident(),
        sa.Column("competitor_id", sa.String(36), nullable=False),
        sa.Column("keyword_id", sa.String(36), nullable=False),
        sa.Column("hour", sa.Integer, nullable=False),
        sa.Column("weekday", sa.Integer, nullable=False),
        sa.Column("presence_rate", sa.Float, nullable=False),
        sa.Column("sample_size", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="derived"),
        sa.UniqueConstraint(
            "competitor_id", "keyword_id", "hour", "weekday", name="uq_ad_daypart_profile"
        ),
    )
    op.create_table(
        "ad_creatives",
        ident(),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("competitor_id", sa.String(36)),
        sa.Column("ad_type", sa.String(40), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("content", sa.JSON, nullable=False),
        sa.Column("evidence_ref", sa.Text),
        sa.UniqueConstraint("platform", "external_id", name="uq_ad_creatives_external"),
    )
    op.create_table(
        "external_ad_records",
        ident(),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("competitor_id", sa.String(36)),
        sa.Column("run_date", sa.Date, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("evidence_ref", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="measured"),
        sa.UniqueConstraint("source", "external_id", name="uq_external_ads_source_id"),
    )
    op.create_table(
        "spend_estimates",
        ident(),
        sa.Column("competitor_id", sa.String(36), nullable=False),
        sa.Column("keyword_id", sa.String(36)),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("low", sa.Float, nullable=False),
        sa.Column("expected", sa.Float, nullable=False),
        sa.Column("high", sa.Float, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("method", sa.String(120), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("input_coverage", sa.Float, nullable=False),
        sa.Column("backtest_ref", sa.String(255)),
    )
    op.create_table(
        "own_ad_performance",
        ident(),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("account_id", sa.String(120), nullable=False),
        sa.Column("campaign_id", sa.String(120)),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("impressions", sa.Integer),
        sa.Column("clicks", sa.Integer),
        sa.Column("spend", sa.Float),
        sa.Column("sales", sa.Float),
        sa.Column("conversions", sa.Integer),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("evidence_ref", sa.Text),
        sa.UniqueConstraint(
            "account_id",
            "campaign_id",
            "period_start",
            "period_end",
            name="uq_own_ad_performance_period",
        ),
    )


def downgrade() -> None:
    for table in (
        "own_ad_performance",
        "spend_estimates",
        "external_ad_records",
        "ad_creatives",
        "ad_daypart_profiles",
        "ad_presence_daily",
    ):
        op.drop_table(table)
    op.drop_index("ix_ad_observations_competitor_captured", table_name="ad_observations")
    op.drop_table("ad_observations")

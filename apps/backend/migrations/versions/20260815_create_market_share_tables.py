"""Create versioned units and market-share estimate tables."""

import sqlalchemy as sa
from alembic import op

revision = "20260815_market_share"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "units_model_fits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("marketplace", sa.String(80), nullable=False),
        sa.Column("category_node", sa.String(160), nullable=False),
        sa.Column("pack_size", sa.String(80)),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column("trained_from", sa.Date, nullable=False),
        sa.Column("trained_to", sa.Date, nullable=False),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column("metrics", sa.JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "platform", "marketplace", "category_node", "model_version",
            name="uq_units_model_fits_scope_version",
        ),
    )
    op.create_table(
        "units_estimates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_fit_id", sa.String(36), nullable=False),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("marketplace", sa.String(80), nullable=False),
        sa.Column("category_node", sa.String(160), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.String(120), nullable=False),
        sa.Column("brand_id", sa.String(120)),
        sa.Column("observed_on", sa.Date, nullable=False),
        sa.Column("bsr", sa.Integer),
        sa.Column("price", sa.Float),
        sa.Column("units_low", sa.Float, nullable=False),
        sa.Column("units_point", sa.Float, nullable=False),
        sa.Column("units_high", sa.Float, nullable=False),
        sa.Column("revenue_low", sa.Float, nullable=False),
        sa.Column("revenue_point", sa.Float, nullable=False),
        sa.Column("revenue_high", sa.Float, nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("input_coverage", sa.Float, nullable=False),
        sa.Column("method", sa.String(120), nullable=False),
        sa.Column("cross_check_units", sa.Float),
        sa.Column("divergence_warning", sa.Text),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "entity_id", "observed_on", "model_version", name="uq_units_estimate_identity"
        ),
    )
    op.create_table(
        "market_share_daily",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("marketplace", sa.String(80), nullable=False),
        sa.Column("category_node", sa.String(160), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.String(120), nullable=False),
        sa.Column("brand_id", sa.String(120)),
        sa.Column("observed_on", sa.Date, nullable=False),
        sa.Column("segment_key", sa.String(255), nullable=False, server_default="all"),
        sa.Column("units_low", sa.Float, nullable=False),
        sa.Column("units_point", sa.Float, nullable=False),
        sa.Column("units_high", sa.Float, nullable=False),
        sa.Column("share_low", sa.Float, nullable=False),
        sa.Column("share_point", sa.Float, nullable=False),
        sa.Column("share_high", sa.Float, nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("input_coverage", sa.Float, nullable=False),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column("divergence_warning", sa.Text),
        sa.UniqueConstraint(
            "entity_id", "observed_on", "segment_key", "model_version",
            name="uq_market_share_daily_identity",
        ),
    )
    op.create_table(
        "units_model_backtests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_fit_id", sa.String(36), nullable=False),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column("actual_units", sa.Float, nullable=False),
        sa.Column("predicted_units", sa.Float, nullable=False),
        sa.Column("mae", sa.Float, nullable=False),
        sa.Column("mape", sa.Float),
        sa.Column("metrics", sa.JSON, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("units_model_backtests")
    op.drop_table("market_share_daily")
    op.drop_table("units_estimates")
    op.drop_table("units_model_fits")

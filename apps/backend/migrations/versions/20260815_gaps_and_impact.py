"""Create gap and action impact tables."""

import sqlalchemy as sa
from alembic import op

revision = "20260815_gaps_impact"
down_revision = "20260815_scorecards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gaps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fingerprint", sa.String(255), nullable=False, unique=True),
        sa.Column("dimension", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("keyword_id", sa.String(36)),
        sa.Column("benchmark_value", sa.JSON()),
        sa.Column("current_value", sa.JSON()),
        sa.Column("gap_size", sa.Float()),
        sa.Column("revenue_at_stake", sa.Float()),
        sa.Column("root_cause", sa.String(120)),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_gaps_status_revenue", "gaps", ["status", "revenue_at_stake"])
    op.create_table(
        "action_impact",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "action_id",
            sa.String(36),
            sa.ForeignKey("actions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("days_after", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(80), nullable=False),
        sa.Column("baseline", sa.Float()),
        sa.Column("observed", sa.Float()),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column(
            "measured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("action_id", "days_after", name="uq_action_impact_day"),
    )


def downgrade() -> None:
    op.drop_table("action_impact")
    op.drop_index("ix_gaps_status_revenue", table_name="gaps")
    op.drop_table("gaps")

"""Add evidence-safe scorecards, gap actions, and S11 alerts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20260825_01"
down_revision = "20260818_03"
branch_labels: str | Sequence[str] | None = None
depends_on = None


def upgrade() -> None:
    op.alter_column("scorecard_cells", "score", existing_type=sa.Float(), nullable=True)
    op.alter_column("scorecard_history", "score", existing_type=sa.Float(), nullable=True)
    op.add_column("scorecard_cells", sa.Column("unknown_reason", sa.String(255)))
    op.add_column(
        "scorecard_cells",
        sa.Column("formula_version", sa.String(80), nullable=False, server_default="scorecard-v1"),
    )
    op.add_column(
        "scorecard_cells",
        sa.Column("freshness_state", sa.String(20), nullable=False, server_default="fresh"),
    )

    op.alter_column("actions", "change_event_id", existing_type=sa.String(36), nullable=True)
    op.add_column("actions", sa.Column("gap_id", sa.String(36)))
    op.add_column("actions", sa.Column("playbook_entry", sa.String(120)))
    op.create_foreign_key("fk_actions_gap_id_gaps", "actions", "gaps", ["gap_id"], ["id"])
    op.create_index("ix_actions_gap_status", "actions", ["gap_id", "status"])
    op.create_check_constraint(
        "action_origin_required", "actions", "change_event_id IS NOT NULL OR gap_id IS NOT NULL"
    )

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("rule_key", sa.String(120), nullable=False),
        sa.Column("alert_type", sa.String(80), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("threshold", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("rule_key", "version", name="uq_alert_rule_version"),
    )
    op.create_table(
        "alert_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("rule_id", sa.String(36), nullable=False),
        sa.Column("alert_type", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("target_type", sa.String(80), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("competitor_id", sa.String(36)),
        sa.Column("keyword_id", sa.String(36)),
        sa.Column("gap_id", sa.String(36)),
        sa.Column("action_id", sa.String(36)),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("fingerprint", sa.String(255), nullable=False),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["rule_id"], ["alert_rules.id"]),
        sa.ForeignKeyConstraint(["gap_id"], ["gaps.id"]),
        sa.ForeignKeyConstraint(["action_id"], ["actions.id"]),
        sa.UniqueConstraint("fingerprint", name="uq_alert_event_fingerprint"),
    )
    op.create_index(
        "ix_alert_events_status_severity_opened",
        "alert_events",
        ["status", "severity", "opened_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_alert_events_status_severity_opened", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_table("alert_rules")
    op.drop_constraint("action_origin_required", "actions", type_="check")
    op.drop_index("ix_actions_gap_status", table_name="actions")
    op.drop_constraint("fk_actions_gap_id_gaps", "actions", type_="foreignkey")
    op.drop_column("actions", "playbook_entry")
    op.drop_column("actions", "gap_id")
    op.alter_column("actions", "change_event_id", existing_type=sa.String(36), nullable=False)
    op.drop_column("scorecard_cells", "freshness_state")
    op.drop_column("scorecard_cells", "formula_version")
    op.drop_column("scorecard_cells", "unknown_reason")
    op.alter_column("scorecard_history", "score", existing_type=sa.Float(), nullable=False)
    op.alter_column("scorecard_cells", "score", existing_type=sa.Float(), nullable=False)

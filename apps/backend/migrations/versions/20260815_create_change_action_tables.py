"""Create Week 1 change and action tables."""

from alembic import op
import sqlalchemy as sa

revision = "20260815_actions"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "change_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("target_type", sa.String(80), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("old_observation_type", sa.String(80)),
        sa.Column("old_observation_id", sa.String(36)),
        sa.Column("new_observation_type", sa.String(80)),
        sa.Column("new_observation_id", sa.String(36)),
        sa.Column("field_name", sa.String(120)),
        sa.Column("old_value", sa.JSON),
        sa.Column("new_value", sa.JSON),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="info"),
        sa.Column("fingerprint", sa.String(255), nullable=False),
        sa.UniqueConstraint("fingerprint", name="uq_change_events_fingerprint"),
    )
    op.create_table(
        "actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("change_event_id", sa.String(36), sa.ForeignKey("change_events.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("owner_user_id", sa.String(120)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("outcome_note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_actions_status_created_at", "actions", ["status", "created_at"])
    op.create_table(
        "action_status_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("action_id", sa.String(36), sa.ForeignKey("actions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(20)),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("changed_by", sa.String(120)),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("note", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("action_status_history")
    op.drop_index("ix_actions_status_created_at", table_name="actions")
    op.drop_table("actions")
    op.drop_table("change_events")

"""Create evidence-constrained action drafts.

Revision ID: 20260826_02
Revises: 20260826_01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_02"
down_revision: str | None = "20260826_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "action_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("gap_id", sa.String(length=36), nullable=True),
        sa.Column("action_id", sa.String(length=36), nullable=True),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("recommended_steps", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("uncertainty_note", sa.Text(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("gap_id IS NOT NULL OR action_id IS NOT NULL", name="action_draft_origin_required"),
        sa.CheckConstraint(
            "status IN ('draft', 'accepted', 'rejected')", name="action_draft_status_valid"
        ),
        sa.ForeignKeyConstraint(["action_id"], ["actions.id"]),
        sa.ForeignKeyConstraint(["gap_id"], ["gaps.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("input_fingerprint", name="uq_action_drafts_input_fingerprint"),
    )
    op.create_index("ix_action_drafts_status_created_at", "action_drafts", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_action_drafts_status_created_at", table_name="action_drafts")
    op.drop_table("action_drafts")

"""Add competitor discovery proposal queue (PM Phase 4).

Revision ID: 20260828_01
Revises: 20260827_02
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_01"
down_revision: str = "20260827_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

proposal_status = postgresql.ENUM(
    "pending", "approved", "rejected", "archived", name="proposal_status", create_type=False
)
proposal_marketplace = postgresql.ENUM("amazon_in", name="marketplace", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    proposal_status.create(bind, checkfirst=True)
    op.create_table(
        "competitor_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fingerprint", sa.String(length=255), nullable=False),
        sa.Column("marketplace", proposal_marketplace, nullable=False),
        sa.Column("marketplace_product_id", sa.String(length=255), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("status", proposal_status, server_default="pending", nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("score_breakdown", sa.JSON(), nullable=True),
        sa.Column("appearances", sa.Integer(), server_default="1", nullable=False),
        sa.Column("best_rank", sa.Integer(), nullable=True),
        sa.Column(
            "first_seen_keyword_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column(
            "linked_competitor_product_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(trim(marketplace_product_id)) > 0",
            name="proposal_marketplace_product_id_not_blank",
        ),
        sa.CheckConstraint("appearances > 0", name="proposal_appearances_positive"),
        sa.CheckConstraint(
            "best_rank IS NULL OR best_rank > 0", name="proposal_best_rank_positive"
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 100)",
            name="proposal_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_keyword_id"], ["keywords.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["linked_competitor_product_id"],
            ["competitor_products.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_competitor_proposals"),
        sa.UniqueConstraint("fingerprint", name="uq_competitor_proposals_fingerprint"),
    )
    op.create_index(
        "ix_competitor_proposals_status_score",
        "competitor_proposals",
        ["status", "score"],
    )
    op.create_index(
        "ix_competitor_proposals_fingerprint", "competitor_proposals", ["fingerprint"]
    )
    op.create_index(
        "uq_competitor_proposals_active_identity",
        "competitor_proposals",
        ["marketplace", "marketplace_product_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_competitor_proposals_active_identity", table_name="competitor_proposals"
    )
    op.drop_index("ix_competitor_proposals_fingerprint", table_name="competitor_proposals")
    op.drop_index(
        "ix_competitor_proposals_status_score", table_name="competitor_proposals"
    )
    op.drop_table("competitor_proposals")
    bind = op.get_bind()
    proposal_status.drop(bind, checkfirst=True)

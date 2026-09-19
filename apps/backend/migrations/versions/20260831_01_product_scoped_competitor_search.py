"""Scope competitor proposals to the Novel product that found them."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_01"
down_revision: str | None = "20260830_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "competitor_proposals",
        sa.Column("discovered_for_product_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_competitor_proposals_discovered_for_product_id_products",
        "competitor_proposals", "products", ["discovered_for_product_id"], ["id"],
        ondelete="SET NULL",
    )
    op.drop_index("uq_competitor_proposals_active_identity", table_name="competitor_proposals")
    op.create_index(
        "uq_competitor_proposals_active_identity", "competitor_proposals",
        ["marketplace", "marketplace_product_id", "discovered_for_product_id"],
        unique=True, postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_competitor_proposals_active_identity", table_name="competitor_proposals")
    op.create_index(
        "uq_competitor_proposals_active_identity", "competitor_proposals",
        ["marketplace", "marketplace_product_id"], unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )
    op.drop_constraint(
        "fk_competitor_proposals_discovered_for_product_id_products",
        "competitor_proposals", type_="foreignkey",
    )
    op.drop_column("competitor_proposals", "discovered_for_product_id")

"""Enforce active competitor-product marketplace identity uniqueness.

Revision ID: 20260816_01
Revises: 20260815_01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260816_01"
down_revision: str | None = "20260815_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_competitor_products_active_identity", table_name="competitor_products")
    op.create_index(
        "uq_competitor_products_active_marketplace_identity",
        "competitor_products",
        ["marketplace", "marketplace_product_id"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL AND marketplace_product_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_competitor_products_active_marketplace_identity",
        table_name="competitor_products",
    )
    op.create_index(
        "uq_competitor_products_active_identity",
        "competitor_products",
        ["competitor_id", "marketplace", "marketplace_product_id"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL AND marketplace_product_id IS NOT NULL"),
    )

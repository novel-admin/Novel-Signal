"""Create the S1 universe domain tables.

Revision ID: 20260814_01
Revises:
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

positioning_tier = postgresql.ENUM(
    "premium", "mid", "value", "unknown", name="positioning_tier", create_type=False
)
tracking_tier = postgresql.ENUM("T1", "T2", "T3", name="tracking_tier", create_type=False)
marketplace = postgresql.ENUM("amazon_in", name="marketplace", create_type=False)
battle_card_status = postgresql.ENUM(
    "draft", "approved", name="battle_card_status", create_type=False
)


def timestamp_columns() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    bind = op.get_bind()
    positioning_tier.create(bind, checkfirst=True)
    tracking_tier.create(bind, checkfirst=True)
    marketplace.create(bind, checkfirst=True)
    battle_card_status.create(bind, checkfirst=True)

    op.create_table(
        "competitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("parent_company", sa.String(length=255), nullable=True),
        sa.Column("amazon_store_url", sa.String(length=2048), nullable=True),
        sa.Column("amazon_seller_id", sa.String(length=255), nullable=True),
        sa.Column("category_presence", sa.Text(), nullable=True),
        sa.Column(
            "positioning_tier", positioning_tier, server_default="unknown", nullable=False
        ),
        sa.Column("threat_rating", sa.SmallInteger(), nullable=True),
        sa.Column("analyst_owner", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        sa.CheckConstraint(
            "threat_rating IS NULL OR threat_rating BETWEEN 1 AND 5",
            name="threat_rating_range",
        ),
        sa.CheckConstraint(
            "amazon_store_url IS NULL OR length(trim(amazon_store_url)) > 0",
            name="amazon_store_url_not_blank",
        ),
        sa.CheckConstraint(
            "amazon_seller_id IS NULL OR length(trim(amazon_seller_id)) > 0",
            name="amazon_seller_id_not_blank",
        ),
        sa.CheckConstraint(
            "category_presence IS NULL OR length(trim(category_presence)) > 0",
            name="category_presence_not_blank",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_competitors"),
    )
    op.create_index(
        "uq_competitors_normalized_active_name",
        "competitors",
        [sa.text("lower(btrim(name))")],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("internal_sku", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=255), nullable=False),
        sa.Column("marketplace", marketplace, nullable=False),
        sa.Column("marketplace_product_id", sa.String(length=255), nullable=True),
        sa.Column("product_url", sa.String(length=2048), nullable=True),
        sa.Column("pack_quantity", sa.Integer(), nullable=True),
        sa.Column("pack_unit", sa.String(length=50), nullable=True),
        sa.Column("tracking_tier", tracking_tier, nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint(
            "length(trim(internal_sku)) > 0", name="internal_sku_not_blank"
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        sa.CheckConstraint("length(trim(brand)) > 0", name="brand_not_blank"),
        sa.CheckConstraint(
            "length(trim(category)) > 0", name="category_not_blank"
        ),
        sa.CheckConstraint(
            "marketplace_product_id IS NULL OR length(trim(marketplace_product_id)) > 0",
            name="marketplace_product_id_not_blank",
        ),
        sa.CheckConstraint(
            "pack_quantity IS NULL OR pack_quantity > 0",
            name="pack_quantity_positive",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
    )
    op.create_index("ix_products_archived_at", "products", ["archived_at"])
    op.create_index(
        "uq_products_active_internal_sku",
        "products",
        ["internal_sku"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "uq_products_active_marketplace_identity",
        "products",
        ["marketplace", "marketplace_product_id"],
        unique=True,
        postgresql_where=sa.text(
            "archived_at IS NULL AND marketplace_product_id IS NOT NULL"
        ),
    )
    op.create_index(
        "ix_products_marketplace_product_id",
        "products",
        ["marketplace", "marketplace_product_id"],
    )

    op.create_table(
        "competitor_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=255), nullable=False),
        sa.Column("marketplace", marketplace, nullable=False),
        sa.Column("marketplace_product_id", sa.String(length=255), nullable=True),
        sa.Column("product_url", sa.String(length=2048), nullable=True),
        sa.Column("pack_quantity", sa.Integer(), nullable=True),
        sa.Column("pack_unit", sa.String(length=50), nullable=True),
        sa.Column("tracking_tier", tracking_tier, nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint(
            "length(trim(name)) > 0", name="name_not_blank"
        ),
        sa.CheckConstraint(
            "length(trim(brand)) > 0", name="brand_not_blank"
        ),
        sa.CheckConstraint(
            "length(trim(category)) > 0", name="category_not_blank"
        ),
        sa.CheckConstraint(
            "marketplace_product_id IS NULL OR length(trim(marketplace_product_id)) > 0",
            name="marketplace_product_id_not_blank",
        ),
        sa.CheckConstraint(
            "pack_quantity IS NULL OR pack_quantity > 0",
            name="pack_quantity_positive",
        ),
        sa.ForeignKeyConstraint(
            ["competitor_id"],
            ["competitors.id"],
            name="fk_competitor_products_competitor_id_competitors",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_competitor_products"),
    )
    op.create_index(
        "ix_competitor_products_archived_at", "competitor_products", ["archived_at"]
    )
    op.create_index(
        "uq_competitor_products_active_identity",
        "competitor_products",
        ["competitor_id", "marketplace", "marketplace_product_id"],
        unique=True,
        postgresql_where=sa.text(
            "archived_at IS NULL AND marketplace_product_id IS NOT NULL"
        ),
    )
    op.create_index(
        "ix_competitor_products_competitor_id", "competitor_products", ["competitor_id"]
    )
    op.create_index(
        "ix_competitor_products_marketplace_product_id",
        "competitor_products",
        ["marketplace", "marketplace_product_id"],
    )

    op.create_table(
        "battle_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "status", battle_card_status, server_default="draft", nullable=False
        ),
        sa.Column("comparison_notes", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_battle_cards_product_id_products",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_battle_cards"),
    )
    op.create_index("ix_battle_cards_archived_at", "battle_cards", ["archived_at"])
    op.create_index("ix_battle_cards_product_id", "battle_cards", ["product_id"])

    op.create_table(
        "battle_card_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("battle_card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competitor_product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("priority_order", sa.Integer(), nullable=True),
        sa.Column("same_pack_basis", sa.Boolean(), nullable=False),
        sa.Column("same_price_band", sa.Boolean(), nullable=False),
        sa.Column("same_category", sa.Boolean(), nullable=False),
        sa.Column("same_use_case", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.CheckConstraint(
            "priority_order IS NULL OR priority_order >= 0",
            name="priority_order_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["battle_card_id"],
            ["battle_cards.id"],
            name="fk_battle_card_items_battle_card_id_battle_cards",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["competitor_product_id"],
            ["competitor_products.id"],
            name="fk_battle_card_items_competitor_product_id_competitor_products",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_battle_card_items"),
    )
    op.create_index(
        "ix_battle_card_items_archived_at", "battle_card_items", ["archived_at"]
    )
    op.create_index(
        "uq_battle_card_items_active_mapping",
        "battle_card_items",
        ["battle_card_id", "competitor_product_id"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "ix_battle_card_items_battle_card_id", "battle_card_items", ["battle_card_id"]
    )
    op.create_index(
        "ix_battle_card_items_competitor_product_id",
        "battle_card_items",
        ["competitor_product_id"],
    )


def downgrade() -> None:
    op.drop_table("battle_card_items")
    op.drop_table("battle_cards")
    op.drop_table("competitor_products")
    op.drop_table("products")
    op.drop_table("competitors")

    bind = op.get_bind()
    battle_card_status.drop(bind, checkfirst=True)
    marketplace.drop(bind, checkfirst=True)
    tracking_tier.drop(bind, checkfirst=True)
    positioning_tier.drop(bind, checkfirst=True)

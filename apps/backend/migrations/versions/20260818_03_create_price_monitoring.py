"""Create S6 price monitoring."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260818_03"
down_revision = "20260818_02"
branch_labels: str | Sequence[str] | None = None
depends_on = None
marketplace = postgresql.ENUM("amazon_in", name="marketplace", create_type=False)
availability = postgresql.ENUM(
    "available",
    "unavailable",
    "unknown",
    "limited",
    "out_of_stock",
    name="price_availability_status",
    create_type=False,
)
coupon_type = postgresql.ENUM(
    "absolute", "percentage", "uncertain", name="price_coupon_type", create_type=False
)
event_type = postgresql.ENUM(
    "price_increase",
    "price_decrease",
    "became_available",
    "became_unavailable",
    name="price_event_type",
    create_type=False,
)


def money(name: str) -> sa.Column[sa.Numeric]:
    return sa.Column(name, sa.Numeric(14, 2))


def upgrade() -> None:
    availability.create(op.get_bind(), checkfirst=True)
    coupon_type.create(op.get_bind(), checkfirst=True)
    event_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "price_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("marketplace", marketplace, nullable=False),
        sa.Column("marketplace_product_id", sa.String(255), nullable=False),
        sa.Column("product_id", sa.Uuid()),
        sa.Column("competitor_product_id", sa.Uuid()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("geo_code", sa.String(50)),
        sa.Column("device_profile", sa.String(50)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("availability_status", availability, nullable=False),
        money("primary_price"),
        money("list_price"),
        sa.Column("discount_percent", sa.Numeric(5, 2)),
        sa.Column("coupon_text", sa.Text()),
        money("coupon_value"),
        sa.Column("coupon_type", coupon_type),
        money("shipping_amount"),
        money("effective_price"),
        sa.Column("primary_seller_name", sa.String(500)),
        sa.Column("primary_seller_id", sa.String(255)),
        sa.Column("is_featured_offer", sa.Boolean()),
        sa.Column("seller_count", sa.Integer()),
        sa.Column("source_job_id", sa.Uuid()),
        sa.Column("parser_version", sa.String(100)),
        sa.Column("source_url", sa.String(2048)),
        sa.Column("ingestion_key", sa.String(255)),
        sa.Column("provider", sa.String(100)),
        sa.Column("source_metadata", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(trim(marketplace_product_id)) > 0", name="marketplace_product_id_not_blank"
        ),
        sa.CheckConstraint("length(trim(currency)) > 0", name="currency_not_blank"),
        sa.CheckConstraint(
            "NOT (product_id IS NOT NULL AND competitor_product_id IS NOT NULL)",
            name="single_product_mapping",
        ),
        sa.CheckConstraint(
            "primary_price IS NULL OR primary_price >= 0", name="primary_price_nonnegative"
        ),
        sa.CheckConstraint("list_price IS NULL OR list_price >= 0", name="list_price_nonnegative"),
        sa.CheckConstraint(
            "shipping_amount IS NULL OR shipping_amount >= 0", name="shipping_nonnegative"
        ),
        sa.CheckConstraint(
            "coupon_value IS NULL OR coupon_value >= 0", name="coupon_value_nonnegative"
        ),
        sa.CheckConstraint(
            "effective_price IS NULL OR effective_price >= 0", name="effective_price_nonnegative"
        ),
        sa.CheckConstraint(
            "discount_percent IS NULL OR discount_percent BETWEEN 0 AND 100",
            name="discount_percent_range",
        ),
        sa.CheckConstraint(
            "seller_count IS NULL OR seller_count >= 0", name="seller_count_nonnegative"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["competitor_product_id"], ["competitor_products.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["source_job_id"], ["collection_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ingestion_key", name="uq_price_observations_ingestion_key"),
    )
    op.create_index(
        "ix_price_observations_identity_observed",
        "price_observations",
        ["marketplace", "marketplace_product_id", "geo_code", "observed_at"],
    )
    op.create_index(
        "ix_price_observations_product_observed",
        "price_observations",
        ["product_id", "geo_code", "observed_at"],
    )
    op.create_index(
        "ix_price_observations_competitor_observed",
        "price_observations",
        ["competitor_product_id", "geo_code", "observed_at"],
    )
    op.create_table(
        "seller_offers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=False),
        sa.Column("seller_name", sa.String(500), nullable=False),
        sa.Column("seller_id", sa.String(255)),
        money("offer_price"),
        money("list_price"),
        money("shipping_amount"),
        sa.Column("coupon_text", sa.Text()),
        money("coupon_value"),
        money("effective_price"),
        sa.Column("availability_status", availability, nullable=False),
        sa.Column("fulfillment_type", sa.String(100)),
        sa.Column("is_featured_offer", sa.Boolean()),
        sa.Column("prime_eligible", sa.Boolean()),
        sa.Column("offer_metadata", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(trim(seller_name)) > 0", name="seller_name_not_blank"),
        sa.CheckConstraint(
            "offer_price IS NULL OR offer_price >= 0", name="offer_price_nonnegative"
        ),
        sa.CheckConstraint("list_price IS NULL OR list_price >= 0", name="list_price_nonnegative"),
        sa.CheckConstraint(
            "shipping_amount IS NULL OR shipping_amount >= 0", name="shipping_nonnegative"
        ),
        sa.CheckConstraint(
            "coupon_value IS NULL OR coupon_value >= 0", name="coupon_value_nonnegative"
        ),
        sa.CheckConstraint(
            "effective_price IS NULL OR effective_price >= 0", name="effective_price_nonnegative"
        ),
        sa.ForeignKeyConstraint(["observation_id"], ["price_observations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "observation_id",
            "seller_name",
            "seller_id",
            name="uq_seller_offers_observation_identity",
        ),
    )
    op.create_index("ix_seller_offers_observation", "seller_offers", ["observation_id"])
    op.create_table(
        "price_change_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=False),
        sa.Column("previous_observation_id", sa.Uuid()),
        sa.Column("marketplace", marketplace, nullable=False),
        sa.Column("marketplace_product_id", sa.String(255), nullable=False),
        sa.Column("product_id", sa.Uuid()),
        sa.Column("competitor_product_id", sa.Uuid()),
        sa.Column("event_type", event_type, nullable=False),
        money("previous_price"),
        money("new_price"),
        money("absolute_change"),
        sa.Column("percent_change", sa.Numeric(9, 2)),
        sa.Column("geo_code", sa.String(50)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["observation_id"], ["price_observations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["previous_observation_id"], ["price_observations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["competitor_product_id"], ["competitor_products.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "observation_id", "event_type", name="uq_price_events_observation_type"
        ),
    )
    op.create_index(
        "ix_price_events_identity_observed",
        "price_change_events",
        ["marketplace_product_id", "geo_code", "observed_at"],
    )
    op.create_index(
        "ix_price_events_product_observed", "price_change_events", ["product_id", "observed_at"]
    )


def downgrade() -> None:
    op.drop_table("price_change_events")
    op.drop_table("seller_offers")
    op.drop_table("price_observations")
    event_type.drop(op.get_bind(), checkfirst=True)
    coupon_type.drop(op.get_bind(), checkfirst=True)
    availability.drop(op.get_bind(), checkfirst=True)

"""Create S3 rank and visibility tables and join current migration heads.

Revision ID: 20260818_01
Revises: 20260816_01, 20260816_lineage_publication
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_01"
down_revision: tuple[str, ...] = ("20260816_01", "20260816_lineage_publication")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

device_profile = postgresql.ENUM("desktop", "mobile", name="device_profile", create_type=False)
placement_type = postgresql.ENUM(
    "organic",
    "sponsored_product",
    "sponsored_brand",
    "sponsored_brand_video",
    "sponsored_display",
    "editorial_or_deal",
    name="serp_placement_type",
    create_type=False,
)
badge_type = postgresql.ENUM(
    "best_seller",
    "amazons_choice",
    "deal",
    "limited_time_deal",
    "new_arrival",
    "sponsored",
    name="badge_type",
    create_type=False,
)
badge_event_type = postgresql.ENUM("acquired", "lost", name="badge_event_type", create_type=False)
marketplace = postgresql.ENUM("amazon_in", name="marketplace", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    device_profile.create(bind, checkfirst=True)
    placement_type.create(bind, checkfirst=True)
    badge_type.create(bind, checkfirst=True)
    badge_event_type.create(bind, checkfirst=True)
    op.create_table(
        "serp_captures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("keyword_id", sa.Uuid(), nullable=False),
        sa.Column("marketplace", marketplace, nullable=False),
        sa.Column("geo_code", sa.String(50), nullable=False),
        sa.Column("device_profile", device_profile, nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("source_job_id", sa.String(255)),
        sa.Column("parser_version", sa.String(100)),
        sa.Column("ingestion_key", sa.String(255)),
        sa.Column("capture_metadata", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(trim(geo_code)) > 0", name="geo_code_not_blank"),
        sa.CheckConstraint("page_count >= 0", name="page_count_nonnegative"),
        sa.CheckConstraint("result_count >= 0", name="result_count_nonnegative"),
        sa.ForeignKeyConstraint(["keyword_id"], ["keywords.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ingestion_key", name="uq_serp_captures_ingestion_key"),
    )
    op.create_index(
        "ix_serp_captures_keyword_captured", "serp_captures", ["keyword_id", "captured_at"]
    )
    op.create_index(
        "ix_serp_captures_marketplace_captured", "serp_captures", ["marketplace", "captured_at"]
    )
    op.create_index(
        "ix_serp_captures_context_captured",
        "serp_captures",
        ["keyword_id", "marketplace", "geo_code", "device_profile", "captured_at"],
    )
    op.create_table(
        "serp_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("capture_id", sa.Uuid(), nullable=False),
        sa.Column("absolute_position", sa.Integer(), nullable=False),
        sa.Column("within_type_position", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("marketplace_product_id", sa.String(255), nullable=False),
        sa.Column("product_id", sa.Uuid()),
        sa.Column("competitor_product_id", sa.Uuid()),
        sa.Column("brand", sa.String(255)),
        sa.Column("placement_type", placement_type, nullable=False),
        sa.Column("badges", sa.JSON(), nullable=False),
        sa.Column("amazons_choice_term", sa.String(500)),
        sa.Column("displayed_price", sa.Numeric(12, 2)),
        sa.Column("mrp", sa.Numeric(12, 2)),
        sa.Column("discount_percent", sa.Numeric(5, 2)),
        sa.Column("coupon", sa.String(500)),
        sa.Column("delivery_promise", sa.String(500)),
        sa.Column("rating", sa.Numeric(3, 2)),
        sa.Column("review_count", sa.Integer()),
        sa.Column("thumbnail_hash", sa.String(255)),
        sa.Column("result_metadata", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("absolute_position > 0", name="absolute_position_positive"),
        sa.CheckConstraint("within_type_position > 0", name="within_type_position_positive"),
        sa.CheckConstraint("page_number > 0", name="page_number_positive"),
        sa.CheckConstraint(
            "length(trim(marketplace_product_id)) > 0",
            name="marketplace_product_id_not_blank",
        ),
        sa.CheckConstraint(
            "displayed_price IS NULL OR displayed_price >= 0",
            name="price_nonnegative",
        ),
        sa.CheckConstraint("mrp IS NULL OR mrp >= 0", name="mrp_nonnegative"),
        sa.CheckConstraint(
            "discount_percent IS NULL OR discount_percent BETWEEN 0 AND 100",
            name="discount_percent_range",
        ),
        sa.CheckConstraint("rating IS NULL OR rating BETWEEN 0 AND 5", name="rating_range"),
        sa.CheckConstraint(
            "review_count IS NULL OR review_count >= 0",
            name="review_count_nonnegative",
        ),
        sa.CheckConstraint(
            "NOT (product_id IS NOT NULL AND competitor_product_id IS NOT NULL)",
            name="at_most_one_product_mapping",
        ),
        sa.ForeignKeyConstraint(["capture_id"], ["serp_captures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["competitor_product_id"], ["competitor_products.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "capture_id", "absolute_position", name="uq_serp_results_capture_position"
        ),
    )
    for name, columns in (
        ("ix_serp_results_capture_id", ["capture_id"]),
        ("ix_serp_results_marketplace_product_id", ["marketplace_product_id"]),
        ("ix_serp_results_product_id", ["product_id"]),
        ("ix_serp_results_competitor_product_id", ["competitor_product_id"]),
    ):
        op.create_index(name, "serp_results", columns)
    op.create_table(
        "badge_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("keyword_id", sa.Uuid(), nullable=False),
        sa.Column("capture_id", sa.Uuid(), nullable=False),
        sa.Column("result_id", sa.Uuid(), nullable=False),
        sa.Column("marketplace_product_id", sa.String(255), nullable=False),
        sa.Column("product_id", sa.Uuid()),
        sa.Column("competitor_product_id", sa.Uuid()),
        sa.Column("brand", sa.String(255)),
        sa.Column("badge_type", badge_type, nullable=False),
        sa.Column("event_type", badge_event_type, nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["keyword_id"], ["keywords.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["capture_id"], ["serp_captures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["result_id"], ["serp_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["competitor_product_id"], ["competitor_products.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "capture_id",
            "result_id",
            "badge_type",
            "event_type",
            name="uq_badge_events_observation",
        ),
    )
    op.create_index(
        "ix_badge_events_keyword_observed", "badge_events", ["keyword_id", "observed_at"]
    )
    op.create_index(
        "ix_badge_events_marketplace_product_id", "badge_events", ["marketplace_product_id"]
    )
    op.create_table(
        "new_entrant_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("keyword_id", sa.Uuid(), nullable=False),
        sa.Column("marketplace", marketplace, nullable=False),
        sa.Column("marketplace_product_id", sa.String(255), nullable=False),
        sa.Column("product_id", sa.Uuid()),
        sa.Column("competitor_product_id", sa.Uuid()),
        sa.Column("first_seen_capture_id", sa.Uuid(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("brand", sa.String(255)),
        sa.Column("geo_code", sa.String(50), nullable=False),
        sa.Column("device_profile", device_profile, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["keyword_id"], ["keywords.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["competitor_product_id"], ["competitor_products.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_capture_id"], ["serp_captures.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "keyword_id",
            "marketplace",
            "marketplace_product_id",
            "geo_code",
            "device_profile",
            name="uq_new_entrant_events_context_identity",
        ),
    )
    op.create_index(
        "ix_new_entrant_events_keyword_first_seen",
        "new_entrant_events",
        ["keyword_id", "first_seen_at"],
    )


def downgrade() -> None:
    op.drop_table("new_entrant_events")
    op.drop_table("badge_events")
    op.drop_table("serp_results")
    op.drop_table("serp_captures")
    bind = op.get_bind()
    badge_event_type.drop(bind, checkfirst=True)
    badge_type.drop(bind, checkfirst=True)
    placement_type.drop(bind, checkfirst=True)
    device_profile.drop(bind, checkfirst=True)

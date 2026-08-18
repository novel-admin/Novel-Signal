"""Create S5 listing intelligence and merge S3/S12 heads."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260818_02"
down_revision = ("20260816_02", "20260818_01")
branch_labels: str | Sequence[str] | None = None
depends_on = None
marketplace = postgresql.ENUM("amazon_in", name="marketplace", create_type=False)
change_type = postgresql.ENUM(
    "added", "removed", "modified", name="listing_change_type", create_type=False
)


def upgrade() -> None:
    change_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "listing_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("marketplace", marketplace, nullable=False),
        sa.Column("marketplace_product_id", sa.String(255), nullable=False),
        sa.Column("product_id", sa.Uuid()),
        sa.Column("competitor_product_id", sa.Uuid()),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("geo_code", sa.String(50)),
        sa.Column("device_profile", sa.String(30)),
        sa.Column("source_job_id", sa.Uuid()),
        sa.Column("parser_version", sa.String(100)),
        sa.Column("ingestion_key", sa.String(255)),
        sa.Column("source_url", sa.String(2048)),
        sa.Column("title", sa.Text()),
        sa.Column("brand", sa.String(255)),
        sa.Column("category_path", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("bullets", sa.JSON(), nullable=False),
        sa.Column("key_features", sa.JSON(), nullable=False),
        sa.Column("a_plus_present", sa.Boolean(), nullable=False),
        sa.Column("a_plus_sections", sa.JSON(), nullable=False),
        sa.Column("image_urls", sa.JSON(), nullable=False),
        sa.Column("image_hashes", sa.JSON(), nullable=False),
        sa.Column("image_count", sa.Integer(), nullable=False),
        sa.Column("video_present", sa.Boolean(), nullable=False),
        sa.Column("video_count", sa.Integer(), nullable=False),
        sa.Column("variation_count", sa.Integer()),
        sa.Column("variation_metadata", sa.JSON()),
        sa.Column("storefront_text", sa.Text()),
        sa.Column("content_metadata", sa.JSON()),
        sa.Column("completeness_score", sa.Integer(), nullable=False),
        sa.Column("completeness_breakdown", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(trim(marketplace_product_id)) > 0", name="marketplace_product_id_not_blank"
        ),
        sa.CheckConstraint(
            "NOT (product_id IS NOT NULL AND competitor_product_id IS NOT NULL)",
            name="single_product_mapping",
        ),
        sa.CheckConstraint("image_count >= 0", name="image_count_nonnegative"),
        sa.CheckConstraint("video_count >= 0", name="video_count_nonnegative"),
        sa.CheckConstraint(
            "variation_count IS NULL OR variation_count >= 0", name="variation_count_nonnegative"
        ),
        sa.CheckConstraint("completeness_score BETWEEN 0 AND 100", name="completeness_score_range"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["competitor_product_id"], ["competitor_products.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["source_job_id"], ["collection_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ingestion_key", name="uq_listing_snapshots_ingestion_key"),
    )
    op.create_index(
        "ix_listing_snapshots_identity_captured",
        "listing_snapshots",
        ["marketplace", "marketplace_product_id", "captured_at"],
    )
    op.create_index(
        "ix_listing_snapshots_product_captured", "listing_snapshots", ["product_id", "captured_at"]
    )
    op.create_index(
        "ix_listing_snapshots_competitor_captured",
        "listing_snapshots",
        ["competitor_product_id", "captured_at"],
    )
    op.create_table(
        "listing_change_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("previous_snapshot_id", sa.Uuid()),
        sa.Column("marketplace", marketplace, nullable=False),
        sa.Column("marketplace_product_id", sa.String(255), nullable=False),
        sa.Column("product_id", sa.Uuid()),
        sa.Column("competitor_product_id", sa.Uuid()),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("change_type", change_type, nullable=False),
        sa.Column("old_value", sa.JSON()),
        sa.Column("new_value", sa.JSON()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["snapshot_id"], ["listing_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["previous_snapshot_id"], ["listing_snapshots.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["competitor_product_id"], ["competitor_products.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "snapshot_id",
            "field_name",
            "change_type",
            name="uq_listing_change_events_snapshot_field_type",
        ),
    )
    op.create_index(
        "ix_listing_change_events_identity_observed",
        "listing_change_events",
        ["marketplace_product_id", "observed_at"],
    )
    op.create_index(
        "ix_listing_change_events_product_observed",
        "listing_change_events",
        ["product_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_table("listing_change_events")
    op.drop_table("listing_snapshots")
    change_type.drop(op.get_bind(), checkfirst=True)

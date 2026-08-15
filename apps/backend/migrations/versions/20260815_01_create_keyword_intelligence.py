"""Create S2 keyword intelligence tables.

Revision ID: 20260815_01
Revises: 20260814_01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_01"
down_revision: str | None = "20260814_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

marketplace = postgresql.ENUM("amazon_in", name="marketplace", create_type=False)
tracking_tier = postgresql.ENUM("T1", "T2", "T3", name="tracking_tier", create_type=False)
tracking_status = postgresql.ENUM(
    "active", "paused", name="keyword_tracking_status", create_type=False
)
intent_cluster = postgresql.ENUM(
    "generic_category",
    "attribute_long_tail",
    "problem_benefit",
    "own_brand",
    "competitor_brand",
    "adjacent",
    "unclassified",
    name="keyword_intent_cluster",
    create_type=False,
)
source_type = postgresql.ENUM(
    "brand_analytics",
    "amazon_ads",
    "autocomplete",
    "reverse_asin",
    "google_keyword_planner",
    "search_console",
    "review_mining",
    "regional_variant",
    "manual",
    name="keyword_source_type",
    create_type=False,
)


def timestamps() -> list[sa.Column]:
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
        sa.Column("archived_at", sa.DateTime(timezone=True)),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    tracking_status.create(bind, checkfirst=True)
    intent_cluster.create(bind, checkfirst=True)
    source_type.create(bind, checkfirst=True)
    op.create_table(
        "keywords",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keyword_text", sa.String(500), nullable=False),
        sa.Column("normalized_text", sa.String(500), nullable=False),
        sa.Column("marketplace", marketplace, nullable=False),
        sa.Column("category", sa.String(255)),
        sa.Column("tier", tracking_tier, nullable=False),
        sa.Column("tracking_status", tracking_status, server_default="active", nullable=False),
        sa.Column("intent_cluster", intent_cluster, server_default="unclassified", nullable=False),
        sa.Column("volume_estimate", sa.Integer()),
        sa.Column("trend_metadata", sa.JSON()),
        sa.Column("seasonality_index", sa.Integer()),
        sa.Column("notes", sa.Text()),
        *timestamps(),
        sa.CheckConstraint("length(trim(keyword_text)) > 0", name="keyword_text_not_blank"),
        sa.CheckConstraint("length(trim(normalized_text)) > 0", name="normalized_text_not_blank"),
        sa.CheckConstraint(
            "volume_estimate IS NULL OR volume_estimate >= 0", name="volume_estimate_nonnegative"
        ),
        sa.CheckConstraint(
            "seasonality_index IS NULL OR seasonality_index >= 0",
            name="seasonality_index_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_keywords"),
    )
    op.create_index("ix_keywords_archived_at", "keywords", ["archived_at"])
    op.create_index(
        "ix_keywords_filters",
        "keywords",
        ["marketplace", "tier", "tracking_status", "intent_cluster"],
    )
    op.create_index(
        "uq_keywords_active_identity",
        "keywords",
        ["marketplace", "normalized_text"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_table(
        "keyword_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("source_reference", sa.String(500), server_default="", nullable=False),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_metadata", sa.JSON()),
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
        sa.ForeignKeyConstraint(
            ["keyword_id"],
            ["keywords.id"],
            ondelete="CASCADE",
            name="fk_keyword_sources_keyword_id_keywords",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_keyword_sources"),
        sa.UniqueConstraint(
            "keyword_id", "source_type", "source_reference", name="uq_keyword_sources_identity"
        ),
    )
    op.create_index("ix_keyword_sources_keyword_id", "keyword_sources", ["keyword_id"])
    op.create_index("ix_keyword_sources_source_type", "keyword_sources", ["source_type"])
    op.create_table(
        "tracking_targets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True)),
        sa.Column("competitor_product_id", postgresql.UUID(as_uuid=True)),
        sa.Column("cadence_minutes", sa.Integer(), server_default="240", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "(product_id IS NOT NULL) <> (competitor_product_id IS NOT NULL)",
            name="exactly_one_target",
        ),
        sa.CheckConstraint("cadence_minutes > 0", name="cadence_positive"),
        sa.ForeignKeyConstraint(
            ["keyword_id"],
            ["keywords.id"],
            ondelete="RESTRICT",
            name="fk_tracking_targets_keyword_id_keywords",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="RESTRICT",
            name="fk_tracking_targets_product_id_products",
        ),
        sa.ForeignKeyConstraint(
            ["competitor_product_id"],
            ["competitor_products.id"],
            ondelete="RESTRICT",
            name="fk_tracking_targets_competitor_product_id_competitor_products",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tracking_targets"),
    )
    for column in ("keyword_id", "product_id", "competitor_product_id", "archived_at"):
        op.create_index(f"ix_tracking_targets_{column}", "tracking_targets", [column])
    op.create_index(
        "uq_tracking_targets_active_product",
        "tracking_targets",
        ["keyword_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL AND product_id IS NOT NULL"),
    )
    op.create_index(
        "uq_tracking_targets_active_competitor_product",
        "tracking_targets",
        ["keyword_id", "competitor_product_id"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL AND competitor_product_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("tracking_targets")
    op.drop_table("keyword_sources")
    op.drop_table("keywords")
    bind = op.get_bind()
    source_type.drop(bind, checkfirst=True)
    intent_cluster.drop(bind, checkfirst=True)
    tracking_status.drop(bind, checkfirst=True)

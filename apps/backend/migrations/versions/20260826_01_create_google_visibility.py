"""Create Google organic visibility capture history.

Revision ID: 20260826_01
Revises: 20260825_03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260826_01"
down_revision: str | None = "20260825_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

device_profile = postgresql.ENUM("desktop", "mobile", name="device_profile", create_type=False)


def upgrade() -> None:
    op.create_table(
        "google_serp_captures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("keyword_id", sa.Uuid(), nullable=False),
        sa.Column("geo_code", sa.String(50), nullable=False),
        sa.Column("device_profile", device_profile, nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_job_id", sa.Uuid(), nullable=False),
        sa.Column("raw_evidence_id", sa.Uuid(), nullable=False),
        sa.Column("parser_version_id", sa.Uuid(), nullable=False),
        sa.Column("parser_version", sa.String(100), nullable=False),
        sa.Column("ingestion_key", sa.String(255), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("capture_metadata", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(trim(geo_code)) > 0", name="geo_code_not_blank"),
        sa.CheckConstraint("page_number > 0", name="page_number_positive"),
        sa.CheckConstraint("result_count >= 0", name="result_count_nonnegative"),
        sa.ForeignKeyConstraint(["keyword_id"], ["keywords.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_job_id"], ["collection_jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["raw_evidence_id"], ["raw_evidence.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parser_version_id"], ["parser_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ingestion_key", name="uq_google_serp_captures_ingestion_key"),
        sa.UniqueConstraint(
            "raw_evidence_id",
            "parser_version_id",
            name="uq_google_serp_captures_evidence_parser",
        ),
    )
    op.create_index(
        "ix_google_serp_captures_keyword_captured",
        "google_serp_captures",
        ["keyword_id", "captured_at"],
    )
    op.create_index(
        "ix_google_serp_captures_context_captured",
        "google_serp_captures",
        ["keyword_id", "geo_code", "device_profile", "captured_at"],
    )
    op.create_index(
        "ix_google_serp_captures_raw_evidence_id",
        "google_serp_captures",
        ["raw_evidence_id"],
    )
    op.create_table(
        "google_serp_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("capture_id", sa.Uuid(), nullable=False),
        sa.Column("absolute_position", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("result_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(1000), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("displayed_domain", sa.String(255), nullable=False),
        sa.Column("snippet", sa.String(2000)),
        sa.Column("identity_match", sa.String(20)),
        sa.Column("identity_domain", sa.String(255)),
        sa.Column("result_metadata", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("absolute_position > 0", name="absolute_position_positive"),
        sa.CheckConstraint("page_number > 0", name="page_number_positive"),
        sa.CheckConstraint("length(trim(result_type)) > 0", name="result_type_not_blank"),
        sa.CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        sa.CheckConstraint("length(trim(url)) > 0", name="url_not_blank"),
        sa.CheckConstraint("length(trim(displayed_domain)) > 0", name="displayed_domain_not_blank"),
        sa.CheckConstraint(
            "identity_match IS NULL OR identity_match IN ('novel', 'competitor')",
            name="identity_match_valid",
        ),
        sa.ForeignKeyConstraint(["capture_id"], ["google_serp_captures.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "capture_id", "absolute_position", name="uq_google_serp_results_capture_position"
        ),
    )
    op.create_index("ix_google_serp_results_capture_id", "google_serp_results", ["capture_id"])
    op.create_index("ix_google_serp_results_domain", "google_serp_results", ["displayed_domain"])
    op.create_index(
        "ix_google_serp_results_identity_domain", "google_serp_results", ["identity_domain"]
    )


def downgrade() -> None:
    op.drop_table("google_serp_results")
    op.drop_table("google_serp_captures")

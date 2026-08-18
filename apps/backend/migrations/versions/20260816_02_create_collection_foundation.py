"""Create S12 collection infrastructure foundation tables.

Revision ID: 20260816_02
Revises: 20260816_01, 20260816_lineage_publication
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260816_02"
down_revision: tuple[str, str] = ("20260816_01", "20260816_lineage_publication")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

collection_job_type = postgresql.ENUM(
    "serp", "product_detail", name="collection_job_type", create_type=False
)
collection_source_tier = postgresql.ENUM(
    "first_party_api",
    "licensed_data",
    "public_page",
    name="collection_source_tier",
    create_type=False,
)
collection_job_status = postgresql.ENUM(
    "pending",
    "running",
    "succeeded",
    "failed",
    "quarantined",
    "cancelled",
    name="collection_job_status",
    create_type=False,
)
collection_attempt_status = postgresql.ENUM(
    "running",
    "succeeded",
    "failed",
    "quarantined",
    name="collection_attempt_status",
    create_type=False,
)
collection_failure_type = postgresql.ENUM(
    "network",
    "timeout",
    "challenge",
    "http_error",
    "storage_error",
    "parse_error",
    "validation_error",
    "unknown",
    name="collection_failure_type",
    create_type=False,
)
raw_evidence_type = postgresql.ENUM(
    "response_body", "screenshot", name="raw_evidence_type", create_type=False
)
quarantine_status = postgresql.ENUM(
    "quarantined", "released", "discarded", name="quarantine_status", create_type=False
)
data_quality_check_type = postgresql.ENUM(
    "freshness",
    "completeness",
    "consistency",
    "field_fill_rate",
    "row_count",
    "value_distribution",
    name="data_quality_check_type",
    create_type=False,
)
data_quality_status = postgresql.ENUM(
    "pass", "warn", "fail", name="data_quality_status", create_type=False
)


def _create_enum_types() -> None:
    bind = op.get_bind()
    for enum_type in (
        collection_job_type,
        collection_source_tier,
        collection_job_status,
        collection_attempt_status,
        collection_failure_type,
        raw_evidence_type,
        quarantine_status,
        data_quality_check_type,
        data_quality_status,
    ):
        enum_type.create(bind, checkfirst=True)


def upgrade() -> None:
    _create_enum_types()

    op.create_table(
        "collection_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("job_type", collection_job_type, nullable=False),
        sa.Column("source_tier", collection_source_tier, nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("competitor_product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tracking_target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            collection_job_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(idempotency_key)) > 0",
            name="ck_collection_jobs_idempotency_key_not_blank",
        ),
        sa.CheckConstraint(
            "length(trim(platform)) > 0", name="ck_collection_jobs_platform_not_blank"
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_collection_jobs_attempt_count_nonnegative"
        ),
        sa.CheckConstraint("max_attempts > 0", name="ck_collection_jobs_max_attempts_positive"),
        sa.CheckConstraint(
            "keyword_id IS NOT NULL OR product_id IS NOT NULL OR "
            "competitor_product_id IS NOT NULL OR tracking_target_id IS NOT NULL",
            name="ck_collection_jobs_subject_required",
        ),
        sa.CheckConstraint(
            "NOT (product_id IS NOT NULL AND competitor_product_id IS NOT NULL)",
            name="ck_collection_jobs_single_product_subject",
        ),
        sa.ForeignKeyConstraint(
            ["keyword_id"],
            ["keywords.id"],
            name="fk_collection_jobs_keyword_id_keywords",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_collection_jobs_product_id_products",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["competitor_product_id"],
            ["competitor_products.id"],
            name="fk_collection_jobs_competitor_product_id_competitor_products",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tracking_target_id"],
            ["tracking_targets.id"],
            name="fk_collection_jobs_tracking_target_id_tracking_targets",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_collection_jobs"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_collection_jobs_idempotency_key"
        ),
    )
    op.create_index(
        "ix_collection_jobs_status_scheduled_for",
        "collection_jobs",
        ["status", "scheduled_for"],
    )
    op.create_index(
        "ix_collection_jobs_platform_job_type", "collection_jobs", ["platform", "job_type"]
    )
    op.create_index("ix_collection_jobs_keyword_id", "collection_jobs", ["keyword_id"])
    op.create_index("ix_collection_jobs_product_id", "collection_jobs", ["product_id"])
    op.create_index(
        "ix_collection_jobs_competitor_product_id",
        "collection_jobs",
        ["competitor_product_id"],
    )
    op.create_index(
        "ix_collection_jobs_tracking_target_id", "collection_jobs", ["tracking_target_id"]
    )

    op.create_table(
        "collection_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", collection_attempt_status, nullable=False),
        sa.Column("worker_id", sa.String(length=255), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retryable", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "attempt_number > 0", name="ck_collection_attempts_attempt_number_positive"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["collection_jobs.id"],
            name="fk_collection_attempts_job_id_collection_jobs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_collection_attempts"),
        sa.UniqueConstraint(
            "job_id", "attempt_number", name="uq_collection_attempts_job_number"
        ),
    )
    op.create_index("ix_collection_attempts_job_id", "collection_attempts", ["job_id"])
    op.create_index(
        "ix_collection_attempts_status_started_at",
        "collection_attempts",
        ["status", "started_at"],
    )

    op.create_table(
        "collection_failures",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("failure_type", collection_failure_type, nullable=False),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("retryable", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(message)) > 0", name="ck_collection_failures_message_not_blank"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["collection_jobs.id"],
            name="fk_collection_failures_job_id_collection_jobs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["collection_attempts.id"],
            name="fk_collection_failures_attempt_id_collection_attempts",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_collection_failures"),
    )
    op.create_index(
        "ix_collection_failures_job_occurred_at",
        "collection_failures",
        ["job_id", "occurred_at"],
    )
    op.create_index(
        "ix_collection_failures_failure_type", "collection_failures", ["failure_type"]
    )

    op.create_table(
        "raw_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "evidence_type",
            raw_evidence_type,
            server_default="response_body",
            nullable=False,
        ),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_bucket", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("byte_length", sa.Integer(), nullable=False),
        sa.Column("compressed", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("final_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "challenge_detected", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "capture_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("length(sha256) = 64", name="ck_raw_evidence_sha256_length"),
        sa.CheckConstraint(
            "byte_length >= 0", name="ck_raw_evidence_byte_length_nonnegative"
        ),
        sa.CheckConstraint(
            "length(trim(storage_bucket)) > 0",
            name="ck_raw_evidence_storage_bucket_not_blank",
        ),
        sa.CheckConstraint(
            "length(trim(object_key)) > 0", name="ck_raw_evidence_object_key_not_blank"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["collection_jobs.id"],
            name="fk_raw_evidence_job_id_collection_jobs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["collection_attempts.id"],
            name="fk_raw_evidence_attempt_id_collection_attempts",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_raw_evidence"),
    )
    op.create_index(
        "ix_raw_evidence_job_captured_at", "raw_evidence", ["job_id", "captured_at"]
    )
    op.create_index("ix_raw_evidence_sha256", "raw_evidence", ["sha256"])

    op.create_table(
        "parser_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("page_type", sa.String(length=80), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("code_checksum", sa.String(length=64), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(platform)) > 0", name="ck_parser_versions_platform_not_blank"
        ),
        sa.CheckConstraint(
            "length(trim(page_type)) > 0", name="ck_parser_versions_page_type_not_blank"
        ),
        sa.CheckConstraint(
            "length(trim(version)) > 0", name="ck_parser_versions_version_not_blank"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_parser_versions"),
        sa.UniqueConstraint(
            "platform",
            "page_type",
            "version",
            name="uq_parser_versions_platform_page_version",
        ),
    )
    op.create_index(
        "ix_parser_versions_platform_page_active",
        "parser_versions",
        ["platform", "page_type", "active"],
    )

    op.create_table(
        "quarantine_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("raw_evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parser_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status", quarantine_status, server_default="quarantined", nullable=False
        ),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("schema_errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("parsed_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(trim(reason_code)) > 0",
            name="ck_quarantine_records_reason_code_not_blank",
        ),
        sa.CheckConstraint(
            "length(trim(reason)) > 0", name="ck_quarantine_records_reason_not_blank"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["collection_jobs.id"],
            name="fk_quarantine_records_job_id_collection_jobs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["collection_attempts.id"],
            name="fk_quarantine_records_attempt_id_collection_attempts",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["raw_evidence_id"],
            ["raw_evidence.id"],
            name="fk_quarantine_records_raw_evidence_id_raw_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parser_version_id"],
            ["parser_versions.id"],
            name="fk_quarantine_records_parser_version_id_parser_versions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quarantine_records"),
    )
    op.create_index(
        "ix_quarantine_records_status_created_at",
        "quarantine_records",
        ["status", "created_at"],
    )
    op.create_index("ix_quarantine_records_job_id", "quarantine_records", ["job_id"])
    op.create_index(
        "ix_quarantine_records_raw_evidence_id",
        "quarantine_records",
        ["raw_evidence_id"],
    )

    op.create_table(
        "data_quality_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("check_type", data_quality_check_type, nullable=False),
        sa.Column("status", data_quality_status, nullable=False),
        sa.Column("scope_type", sa.String(length=80), nullable=False),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expected_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(scope_type)) > 0",
            name="ck_data_quality_checks_scope_type_not_blank",
        ),
        sa.CheckConstraint(
            "length(trim(scope_key)) > 0",
            name="ck_data_quality_checks_scope_key_not_blank",
        ),
        sa.CheckConstraint(
            "window_end IS NULL OR window_start IS NULL OR window_end >= window_start",
            name="ck_data_quality_checks_window_order",
        ),
        sa.CheckConstraint(
            "sample_size IS NULL OR sample_size >= 0",
            name="ck_data_quality_checks_sample_size_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_quality_checks"),
    )
    op.create_index(
        "ix_data_quality_checks_scope_created_at",
        "data_quality_checks",
        ["scope_type", "scope_key", "created_at"],
    )
    op.create_index(
        "ix_data_quality_checks_type_status",
        "data_quality_checks",
        ["check_type", "status"],
    )


def downgrade() -> None:
    op.drop_table("data_quality_checks")
    op.drop_table("quarantine_records")
    op.drop_table("parser_versions")
    op.drop_table("raw_evidence")
    op.drop_table("collection_failures")
    op.drop_table("collection_attempts")
    op.drop_table("collection_jobs")

    bind = op.get_bind()
    for enum_type in (
        data_quality_status,
        data_quality_check_type,
        quarantine_status,
        raw_evidence_type,
        collection_failure_type,
        collection_attempt_status,
        collection_job_status,
        collection_source_tier,
        collection_job_type,
    ):
        enum_type.drop(bind, checkfirst=True)

"""Add Week 1 keywords, captures, observations, and collection jobs."""

import sqlalchemy as sa
from alembic import op

revision = "20260819_week1_collection"
down_revision = "20260816_component_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("keywords",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("text", sa.String(255), nullable=False),
        sa.Column("normalized_text", sa.String(255), nullable=False, unique=True), sa.Column("source", sa.String(80), nullable=False),
        sa.Column("intent", sa.String(80)), sa.Column("tier", sa.String(2), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("captures",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("source", sa.String(80), nullable=False),
        sa.Column("page_type", sa.String(40), nullable=False), sa.Column("url", sa.Text(), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False), sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("failure_reason", sa.Text()), sa.Column("metadata_json", sa.JSON(), nullable=False))
    op.create_table("observations",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("capture_id", sa.String(36), nullable=False),
        sa.Column("target_type", sa.String(40), nullable=False), sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("observation_type", sa.String(80), nullable=False), sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("measured_status", sa.String(20), nullable=False), sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("publication_status", sa.String(20), nullable=False), sa.Column("quarantine_reason", sa.Text()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("collection_jobs",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("job_key", sa.String(255), nullable=False, unique=True),
        sa.Column("page_type", sa.String(40), nullable=False), sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("failure_reason", sa.Text()), sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_table("collection_jobs")
    op.drop_table("observations")
    op.drop_table("captures")
    op.drop_table("keywords")

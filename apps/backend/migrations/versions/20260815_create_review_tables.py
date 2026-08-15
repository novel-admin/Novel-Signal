"""Create S7 review and voice-of-customer tables."""

import sqlalchemy as sa
from alembic import op

revision = "20260815_reviews"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("source_review_id", sa.String(255)),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("rating", sa.Float, nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("text", sa.Text),
        sa.Column("topic_type", sa.String(20)),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_on", sa.Date),
        sa.Column("sample_size", sa.Integer, nullable=False, server_default="1"),
        sa.Column("confidence", sa.String(20), nullable=False, server_default="low"),
        sa.Column("evidence", sa.JSON),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("source", "source_review_id", name="uq_review_source_identity"),
        sa.UniqueConstraint("fingerprint", name="uq_review_fingerprint"),
    )
    op.create_index(
        "ix_reviews_target_captured", "review_observations", ["target_id", "captured_at"]
    )
    op.create_table(
        "review_topics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("review_id", sa.String(36), nullable=False),
        sa.Column("topic", sa.String(80), nullable=False),
        sa.Column("topic_type", sa.String(20), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False, server_default="rules-v1"),
        sa.Column("confidence", sa.String(20), nullable=False, server_default="low"),
        sa.ForeignKeyConstraint(["review_id"], ["review_observations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("review_id", "topic", name="uq_review_topic"),
    )
    op.create_table(
        "review_topic_trends",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("topic", sa.String(80), nullable=False),
        sa.Column("topic_type", sa.String(20), nullable=False),
        sa.Column("review_count", sa.Integer, nullable=False),
        sa.Column("average_rating", sa.Float),
        sa.Column("sample_size", sa.Integer, nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.UniqueConstraint("target_id", "period_start", "topic", name="uq_review_topic_trend"),
    )


def downgrade() -> None:
    op.drop_table("review_topic_trends")
    op.drop_table("review_topics")
    op.drop_index("ix_reviews_target_captured", table_name="review_observations")
    op.drop_table("review_observations")

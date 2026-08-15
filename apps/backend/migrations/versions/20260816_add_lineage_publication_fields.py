"""Add evidence lineage and publication state to Palguna observations."""

import sqlalchemy as sa
from alembic import op

revision = "20260816_lineage_publication"
down_revision = "20260815_gaps_impact"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("ad_observations", "review_observations"):
        op.add_column(table, sa.Column("raw_capture_id", sa.String(36)))
        op.add_column(table, sa.Column("parse_run_id", sa.String(36)))
        op.add_column(
            table,
            sa.Column(
                "publication_status",
                sa.String(20),
                nullable=False,
                server_default="published",
            ),
        )
        op.add_column(table, sa.Column("quarantine_reason", sa.Text()))


def downgrade() -> None:
    for table in ("review_observations", "ad_observations"):
        op.drop_column(table, "quarantine_reason")
        op.drop_column(table, "publication_status")
        op.drop_column(table, "parse_run_id")
        op.drop_column(table, "raw_capture_id")

"""Require evidence for market-share models and estimates."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20260825_02"
down_revision = "20260825_01"
branch_labels: str | Sequence[str] | None = None
depends_on = None


def upgrade() -> None:
    for table in ("units_model_fits", "units_estimates", "market_share_daily"):
        op.add_column(
            table,
            sa.Column("input_evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )


def downgrade() -> None:
    for table in ("market_share_daily", "units_estimates", "units_model_fits"):
        op.drop_column(table, "input_evidence")

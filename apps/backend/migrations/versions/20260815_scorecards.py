"""Create scorecard cells and history."""

import sqlalchemy as sa
from alembic import op

revision = "20260815_scorecards"
down_revision = "20260816_component_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scorecard_cells",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("dimension", sa.String(40), nullable=False),
        sa.Column("keyword_id", sa.String(36)),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("band", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("velocity", sa.Float(), nullable=False),
        sa.Column("revenue_at_stake", sa.Float()),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column(
            "measured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "level", "entity_id", "dimension", "keyword_id", name="uq_scorecard_cell_identity"
        ),
    )
    op.create_index("ix_scorecard_cells_entity_level", "scorecard_cells", ["entity_id", "level"])
    op.create_table(
        "scorecard_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("cell_id", sa.String(36), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("band", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("velocity", sa.Float(), nullable=False),
        sa.Column(
            "measured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_scorecard_history_cell_measured", "scorecard_history", ["cell_id", "measured_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_scorecard_history_cell_measured", table_name="scorecard_history")
    op.drop_table("scorecard_history")
    op.drop_index("ix_scorecard_cells_entity_level", table_name="scorecard_cells")
    op.drop_table("scorecard_cells")

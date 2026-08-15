"""Merge independent component migration heads."""

from collections.abc import Sequence

revision = "20260816_component_heads"
down_revision: tuple[str, ...] = (
    "20260814_01",
    "20260815_actions",
    "20260815_ads",
    "20260815_market_share",
    "20260815_reviews",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

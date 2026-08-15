from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from novel_signal.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


class ScorecardCell(Base):
    __tablename__ = "scorecard_cells"
    __table_args__ = (
        UniqueConstraint(
            "level", "entity_id", "dimension", "keyword_id", name="uq_scorecard_cell_identity"
        ),
        Index("ix_scorecard_cells_entity_level", "entity_id", "level"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    dimension: Mapped[str] = mapped_column(String(40), nullable=False)
    keyword_id: Mapped[str | None] = mapped_column(String(36))
    score: Mapped[float] = mapped_column(nullable=False)
    band: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False, default="flat")
    velocity: Mapped[float] = mapped_column(nullable=False, default=0)
    revenue_at_stake: Mapped[float | None] = mapped_column()
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="measured")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ScorecardHistory(Base):
    __tablename__ = "scorecard_history"
    __table_args__ = (Index("ix_scorecard_history_cell_measured", "cell_id", "measured_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cell_id: Mapped[str] = mapped_column(String(36), nullable=False)
    score: Mapped[float] = mapped_column(nullable=False)
    band: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    velocity: Mapped[float] = mapped_column(nullable=False)
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from novel_signal.db import Base


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    text: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_text: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="manual")
    intent: Mapped[str | None] = mapped_column(String(80))
    tier: Mapped[str] = mapped_column(String(2), nullable=False, default="T1")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from novel_signal.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


class ReviewObservation(Base):
    __tablename__ = "review_observations"
    __table_args__ = (
        UniqueConstraint("source", "source_review_id", name="uq_review_source_identity"),
        UniqueConstraint("fingerprint", name="uq_review_fingerprint"),
        Index("ix_reviews_target_captured", "target_id", "captured_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_review_id: Mapped[str | None] = mapped_column(String(255))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    # Sanitized text only: reviewer name, profile URL, email, phone and order data are never stored.
    text: Mapped[str | None] = mapped_column(Text)
    topic_type: Mapped[str | None] = mapped_column(String(20))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_on: Mapped[date | None] = mapped_column(Date)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReviewTopic(Base):
    __tablename__ = "review_topics"
    __table_args__ = (UniqueConstraint("review_id", "topic", name="uq_review_topic"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("review_observations.id", ondelete="CASCADE"), nullable=False
    )
    topic: Mapped[str] = mapped_column(String(80), nullable=False)
    topic_type: Mapped[str] = mapped_column(String(20), nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False, default="rules-v1")
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="low")


class ReviewTopicTrend(Base):
    __tablename__ = "review_topic_trends"
    __table_args__ = (
        UniqueConstraint("target_id", "period_start", "topic", name="uq_review_topic_trend"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    topic: Mapped[str] = mapped_column(String(80), nullable=False)
    topic_type: Mapped[str] = mapped_column(String(20), nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False)
    average_rating: Mapped[float | None] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)

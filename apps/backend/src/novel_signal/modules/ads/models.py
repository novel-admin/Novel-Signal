from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from novel_signal.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


class AdObservation(Base):
    __tablename__ = "ad_observations"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_ad_observations_fingerprint"),
        Index("ix_ad_observations_competitor_captured", "competitor_id", "captured_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(40), nullable=False)
    competitor_id: Mapped[str | None] = mapped_column(String(36))
    product_id: Mapped[str | None] = mapped_column(String(36))
    keyword_id: Mapped[str | None] = mapped_column(String(36))
    capture_id: Mapped[str | None] = mapped_column(String(36))
    ad_type: Mapped[str] = mapped_column(String(40), nullable=False)
    sponsored_position: Mapped[int | None] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_ref: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="measured")
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)


class AdPresenceDaily(Base):
    __tablename__ = "ad_presence_daily"
    __table_args__ = (
        UniqueConstraint("competitor_id", "keyword_id", "day", name="uq_ad_presence_daily_target"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    competitor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    keyword_id: Mapped[str] = mapped_column(String(36), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    ad_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    observed_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coverage: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    evidence_ref: Mapped[str | None] = mapped_column(Text)


class AdDaypartProfile(Base):
    __tablename__ = "ad_daypart_profiles"
    __table_args__ = (
        UniqueConstraint(
            "competitor_id", "keyword_id", "hour", "weekday", name="uq_ad_daypart_profile"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    competitor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    keyword_id: Mapped[str] = mapped_column(String(36), nullable=False)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    presence_rate: Mapped[float] = mapped_column(Float, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="derived")


class AdCreative(Base):
    __tablename__ = "ad_creatives"
    __table_args__ = (UniqueConstraint("platform", "external_id", name="uq_ad_creatives_external"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    competitor_id: Mapped[str | None] = mapped_column(String(36))
    ad_type: Mapped[str] = mapped_column(String(40), nullable=False)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evidence_ref: Mapped[str | None] = mapped_column(Text)


class ExternalAdRecord(Base):
    __tablename__ = "external_ad_records"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_external_ads_source_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    competitor_id: Mapped[str | None] = mapped_column(String(36))
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evidence_ref: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="measured")


class SpendEstimate(Base):
    __tablename__ = "spend_estimates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    competitor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    keyword_id: Mapped[str | None] = mapped_column(String(36))
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    expected: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    input_coverage: Mapped[float] = mapped_column(Float, nullable=False)
    backtest_ref: Mapped[str | None] = mapped_column(String(255))


class OwnAdPerformance(Base):
    __tablename__ = "own_ad_performance"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "campaign_id",
            "period_start",
            "period_end",
            name="uq_own_ad_performance_period",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    account_id: Mapped[str] = mapped_column(String(120), nullable=False)
    campaign_id: Mapped[str | None] = mapped_column(String(120))
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    impressions: Mapped[int | None] = mapped_column(Integer)
    clicks: Mapped[int | None] = mapped_column(Integer)
    spend: Mapped[float | None] = mapped_column(Float)
    sales: Mapped[float | None] = mapped_column(Float)
    conversions: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evidence_ref: Mapped[str | None] = mapped_column(Text)

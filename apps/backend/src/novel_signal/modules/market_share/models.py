from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from novel_signal.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


class UnitsModelFit(Base):
    __tablename__ = "units_model_fits"
    __table_args__ = (
        UniqueConstraint("platform", "marketplace", "category_node", "model_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(80), nullable=False)
    category_node: Mapped[str] = mapped_column(String(160), nullable=False)
    pack_size: Mapped[str | None] = mapped_column(String(80))
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    trained_from: Mapped[date] = mapped_column(Date, nullable=False)
    trained_to: Mapped[date] = mapped_column(Date, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UnitsEstimate(Base):
    __tablename__ = "units_estimates"
    __table_args__ = (UniqueConstraint("entity_id", "observed_on", "model_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_fit_id: Mapped[str] = mapped_column(String(36), nullable=False)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(80), nullable=False)
    category_node: Mapped[str] = mapped_column(String(160), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False)
    brand_id: Mapped[str | None] = mapped_column(String(120))
    observed_on: Mapped[date] = mapped_column(Date, nullable=False)
    bsr: Mapped[int | None] = mapped_column(Integer)
    price: Mapped[float | None] = mapped_column(Float)
    units_low: Mapped[float] = mapped_column(Float, nullable=False)
    units_point: Mapped[float] = mapped_column(Float, nullable=False)
    units_high: Mapped[float] = mapped_column(Float, nullable=False)
    revenue_low: Mapped[float] = mapped_column(Float, nullable=False)
    revenue_point: Mapped[float] = mapped_column(Float, nullable=False)
    revenue_high: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    input_coverage: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(120), nullable=False)
    cross_check_units: Mapped[float | None] = mapped_column(Float)
    divergence_warning: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MarketShareDaily(Base):
    __tablename__ = "market_share_daily"
    __table_args__ = (
        UniqueConstraint("entity_id", "observed_on", "segment_key", "model_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(80), nullable=False)
    category_node: Mapped[str] = mapped_column(String(160), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False)
    brand_id: Mapped[str | None] = mapped_column(String(120))
    observed_on: Mapped[date] = mapped_column(Date, nullable=False)
    segment_key: Mapped[str] = mapped_column(String(255), nullable=False, default="all")
    units_low: Mapped[float] = mapped_column(Float, nullable=False)
    units_point: Mapped[float] = mapped_column(Float, nullable=False)
    units_high: Mapped[float] = mapped_column(Float, nullable=False)
    share_low: Mapped[float] = mapped_column(Float, nullable=False)
    share_point: Mapped[float] = mapped_column(Float, nullable=False)
    share_high: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    input_coverage: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    divergence_warning: Mapped[str | None] = mapped_column(Text)


class ModelBacktest(Base):
    __tablename__ = "units_model_backtests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_fit_id: Mapped[str] = mapped_column(String(36), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_units: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_units: Mapped[float] = mapped_column(Float, nullable=False)
    mae: Mapped[float] = mapped_column(Float, nullable=False)
    mape: Mapped[float | None] = mapped_column(Float)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

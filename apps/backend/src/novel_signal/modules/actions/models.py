from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from novel_signal.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


class ChangeEvent(Base):
    __tablename__ = "change_events"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_change_events_fingerprint"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    old_observation_type: Mapped[str | None] = mapped_column(String(80))
    old_observation_id: Mapped[str | None] = mapped_column(String(36))
    new_observation_type: Mapped[str | None] = mapped_column(String(80))
    new_observation_id: Mapped[str | None] = mapped_column(String(36))
    field_name: Mapped[str | None] = mapped_column(String(120))
    old_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    new_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    actions: Mapped[list[Action]] = relationship(back_populates="change_event")


class Action(Base):
    __tablename__ = "actions"
    __table_args__ = (
        CheckConstraint(
            "change_event_id IS NOT NULL OR gap_id IS NOT NULL", name="action_origin_required"
        ),
        Index("ix_actions_status_created_at", "status", "created_at"),
        Index("ix_actions_gap_status", "gap_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    change_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("change_events.id"), nullable=True
    )
    gap_id: Mapped[str | None] = mapped_column(ForeignKey("gaps.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[str | None] = mapped_column(String(120))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    outcome_note: Mapped[str | None] = mapped_column(Text)
    playbook_entry: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_event: Mapped[ChangeEvent | None] = relationship(back_populates="actions")
    history: Mapped[list[ActionStatusHistory]] = relationship(
        back_populates="action",
        cascade="all, delete-orphan",
        order_by="ActionStatusHistory.changed_at",
    )


class ActionStatusHistory(Base):
    __tablename__ = "action_status_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action_id: Mapped[str] = mapped_column(
        ForeignKey("actions.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(120))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)
    action: Mapped[Action] = relationship(back_populates="history")


class Gap(Base):
    __tablename__ = "gaps"
    __table_args__ = (Index("ix_gaps_status_revenue", "status", "revenue_at_stake"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    fingerprint: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    dimension: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    keyword_id: Mapped[str | None] = mapped_column(String(36))
    benchmark_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    current_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    gap_size: Mapped[float | None] = mapped_column(nullable=True)
    revenue_at_stake: Mapped[float | None] = mapped_column(nullable=True)
    root_cause: Mapped[str | None] = mapped_column(String(120))
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="derived")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ActionImpact(Base):
    __tablename__ = "action_impact"
    __table_args__ = (UniqueConstraint("action_id", "days_after", name="uq_action_impact_day"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action_id: Mapped[str] = mapped_column(
        ForeignKey("actions.id", ondelete="CASCADE"), nullable=False
    )
    days_after: Mapped[int] = mapped_column(nullable=False)
    metric: Mapped[str] = mapped_column(String(80), nullable=False)
    baseline: Mapped[float | None] = mapped_column(nullable=True)
    observed: Mapped[float | None] = mapped_column(nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

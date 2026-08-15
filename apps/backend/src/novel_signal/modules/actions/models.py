from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, func
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
    old_value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
    new_value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    actions: Mapped[list[Action]] = relationship(back_populates="change_event")


class Action(Base):
    __tablename__ = "actions"
    __table_args__ = (Index("ix_actions_status_created_at", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    change_event_id: Mapped[str] = mapped_column(ForeignKey("change_events.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[str | None] = mapped_column(String(120))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    outcome_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_event: Mapped[ChangeEvent] = relationship(back_populates="actions")
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

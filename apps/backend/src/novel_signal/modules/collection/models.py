from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from novel_signal.db import Base


class Capture(Base):
    __tablename__ = "captures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    page_type: Mapped[str] = mapped_column(String(40), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="captured")
    failure_reason: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    capture_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    observation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    measured_status: Mapped[str] = mapped_column(String(20), nullable=False, default="measured")
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False)
    publication_status: Mapped[str] = mapped_column(String(20), nullable=False, default="published")
    quarantine_reason: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CollectionJob(Base):
    __tablename__ = "collection_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    page_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

from datetime import UTC, datetime

from novel_signal.db import Base
from novel_signal.modules.actions.models import Action, ActionStatusHistory, ChangeEvent, Gap
from novel_signal.modules.collection.models import Capture, CollectionJob, Observation
from novel_signal.modules.collection.schemas import (
    CaptureCreate,
    CollectionJobCreate,
    ObservationCreate,
)
from novel_signal.modules.collection.service import (
    create_capture,
    publish_observation,
    schedule_job,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Capture.__table__,
            Observation.__table__,
            CollectionJob.__table__,
            ChangeEvent.__table__,
            Action.__table__,
            ActionStatusHistory.__table__,
            Gap.__table__,
        ],
    )
    return Session(engine)


def test_week1_flow_publishes_evidence_and_creates_one_change() -> None:
    session = db()
    capture_one = create_capture(
        session,
        CaptureCreate(
            page_type="product", url="https://amazon.in/p/1", target_id="p1", content_hash="a"
        ),
    )
    publish_observation(
        session,
        ObservationCreate(
            capture_id=capture_one.id,
            target_type="product",
            target_id="p1",
            observation_type="price",
            value={"price": 499},
            parser_version="amazon-product-1",
        ),
    )
    capture_two = create_capture(
        session,
        CaptureCreate(
            page_type="product", url="https://amazon.in/p/1", target_id="p1", content_hash="b"
        ),
    )
    publish_observation(
        session,
        ObservationCreate(
            capture_id=capture_two.id,
            target_type="product",
            target_id="p1",
            observation_type="price",
            value={"price": 449},
            parser_version="amazon-product-1",
        ),
    )
    changes = session.query(ChangeEvent).all()
    assert len(changes) == 1
    assert changes[0].old_value == 499
    assert changes[0].new_value == 449


def test_week1_job_key_is_idempotent() -> None:
    session = db()
    data = CollectionJobCreate(
        job_key="product:p1:2026-08-19T10:00Z",
        page_type="product",
        target_id="p1",
        scheduled_at=datetime(2026, 8, 19, 10, tzinfo=UTC),
    )
    first = schedule_job(session, data)
    second = schedule_job(session, data)
    assert first.id == second.id
    assert session.query(CollectionJob).count() == 1

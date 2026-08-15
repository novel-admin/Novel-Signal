from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from novel_signal.db import Base
from novel_signal.modules.actions.models import Action, ActionStatusHistory
from novel_signal.modules.actions.schemas import ActionCreate, ActionTransition, ChangeEventCreate
from novel_signal.modules.actions.service import (
    ActionsError,
    create_action,
    create_change,
    transition_action,
)


def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def event_data(fingerprint: str = "price:one") -> ChangeEventCreate:
    return ChangeEventCreate(
        target_type="product", target_id="p1", event_type="price_changed", fingerprint=fingerprint
    )


def test_change_fingerprint_is_idempotent() -> None:
    db = session()
    first = create_change(db, event_data())
    second = create_change(db, event_data())
    assert first.id == second.id
    assert db.query(Action).count() == 0


def test_action_transition_requires_outcome_note_and_records_history() -> None:
    db = session()
    event = create_change(db, event_data())
    action = create_action(db, ActionCreate(change_event_id=event.id, title="Review price"))
    assert db.query(ActionStatusHistory).count() == 1
    action = transition_action(db, action, ActionTransition(status="in_progress"))
    try:
        transition_action(db, action, ActionTransition(status="done"))
    except ActionsError as error:
        assert "outcome note" in str(error)
    else:
        raise AssertionError("completion without an outcome note must fail")
    updated = transition_action(
        db, action, ActionTransition(status="done", note="Repriced listing", changed_by="palguna")
    )
    assert updated.status == "done"
    assert updated.outcome_note == "Repriced listing"
    assert db.query(ActionStatusHistory).count() == 3


def test_invalid_transition_is_rejected() -> None:
    db = session()
    event = create_change(db, event_data())
    action = create_action(db, ActionCreate(change_event_id=event.id, title="Review price"))
    try:
        transition_action(db, action, ActionTransition(status="done", note="closed"))
    except ActionsError as error:
        assert "cannot transition" in str(error)
    else:
        raise AssertionError("open actions cannot jump directly to done")

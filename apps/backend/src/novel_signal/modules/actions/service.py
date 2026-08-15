from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Action, ActionStatusHistory, ChangeEvent
from .schemas import ActionCreate, ActionTransition, ChangeEventCreate

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open": {"in_progress", "dismissed"},
    "in_progress": {"open", "done", "dismissed"},
    "done": set(),
    "dismissed": {"open"},
}


class ActionsError(Exception):
    """Expected domain error exposed as a 4xx response by the router."""


def create_change(session: Session, data: ChangeEventCreate) -> ChangeEvent:
    existing = session.scalar(
        select(ChangeEvent).where(ChangeEvent.fingerprint == data.fingerprint)
    )
    if existing:
        return existing
    event = ChangeEvent(**data.model_dump(exclude_none=True))
    session.add(event)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(ChangeEvent).where(ChangeEvent.fingerprint == data.fingerprint)
        )
        if existing:
            return existing
        raise
    session.refresh(event)
    return event


def create_action(session: Session, data: ActionCreate) -> Action:
    if not session.get(ChangeEvent, data.change_event_id):
        raise ActionsError("change event not found")
    action = Action(**data.model_dump())
    session.add(action)
    session.flush()
    session.add(ActionStatusHistory(action_id=action.id, from_status=None, to_status="open"))
    session.commit()
    session.refresh(action)
    return action


def transition_action(session: Session, action: Action, data: ActionTransition) -> Action:
    if data.status == action.status:
        raise ActionsError("action is already in that status")
    if data.status not in ALLOWED_TRANSITIONS.get(action.status, set()):
        raise ActionsError(f"cannot transition action from {action.status} to {data.status}")
    if data.status == "done" and not data.note:
        raise ActionsError("an outcome note is required when completing an action")
    now = datetime.now(UTC)
    previous = action.status
    action.status = data.status
    if data.status == "done":
        action.outcome_note = data.note
        action.closed_at = now
    elif data.note and data.status == "dismissed":
        action.outcome_note = data.note
        action.closed_at = now
    elif previous in {"done", "dismissed"}:
        action.closed_at = None
    session.add(
        ActionStatusHistory(
            action_id=action.id,
            from_status=previous,
            to_status=data.status,
            changed_by=data.changed_by,
            note=data.note,
        )
    )
    session.commit()
    session.refresh(action)
    return action

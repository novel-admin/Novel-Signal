from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Action, ActionImpact, ActionStatusHistory, ChangeEvent, Gap
from .schemas import ActionCreate, ActionTransition, ChangeEventCreate, GapCreate, ImpactCreate

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open": {"in_progress", "dismissed"},
    "in_progress": {"open", "done", "dismissed"},
    "done": set(),
    "dismissed": {"open"},
}


class ActionsError(Exception):
    """Expected domain error exposed as a 4xx response by the router."""


def create_gap(session: Session, data: GapCreate) -> Gap:
    existing = session.scalar(select(Gap).where(Gap.fingerprint == data.fingerprint))
    if existing:
        return existing
    gap = Gap(**data.model_dump())
    session.add(gap)
    session.commit()
    session.refresh(gap)
    return gap


def add_impact(session: Session, action_id: str, data: ImpactCreate) -> ActionImpact:
    impact = ActionImpact(action_id=action_id, **data.model_dump())
    session.add(impact)
    session.commit()
    session.refresh(impact)
    return impact


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
    if data.change_event_id and not session.get(ChangeEvent, data.change_event_id):
        raise ActionsError("change event not found")
    if data.gap_id and not session.get(Gap, data.gap_id):
        raise ActionsError("gap not found")
    if data.gap_id:
        existing = session.scalar(
            select(Action).where(
                Action.gap_id == data.gap_id,
                Action.status.in_(("open", "in_progress")),
            )
        )
        if existing:
            return existing
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
    if data.status == "in_progress" and (not action.owner_user_id or not action.due_at):
        raise ActionsError("owner and due date are required before an action becomes active")
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

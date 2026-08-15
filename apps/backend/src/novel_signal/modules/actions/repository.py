from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .models import Action, ChangeEvent


def get_change(session: Session, event_id: str) -> ChangeEvent | None:
    return session.get(ChangeEvent, event_id)


def get_action(session: Session, action_id: str) -> Action | None:
    return session.scalar(
        select(Action).options(joinedload(Action.history)).where(Action.id == action_id)
    )


def list_changes(
    session: Session, *, limit: int, cursor: str | None, event_type: str | None
) -> list[ChangeEvent]:
    query = (
        select(ChangeEvent)
        .order_by(ChangeEvent.detected_at.desc(), ChangeEvent.id.desc())
        .limit(limit + 1)
    )
    if event_type:
        query = query.where(ChangeEvent.event_type == event_type)
    if cursor:
        query = query.where(ChangeEvent.id < cursor)
    return list(session.scalars(query))


def list_actions(
    session: Session, *, limit: int, cursor: str | None, status: str | None
) -> list[Action]:
    query = select(Action).order_by(Action.created_at.desc(), Action.id.desc()).limit(limit + 1)
    if status:
        query = query.where(Action.status == status)
    if cursor:
        query = query.where(Action.id < cursor)
    return list(session.scalars(query))

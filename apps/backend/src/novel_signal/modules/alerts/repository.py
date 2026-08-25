from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AlertEvent, AlertRule


def list_alerts(
    session: Session, *, limit: int, cursor: str | None, status: str | None
) -> list[AlertEvent]:
    query = select(AlertEvent).order_by(AlertEvent.opened_at.desc(), AlertEvent.id).limit(limit + 1)
    if cursor:
        query = query.where(AlertEvent.id > cursor)
    if status:
        query = query.where(AlertEvent.status == status)
    return list(session.scalars(query))


def get_alert(session: Session, alert_id: str) -> AlertEvent | None:
    return session.get(AlertEvent, alert_id)


def list_rules(session: Session) -> list[AlertRule]:
    return list(session.scalars(select(AlertRule).order_by(AlertRule.rule_key, AlertRule.version)))


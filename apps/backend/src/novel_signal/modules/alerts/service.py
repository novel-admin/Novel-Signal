from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AlertEvent, AlertRule
from .schemas import AlertEventCreate, AlertRuleCreate, AlertTransition


class AlertError(Exception):
    pass


def create_rule(session: Session, data: AlertRuleCreate) -> AlertRule:
    existing = session.scalar(
        select(AlertRule).where(
            AlertRule.rule_key == data.rule_key, AlertRule.version == data.version
        )
    )
    if existing:
        return existing
    rule = AlertRule(**data.model_dump())
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


def open_alert(session: Session, data: AlertEventCreate) -> AlertEvent:
    rule = session.get(AlertRule, data.rule_id)
    if not rule or not rule.enabled:
        raise AlertError("enabled alert rule not found")
    existing = session.scalar(select(AlertEvent).where(AlertEvent.fingerprint == data.fingerprint))
    if existing:
        return existing
    event = AlertEvent(**data.model_dump())
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def transition_alert(session: Session, event: AlertEvent, data: AlertTransition) -> AlertEvent:
    if event.status == "resolved":
        raise AlertError("resolved alerts cannot transition")
    if event.status == data.status:
        return event
    if event.status == "open" and data.status == "acknowledged":
        event.status = "acknowledged"
        event.acknowledged_at = datetime.now(UTC)
    elif data.status == "resolved":
        event.status = "resolved"
        event.resolved_at = datetime.now(UTC)
    else:
        raise AlertError(f"cannot transition alert from {event.status} to {data.status}")
    session.commit()
    session.refresh(event)
    return event

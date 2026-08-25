from novel_signal.db import Base
from novel_signal.modules.alerts.models import AlertEvent, AlertRule
from novel_signal.modules.alerts.schemas import AlertEventCreate, AlertRuleCreate, AlertTransition
from novel_signal.modules.alerts.service import create_rule, open_alert, transition_alert
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[AlertRule.__table__, AlertEvent.__table__])
    return Session(engine)


def test_alerts_are_deduplicated_and_transition() -> None:
    db = session()
    rule = create_rule(
        db,
        AlertRuleCreate(
            rule_key="rank-loss",
            alert_type="rank_lost_top_10",
            version="v1",
            severity="critical",
        ),
    )
    data = AlertEventCreate(
        rule_id=rule.id,
        alert_type=rule.alert_type,
        severity="critical",
        target_type="product",
        target_id="product-1",
        title="Product lost top-10 rank",
        evidence={"observation_ids": ["obs-1"]},
        fingerprint="rank-loss:product-1:keyword-1",
    )
    first = open_alert(db, data)
    second = open_alert(db, data)
    assert first.id == second.id
    assert (
        transition_alert(db, first, AlertTransition(status="acknowledged")).status == "acknowledged"
    )
    assert transition_alert(db, first, AlertTransition(status="resolved")).status == "resolved"

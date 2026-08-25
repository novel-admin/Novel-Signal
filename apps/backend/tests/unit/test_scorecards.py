from novel_signal.db import Base
from novel_signal.modules.actions.models import Action, ActionStatusHistory, Gap
from novel_signal.modules.alerts.models import AlertEvent, AlertRule
from novel_signal.modules.scorecards.models import ScorecardCell, ScorecardHistory
from novel_signal.modules.scorecards.schemas import ScorecardUpsert
from novel_signal.modules.scorecards.service import evaluate_scorecard, score_band, upsert_scorecard
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_score_bands_are_deterministic() -> None:
    assert score_band(None) == "unknown"
    assert score_band(90) == "leading"
    assert score_band(70) == "competitive"
    assert score_band(45) == "lagging"
    assert score_band(20) == "critical"


def test_upsert_preserves_history() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[ScorecardCell.__table__, ScorecardHistory.__table__])
    with Session(engine) as session:
        data = ScorecardUpsert(
            level="sku", entity_id="sku-1", dimension="price", score=30, evidence={"ids": ["e1"]}
        )
        cell = upsert_scorecard(session, data)
        updated = upsert_scorecard(session, data.model_copy(update={"score": 80}))
        assert updated.id == cell.id
        assert updated.band == "competitive"


def test_unknown_scorecard_keeps_missing_input_explicit() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[ScorecardCell.__table__, ScorecardHistory.__table__])
    with Session(engine) as session:
        cell = upsert_scorecard(
            session,
            ScorecardUpsert(
                level="sku",
                entity_id="sku-1",
                dimension="availability",
                unknown_reason="latest observation is stale",
                freshness_state="stale",
            ),
        )
        assert cell.score is None
        assert cell.band == "unknown"
        assert cell.confidence == "unknown"


def test_critical_scorecard_creates_one_gap_action_and_alert() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            ScorecardCell.__table__,
            ScorecardHistory.__table__,
            Gap.__table__,
            Action.__table__,
            ActionStatusHistory.__table__,
            AlertRule.__table__,
            AlertEvent.__table__,
        ],
    )
    with Session(engine) as session:
        data = ScorecardUpsert(
            level="sku",
            entity_id="sku-1",
            dimension="price",
            score=20,
            evidence={"observation_ids": ["price-1"]},
        )
        first = evaluate_scorecard(session, data)
        second = evaluate_scorecard(session, data)
        assert first.gap is not None and first.action is not None and first.alert is not None
        assert second.gap is not None and second.gap.id == first.gap.id
        assert second.action is not None and second.action.id == first.action.id
        assert second.alert is not None and second.alert.id == first.alert.id

from novel_signal.db import Base
from novel_signal.modules.scorecards.models import ScorecardCell, ScorecardHistory
from novel_signal.modules.scorecards.schemas import ScorecardUpsert
from novel_signal.modules.scorecards.service import score_band, upsert_scorecard
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_score_bands_are_deterministic() -> None:
    assert score_band(90) == "leading"
    assert score_band(70) == "competitive"
    assert score_band(45) == "lagging"
    assert score_band(20) == "critical"


def test_upsert_preserves_history() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[ScorecardCell.__table__, ScorecardHistory.__table__])
    with Session(engine) as session:
        data = ScorecardUpsert(level="sku", entity_id="sku-1", dimension="price", score=30)
        cell = upsert_scorecard(session, data)
        updated = upsert_scorecard(session, data.model_copy(update={"score": 80}))
        assert updated.id == cell.id
        assert updated.band == "competitive"

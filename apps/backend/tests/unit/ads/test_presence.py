from datetime import UTC, date, datetime

from novel_signal.db import Base
from novel_signal.modules.ads.models import AdObservation, AdPresenceDaily
from novel_signal.modules.ads.schemas import AdObservationCreate, PresenceDerive
from novel_signal.modules.ads.service import continuous_ad_days, derive_presence, record_observation
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_presence_uses_successful_captures_as_denominator() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[AdObservation.__table__, AdPresenceDaily.__table__])
    with Session(engine) as session:
        record_observation(
            session,
            AdObservationCreate(
                platform="amazon_in",
                marketplace="amazon_in",
                competitor_id="competitor-1",
                keyword_id="keyword-1",
                capture_id="capture-1",
                raw_capture_id="raw-1",
                parse_run_id="parser-v1",
                ad_type="sponsored_product",
                sponsored_position=1,
                captured_at=datetime(2026, 8, 25, 10, tzinfo=UTC),
                evidence_ref="raw-1",
                fingerprint="ad-1",
            ),
        )
        row = derive_presence(
            session,
            PresenceDerive(
                competitor_id="competitor-1",
                keyword_id="keyword-1",
                day=date(2026, 8, 25),
                successful_capture_ids=["capture-1", "capture-2"],
            ),
        )
        assert row.observed_slots == 1
        assert row.total_slots == 2
        assert row.coverage == 0.5


def test_continuous_days_stops_at_first_break() -> None:
    rows = [
        AdPresenceDaily(competitor_id="c", keyword_id="k", day=date(2026, 8, day), ad_days=1)
        for day in (25, 24, 22)
    ]
    assert continuous_ad_days(rows) == 2

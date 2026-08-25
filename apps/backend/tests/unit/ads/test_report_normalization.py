import json
from datetime import date

from novel_signal.db import Base
from novel_signal.modules.ads.models import AmazonAdsSearchTermContribution
from novel_signal.modules.ads.service import ingest_search_term_report
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_report_normalization_is_idempotent_and_keeps_lineage() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[AmazonAdsSearchTermContribution.__table__])
    body = json.dumps(
        [
            {
                "campaignId": "campaign-1",
                "adGroupId": "group-1",
                "searchTerm": "baby wipes",
                "keyword": "wipes",
                "matchType": "BROAD",
                "impressions": 100,
                "clicks": 10,
                "cost": 50.5,
                "purchases7d": 2,
                "sales7d": 200,
            }
        ]
    ).encode()
    with Session(engine) as session:
        values = dict(
            body=body,
            profile_id="profile-1",
            report_id="report-1",
            period_start=date(2026, 8, 24),
            period_end=date(2026, 8, 25),
            currency="INR",
            raw_capture_id="raw-1",
            parse_run_id="amazon-ads-search-term-v1",
        )
        first = ingest_search_term_report(session, **values)
        second = ingest_search_term_report(session, **values)
        assert first[0].id == second[0].id
        assert first[0].confidence == "measured"
        assert first[0].raw_capture_id == "raw-1"
        assert session.query(AmazonAdsSearchTermContribution).count() == 1

import hashlib
import json
import uuid
from datetime import date

from novel_signal.db import Base
from novel_signal.modules.ads.models import AmazonAdsSearchTermContribution
from novel_signal.modules.ads.service import (
    ingest_search_term_report,
    ingest_stored_search_term_report,
)
from novel_signal.modules.collection.models import ParserVersion, RawEvidence
from novel_signal.modules.collection.storage import StoredRawObject
from novel_signal.sources.base import RawSourcePage, SourceType
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class Store:
    def put_raw(self, *, platform: str, page_type: str, body: bytes) -> StoredRawObject:
        digest = hashlib.sha256(body).hexdigest()
        return StoredRawObject(digest, "raw", f"{platform}/{digest}", len(body), len(body))


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


def test_stored_report_creates_raw_evidence_before_contributions() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            RawEvidence.__table__,
            ParserVersion.__table__,
            AmazonAdsSearchTermContribution.__table__,
        ],
    )
    body = json.dumps([{"campaignId": "c1", "searchTerm": "baby wipes"}]).encode()
    with Session(engine) as session:
        rows = ingest_stored_search_term_report(
            session,
            object_store=Store(),
            job_id=uuid.uuid4(),
            attempt_id=uuid.uuid4(),
            page=RawSourcePage(
                SourceType.AMAZON_ADS_API,
                "search_terms",
                body,
                "application/json",
                "request-1",
            ),
            profile_id="profile-1",
            report_id="report-1",
            period_start=date(2026, 8, 24),
            period_end=date(2026, 8, 25),
            currency="INR",
        )
        assert session.query(RawEvidence).count() == 1
        assert rows[0].raw_capture_id
        assert rows[0].parse_run_id

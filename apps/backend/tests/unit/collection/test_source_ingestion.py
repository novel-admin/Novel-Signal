import hashlib
import uuid

from novel_signal.db import Base
from novel_signal.modules.collection.models import ParserVersion, RawEvidence
from novel_signal.modules.collection.source_ingestion import (
    ensure_parser_version,
    persist_raw_source_page,
)
from novel_signal.modules.collection.storage import StoredRawObject
from novel_signal.sources.base import RawSourcePage, SourceType
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class Store:
    def put_raw(self, *, platform: str, page_type: str, body: bytes) -> StoredRawObject:
        digest = hashlib.sha256(body).hexdigest()
        return StoredRawObject(
            digest, "raw", f"{platform}/{page_type}/{digest}", len(body), len(body)
        )


def test_source_page_is_durable_before_normalization() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[RawEvidence.__table__, ParserVersion.__table__])
    with Session(engine) as session:
        page = RawSourcePage(
            SourceType.AMAZON_ADS_API,
            "search_terms",
            b"[]",
            "application/json",
            "request-1",
        )
        evidence = persist_raw_source_page(
            session,
            object_store=Store(),
            job_id=uuid.uuid4(),
            attempt_id=uuid.uuid4(),
            platform="amazon_ads_api",
            page=page,
        )
        parser = ensure_parser_version(
            session,
            platform="amazon_ads_api",
            page_type="search_terms",
            version="amazon-ads-search-term-v1",
        )
        assert session.get(RawEvidence, evidence.id) is not None
        assert parser.version == "amazon-ads-search-term-v1"

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from novel_signal.config import get_settings
from novel_signal.modules.keywords.models import (
    IntentCluster,
    Keyword,
    KeywordSource,
    KeywordSourceType,
    KeywordTrackingStatus,
    TrackingTarget,
)
from novel_signal.modules.universe.models import Marketplace, Product, TrackingTier
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session


@pytest.fixture
def postgres_session() -> Iterator[Session]:
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        with engine.connect() as check:
            if not inspect(check).has_table("keywords"):
                pytest.skip("S2 migration not applied")
    except OperationalError:
        engine.dispose()
        pytest.skip("PostgreSQL unavailable")
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def make_keyword(text: str) -> Keyword:
    return Keyword(
        keyword_text=text,
        normalized_text=text.strip().lower(),
        marketplace=Marketplace.AMAZON_IN,
        tier=TrackingTier.T1,
        tracking_status=KeywordTrackingStatus.ACTIVE,
        intent_cluster=IntentCluster.GENERIC_CATEGORY,
        sources=[KeywordSource(source_type=KeywordSourceType.MANUAL)],
    )


def test_postgres_keyword_partial_uniqueness_enum_and_archive_reuse(
    postgres_session: Session,
) -> None:
    text = f"keyword-{uuid4()}"
    first = make_keyword(text)
    postgres_session.add(first)
    postgres_session.flush()
    with pytest.raises(IntegrityError), postgres_session.begin_nested():
        postgres_session.add(make_keyword(text))
        postgres_session.flush()
    first.archived_at = datetime.now(UTC)
    postgres_session.flush()
    replacement = make_keyword(text)
    postgres_session.add(replacement)
    postgres_session.flush()
    postgres_session.expire_all()
    assert (
        postgres_session.get(Keyword, replacement.id).tracking_status
        is KeywordTrackingStatus.ACTIVE
    )


def test_postgres_target_exactly_one_and_active_uniqueness(postgres_session: Session) -> None:
    keyword = make_keyword(f"target-{uuid4()}")
    product = Product(
        internal_sku=f"SKU-{uuid4()}",
        name="Owned",
        brand="Owned",
        category="Care",
        marketplace=Marketplace.AMAZON_IN,
        tracking_tier=TrackingTier.T1,
    )
    postgres_session.add_all([keyword, product])
    postgres_session.flush()
    target = TrackingTarget(keyword_id=keyword.id, product_id=product.id, cadence_minutes=240)
    postgres_session.add(target)
    postgres_session.flush()
    with pytest.raises(IntegrityError), postgres_session.begin_nested():
        postgres_session.add(TrackingTarget(keyword_id=keyword.id, product_id=product.id))
        postgres_session.flush()
    with pytest.raises(IntegrityError), postgres_session.begin_nested():
        postgres_session.add(
            TrackingTarget(
                keyword_id=keyword.id, product_id=product.id, competitor_product_id=uuid4()
            )
        )
        postgres_session.flush()

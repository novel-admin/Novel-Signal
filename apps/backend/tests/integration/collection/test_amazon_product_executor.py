from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from novel_signal.collectors.playwright_browser import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
    BrowserConfigurationError,
    BrowserDeviceType,
    BrowserLifecycleError,
    BrowserNavigationError,
    BrowserNavigationTimeoutError,
    ChallengeKind,
    ChallengeState,
)
from novel_signal.config import Settings
from novel_signal.db import Base
from novel_signal.modules.collection.amazon_product_executor import AmazonProductExecutor
from novel_signal.modules.collection.amazon_serp_executor import AmazonSerpExecutor
from novel_signal.modules.collection.execution import (
    CollectionExecutionError,
    CollectionWorkItem,
    get_executor,
)
from novel_signal.modules.collection.models import (
    CollectionJob,
    CollectionJobType,
    CollectionSourceTier,
    ParserVersion,
    RawEvidence,
)
from novel_signal.modules.collection.service import AttemptClaim, CollectionLifecycleService
from novel_signal.modules.collection.storage import StoredRawObject
from novel_signal.modules.listings.models import ListingSnapshot
from novel_signal.modules.price_monitoring.models import PriceObservation
from novel_signal.modules.universe.models import (
    Competitor,
    CompetitorProduct,
    Marketplace,
    Product,
    TrackingTier,
)
from novel_signal.tasks import collection as collection_tasks
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

CAPTURED_AT = datetime(2026, 8, 30, 10, tzinfo=UTC)
BODY = b"""<input id="ASIN" value="B0TEST0001"><span id="productTitle">Novel Wipes</span>
<span id="priceblock_dealprice">Rs. 99</span><span id="availability">In stock</span>"""


class MemoryStore:
    def __init__(self) -> None:
        self.bodies: list[bytes] = []

    def put_raw(self, *, platform: str, page_type: str, body: bytes) -> StoredRawObject:
        self.bodies.append(body)
        digest = hashlib.sha256(body).hexdigest()
        return StoredRawObject(
            sha256=digest,
            bucket="test-raw",
            object_key=f"raw/{platform}/{page_type}/{digest}.gz",
            byte_length=len(body),
            compressed_byte_length=len(body),
        )


class FakeBrowser:
    def __init__(self, result: BrowserCaptureResult) -> None:
        self.result = result
        self.requests: list[BrowserCaptureRequest] = []
        self.closed = False

    async def __aenter__(self) -> FakeBrowser:
        return self

    async def __aexit__(self, *_: object) -> None:
        self.closed = True

    async def capture(self, request: BrowserCaptureRequest) -> BrowserCaptureResult:
        self.requests.append(request)
        return self.result


class RaisingBrowser:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.closed = False

    async def __aenter__(self) -> RaisingBrowser:
        return self

    async def __aexit__(self, *_: object) -> None:
        self.closed = True

    async def capture(self, request: BrowserCaptureRequest) -> BrowserCaptureResult:
        raise self.error


@pytest.fixture
def engine() -> Iterator[Engine]:
    database = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(database, "connect")
    def foreign_keys(connection: object, _: object) -> None:
        cursor = connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(database)
    yield database
    Base.metadata.drop_all(database)
    database.dispose()


def _settings(**overrides: str) -> Settings:
    return Settings(_env_file=None, amazon_in_min_delay_seconds=0, **overrides)


def _capture(*, challenge: bool = False) -> BrowserCaptureResult:
    return BrowserCaptureResult(
        requested_url="https://www.amazon.in/dp/B0TEST0001",
        final_url="https://www.amazon.in/dp/B0TEST0001?token=not-persisted",
        status=200,
        html=BODY,
        content_type="text/html",
        captured_at=CAPTURED_AT,
        page_type="product_detail",
        profile_id="fake-browser-profile",
        challenge=ChallengeState(ChallengeKind.CAPTCHA, "captcha")
        if challenge
        else ChallengeState(),
    )


def _claim(
    engine: Engine, *, competitor: bool = False
) -> tuple[sessionmaker[Session], AttemptClaim]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        if competitor:
            brand = Competitor(name="Acme")
            session.add(brand)
            session.flush()
            target = CompetitorProduct(
                competitor_id=brand.id,
                name="Acme Wipes",
                brand="Acme",
                category="Care",
                marketplace=Marketplace.AMAZON_IN,
                marketplace_product_id="B0TEST0001",
                tracking_tier=TrackingTier.T1,
            )
            session.add(target)
            session.flush()
            product_id, competitor_product_id = None, target.id
        else:
            target = Product(
                internal_sku="OWN-1",
                name="Novel Wipes",
                brand="Novel",
                category="Care",
                marketplace=Marketplace.AMAZON_IN,
                marketplace_product_id="B0TEST0001",
                tracking_tier=TrackingTier.T1,
            )
            session.add(target)
            session.flush()
            product_id, competitor_product_id = target.id, None
        job = CollectionJob(
            idempotency_key=f"amazon-product-runtime:{target.id}",
            job_type=CollectionJobType.PRODUCT_DETAIL,
            source_tier=CollectionSourceTier.PUBLIC_PAGE,
            platform="amazon_in",
            product_id=product_id,
            competitor_product_id=competitor_product_id,
            scheduled_for=CAPTURED_AT,
        )
        session.add(job)
        session.commit()
        claim = CollectionLifecycleService(session).claim_attempt(job.id, at=CAPTURED_AT)
        assert claim is not None
        session.commit()
        return factory, claim


def _executor(
    *,
    factory: sessionmaker[Session],
    browser_factory: Callable[..., Any],
    settings: Settings | None = None,
) -> tuple[AmazonProductExecutor, MemoryStore]:
    store = MemoryStore()
    return (
        AmazonProductExecutor(
            settings=settings or _settings(),
            session_factory=factory,
            object_store=store,
            browser_session_factory=browser_factory,
        ),
        store,
    )


@pytest.mark.asyncio
async def test_owned_product_executes_raw_first_pipeline(engine: Engine) -> None:
    factory, claim = _claim(engine)
    browser = FakeBrowser(_capture())
    executor, store = _executor(
        factory=factory,
        browser_factory=lambda **_: browser,
        settings=_settings(
            amazon_in_geo_code="MYSORE",
            amazon_in_pincode="570001",
            amazon_in_location_label="Mysore",
        ),
    )

    result = await executor.execute(claim.item)

    assert result.quarantine is None
    assert browser.closed is True
    assert len(browser.requests) == 1
    assert browser.requests[0].requested_url == "https://www.amazon.in/dp/B0TEST0001"
    assert browser.requests[0].profile.device_type is BrowserDeviceType.DESKTOP
    assert browser.requests[0].profile.country_code == "IN"
    assert browser.requests[0].profile.pincode == "570001"
    assert browser.requests[0].profile.location_label == "Mysore"
    assert store.bodies == [BODY]
    assert "listing_snapshot_id" in result.metadata
    assert "price_observation_id" in result.metadata
    with Session(engine) as session:
        raw = session.scalars(select(RawEvidence)).one()
        parser = session.scalars(select(ParserVersion)).one()
        listing = session.scalars(select(ListingSnapshot)).one()
        price = session.scalars(select(PriceObservation)).one()
        assert raw.job_id == claim.item.job_id
        assert raw.attempt_id == claim.item.attempt_id
        assert parser.version == "amazon-product-v1"
        assert listing.product_id == price.product_id == claim.item.product_id
        assert listing.geo_code == price.geo_code == "MYSORE"
        assert listing.content_metadata and listing.content_metadata["pincode"] == "570001"
        assert price.source_metadata and price.source_metadata["location_label"] == "Mysore"
        assert listing.content_metadata and listing.content_metadata["raw_evidence_id"] == str(
            raw.id
        )
        assert price.source_metadata and price.source_metadata["raw_evidence_id"] == str(raw.id)
        assert "?" not in (listing.source_url or "")


@pytest.mark.asyncio
async def test_competitor_product_executes_with_competitor_mapping(engine: Engine) -> None:
    factory, claim = _claim(engine, competitor=True)
    executor, _ = _executor(factory=factory, browser_factory=lambda **_: FakeBrowser(_capture()))
    await executor.execute(claim.item)
    with Session(engine) as session:
        assert (
            session.scalars(select(ListingSnapshot)).one().competitor_product_id
            == claim.item.competitor_product_id
        )
        assert (
            session.scalars(select(PriceObservation)).one().competitor_product_id
            == claim.item.competitor_product_id
        )


@pytest.mark.asyncio
async def test_challenge_retains_raw_without_publication(engine: Engine) -> None:
    factory, claim = _claim(engine)
    executor, _ = _executor(
        factory=factory, browser_factory=lambda **_: FakeBrowser(_capture(challenge=True))
    )
    with pytest.raises(CollectionExecutionError, match="challenge") as raised:
        await executor.execute(claim.item)
    assert raised.value.failure_type.value == "challenge"
    with Session(engine) as session:
        assert len(session.scalars(select(RawEvidence)).all()) == 1
        assert session.scalars(select(ListingSnapshot)).all() == []
        assert session.scalars(select(PriceObservation)).all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "failure_type", "retryable"),
    [
        (BrowserNavigationTimeoutError("secret"), "timeout", True),
        (BrowserNavigationError("secret"), "network", True),
        (BrowserConfigurationError("secret"), "validation_error", False),
        (BrowserLifecycleError("secret"), "unknown", False),
    ],
)
async def test_browser_errors_are_sanitized_and_close_session(
    engine: Engine, error: Exception, failure_type: str, retryable: bool
) -> None:
    factory, claim = _claim(engine)
    browser = RaisingBrowser(error)
    executor, _ = _executor(factory=factory, browser_factory=lambda **_: browser)
    with pytest.raises(CollectionExecutionError) as raised:
        await executor.execute(claim.item)
    assert raised.value.failure_type.value == failure_type
    assert raised.value.retryable is retryable
    assert "secret" not in str(raised.value)
    assert browser.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", ["both", "neither"])
async def test_invalid_product_work_item_is_rejected_before_capture(
    engine: Engine, shape: str
) -> None:
    factory, claim = _claim(engine)
    browser = FakeBrowser(_capture())
    item = CollectionWorkItem(
        job_id=claim.item.job_id,
        attempt_id=claim.item.attempt_id,
        job_type=CollectionJobType.PRODUCT_DETAIL,
        platform="amazon_in",
        keyword_id=None,
        product_id=claim.item.product_id if shape == "both" else None,
        competitor_product_id=uuid4() if shape == "both" else None,
        tracking_target_id=None,
    )
    executor, _ = _executor(factory=factory, browser_factory=lambda **_: browser)
    with pytest.raises(CollectionExecutionError) as raised:
        await executor.execute(item)
    assert raised.value.code == "product_detail_target_invalid"
    assert browser.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["missing", "archived", "missing_identity", "invalid_asin"])
async def test_invalid_owned_targets_are_rejected_before_capture(
    engine: Engine, condition: str
) -> None:
    factory, claim = _claim(engine)
    item = claim.item
    if condition == "missing":
        item = CollectionWorkItem(**{**item.__dict__, "product_id": uuid4()})
    else:
        with Session(engine) as session:
            product = session.get(Product, claim.item.product_id)
            assert product is not None
            if condition == "archived":
                product.archived_at = CAPTURED_AT
            elif condition == "missing_identity":
                product.marketplace_product_id = None
            else:
                product.marketplace_product_id = "invalid"
            session.commit()
    browser = FakeBrowser(_capture())
    executor, _ = _executor(factory=factory, browser_factory=lambda **_: browser)
    with pytest.raises(CollectionExecutionError) as raised:
        await executor.execute(item)
    assert raised.value.code == "product_detail_target_invalid"
    assert browser.requests == []


@pytest.mark.asyncio
async def test_missing_competitor_target_is_rejected_before_capture(engine: Engine) -> None:
    factory, claim = _claim(engine, competitor=True)
    item = CollectionWorkItem(**{**claim.item.__dict__, "competitor_product_id": uuid4()})
    browser = FakeBrowser(_capture())
    executor, _ = _executor(factory=factory, browser_factory=lambda **_: browser)
    with pytest.raises(CollectionExecutionError) as raised:
        await executor.execute(item)
    assert raised.value.code == "product_detail_target_invalid"
    assert browser.requests == []


@pytest.mark.asyncio
async def test_mobile_profile_preserves_blank_location_as_none(engine: Engine) -> None:
    factory, claim = _claim(engine)
    browser = FakeBrowser(_capture())
    executor, _ = _executor(
        factory=factory,
        browser_factory=lambda **_: browser,
        settings=_settings(
            amazon_in_device_profile="mobile",
            amazon_in_pincode="",
            amazon_in_location_label="",
        ),
    )
    await executor.execute(claim.item)
    assert browser.requests[0].profile.device_type is BrowserDeviceType.MOBILE
    assert browser.requests[0].profile.country_code == "IN"
    assert browser.requests[0].profile.pincode is None
    assert browser.requests[0].profile.location_label is None


def test_worker_module_registers_product_and_serp_executors() -> None:
    assert collection_tasks is not None
    assert isinstance(
        get_executor("amazon_in", CollectionJobType.PRODUCT_DETAIL), AmazonProductExecutor
    )
    assert isinstance(get_executor("amazon_in", CollectionJobType.SERP), AmazonSerpExecutor)

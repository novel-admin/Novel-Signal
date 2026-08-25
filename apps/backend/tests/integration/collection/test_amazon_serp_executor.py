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
    BrowserDeviceType,
    BrowserNavigationError,
    BrowserNavigationTimeoutError,
    ChallengeKind,
    ChallengeState,
)
from novel_signal.config import Settings
from novel_signal.db import Base
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
from novel_signal.modules.keywords.models import IntentCluster, Keyword, KeywordTrackingStatus
from novel_signal.modules.rank_visibility.models import DeviceProfile, SerpCapture
from novel_signal.modules.universe.models import Marketplace, TrackingTier
from novel_signal.tasks import collection as collection_tasks
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

CAPTURED_AT = datetime(2026, 8, 25, 7, 0, tzinfo=UTC)
BODY = b"""
<div data-component-type="s-search-result" data-asin="B0TEST0001" data-brand="Novel">
  <h2>Novel Baby Wipes</h2><span>Best Seller</span><span>Rs. 199</span>
</div>
"""


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
            compressed_byte_length=max(1, len(body) // 2),
        )


class FakeBrowserSession:
    def __init__(self, result: BrowserCaptureResult) -> None:
        self.result = result
        self.requests: list[BrowserCaptureRequest] = []

    async def __aenter__(self) -> FakeBrowserSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def capture(self, request: BrowserCaptureRequest) -> BrowserCaptureResult:
        self.requests.append(request)
        return self.result


class RaisingBrowserSession:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def __aenter__(self) -> RaisingBrowserSession:
        raise self.error

    async def __aexit__(self, *_: object) -> None:
        return None


@pytest.fixture
def engine() -> Iterator[Engine]:
    database = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(database, "connect")
    def enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
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
        requested_url="https://www.amazon.in/s?k=baby+wipes",
        final_url="https://www.amazon.in/s?k=baby+wipes",
        status=200,
        html=BODY,
        content_type="text/html",
        captured_at=CAPTURED_AT,
        page_type="serp",
        profile_id="fake-browser-profile",
        challenge=ChallengeState(ChallengeKind.CAPTCHA, "captcha_signal")
        if challenge
        else ChallengeState(),
    )


def _claim(engine: Engine) -> tuple[sessionmaker[Session], Keyword, AttemptClaim]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        keyword = Keyword(
            keyword_text="baby wipes",
            normalized_text="baby wipes",
            marketplace=Marketplace.AMAZON_IN,
            tier=TrackingTier.T1,
            tracking_status=KeywordTrackingStatus.ACTIVE,
            intent_cluster=IntentCluster.GENERIC_CATEGORY,
        )
        session.add(keyword)
        session.flush()
        job = CollectionJob(
            idempotency_key=f"amazon-serp-runtime:{keyword.id}",
            job_type=CollectionJobType.SERP,
            source_tier=CollectionSourceTier.PUBLIC_PAGE,
            platform="amazon_in",
            keyword_id=keyword.id,
            scheduled_for=CAPTURED_AT,
        )
        session.add(job)
        session.commit()
        claim = CollectionLifecycleService(session).claim_attempt(job.id, at=CAPTURED_AT)
        assert claim is not None
        session.commit()
        return factory, keyword, claim


def _executor(
    *,
    factory: sessionmaker[Session],
    browser_factory: Callable[..., Any],
    settings: Settings | None = None,
) -> tuple[AmazonSerpExecutor, MemoryStore]:
    store = MemoryStore()
    return (
        AmazonSerpExecutor(
            settings=settings or _settings(),
            session_factory=factory,
            object_store=store,
            browser_session_factory=browser_factory,
        ),
        store,
    )


@pytest.mark.asyncio
async def test_executor_claim_attempt_and_browser_capture_publish_to_s3(engine: Engine) -> None:
    factory, keyword, claim = _claim(engine)
    browser = FakeBrowserSession(_capture())
    captured_kwargs: dict[str, object] = {}

    def browser_factory(**kwargs: object) -> FakeBrowserSession:
        captured_kwargs.update(kwargs)
        return browser

    executor, store = _executor(factory=factory, browser_factory=browser_factory)
    assert claim.item.attempt_id == claim.attempt.id
    assert claim.item.attempt_id is not None

    result = await executor.execute(claim.item)

    assert result.quarantine is None
    assert result.metadata["publication"] == "created"
    assert browser.requests[0].requested_url == "https://www.amazon.in/s?k=baby+wipes"
    assert browser.requests[0].profile.device_type is BrowserDeviceType.DESKTOP
    assert captured_kwargs["max_concurrency"] == 1
    assert store.bodies == [BODY]
    with Session(engine) as session:
        raw = session.scalars(select(RawEvidence)).one()
        parser_version = session.scalars(select(ParserVersion)).one()
        capture = session.scalars(select(SerpCapture)).one()
        assert raw.sha256 == hashlib.sha256(BODY).hexdigest()
        assert capture.keyword_id == keyword.id
        assert capture.capture_metadata is not None
        assert capture.capture_metadata["raw_evidence_id"] == str(raw.id)
        assert capture.capture_metadata["parser_version_id"] == str(parser_version.id)
        assert capture.captured_at.replace(tzinfo=UTC) == CAPTURED_AT


@pytest.mark.asyncio
async def test_executor_challenge_retains_raw_evidence_without_s3_capture(engine: Engine) -> None:
    factory, _, claim = _claim(engine)
    browser = FakeBrowserSession(_capture(challenge=True))
    executor, _ = _executor(factory=factory, browser_factory=lambda **_: browser)

    with pytest.raises(CollectionExecutionError) as raised:
        await executor.execute(claim.item)

    assert raised.value.code == "challenge_detected"
    with Session(engine) as session:
        assert len(session.scalars(select(RawEvidence)).all()) == 1
        assert session.scalars(select(SerpCapture)).all() == []


@pytest.mark.asyncio
async def test_executor_missing_keyword_fails_safely(engine: Engine) -> None:
    factory, _, claim = _claim(engine)
    executor, _ = _executor(
        factory=factory,
        browser_factory=lambda **_: FakeBrowserSession(_capture()),
    )
    missing_item = CollectionWorkItem(
        job_id=claim.item.job_id,
        attempt_id=claim.item.attempt_id,
        job_type=CollectionJobType.SERP,
        platform="amazon_in",
        keyword_id=uuid4(),
        product_id=None,
        competitor_product_id=None,
        tracking_target_id=None,
    )

    with pytest.raises(CollectionExecutionError) as raised:
        await executor.execute(missing_item)

    assert raised.value.code == "amazon_serp_keyword_not_found"
    assert raised.value.retryable is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("browser_error", "failure_type", "retryable"),
    [
        (BrowserNavigationTimeoutError("ignored"), "timeout", True),
        (BrowserNavigationError("ignored"), "network", True),
        (RuntimeError("fake-secret-value"), "unknown", False),
    ],
)
async def test_executor_maps_browser_failures_safely(
    engine: Engine,
    browser_error: Exception,
    failure_type: str,
    retryable: bool,
) -> None:
    factory, _, claim = _claim(engine)
    executor, _ = _executor(
        factory=factory,
        browser_factory=lambda **_: RaisingBrowserSession(browser_error),
    )

    with pytest.raises(CollectionExecutionError) as raised:
        await executor.execute(claim.item)

    assert raised.value.failure_type.value == failure_type
    assert raised.value.retryable is retryable
    assert "ignored" not in str(raised.value)
    assert "fake-secret-value" not in str(raised.value)


@pytest.mark.asyncio
async def test_executor_validates_device_and_does_not_fabricate_location(engine: Engine) -> None:
    factory, _, claim = _claim(engine)
    browser = FakeBrowserSession(_capture())
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
    assert browser.requests[0].profile.pincode is None
    assert browser.requests[0].profile.location_label is None
    with Session(engine) as session:
        capture = session.scalars(select(SerpCapture)).one()
        assert capture.device_profile is DeviceProfile.MOBILE
        assert "pincode" not in (capture.capture_metadata or {})
        assert "location_label" not in (capture.capture_metadata or {})

    invalid, _ = _executor(
        factory=factory,
        browser_factory=lambda **_: browser,
        settings=_settings(amazon_in_device_profile="tablet"),
    )
    with pytest.raises(CollectionExecutionError) as raised:
        await invalid.execute(claim.item)
    assert raised.value.code == "amazon_serp_device_profile_invalid"


def test_worker_module_registers_amazon_serp_executor() -> None:
    assert collection_tasks is not None
    assert isinstance(get_executor("amazon_in", CollectionJobType.SERP), AmazonSerpExecutor)

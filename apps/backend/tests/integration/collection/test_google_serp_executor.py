from __future__ import annotations

import hashlib
import importlib
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
from novel_signal.modules.collection.execution import (
    CollectionExecutionError,
    CollectionWorkItem,
    get_executor,
)
from novel_signal.modules.collection.google_serp_executor import GoogleSerpExecutor
from novel_signal.modules.collection.models import (
    CollectionJob,
    CollectionJobType,
    CollectionSourceTier,
    ParserVersion,
    RawEvidence,
)
from novel_signal.modules.collection.service import (
    AttemptClaim,
    CollectionLifecycleService,
    CollectionPlanningService,
)
from novel_signal.modules.collection.storage import StoredRawObject
from novel_signal.modules.keywords.models import (
    IntentCluster,
    Keyword,
    KeywordTrackingStatus,
    TrackingTarget,
)
from novel_signal.modules.rank_visibility.models import GoogleSerpCapture, GoogleSerpResult
from novel_signal.modules.universe.models import Marketplace, Product, TrackingTier
from novel_signal.tasks import collection as collection_tasks
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

CAPTURED_AT = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)
BODY = b"""
<input name="q" value="baby wipes">
<div data-result="organic"><a href="https://novel.example/wipes"><h3>Novel Wipes</h3></a>
<div class="snippet">Soft wipes</div></div>
<div data-result="organic"><a href="https://acme.example/wipes"><h3>Acme Wipes</h3></a></div>
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
        self.entered = 0
        self.closed = 0

    async def __aenter__(self) -> FakeBrowserSession:
        self.entered += 1
        return self

    async def __aexit__(self, *_: object) -> None:
        self.closed += 1

    async def capture(self, request: BrowserCaptureRequest) -> BrowserCaptureResult:
        self.requests.append(request)
        return self.result


class RaisingBrowserSession(FakeBrowserSession):
    def __init__(self, error: Exception, *, fail_on_enter: bool = False) -> None:
        super().__init__(_capture())
        self.error = error
        self.fail_on_enter = fail_on_enter

    async def __aenter__(self) -> RaisingBrowserSession:
        self.entered += 1
        if self.fail_on_enter:
            raise self.error
        return self

    async def capture(self, request: BrowserCaptureRequest) -> BrowserCaptureResult:
        self.requests.append(request)
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


def _settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        google_serp_min_delay_seconds=0,
        google_serp_novel_domains="novel.example",
        google_serp_competitor_domains="acme.example",
        **overrides,
    )


def _capture(*, challenge: bool = False) -> BrowserCaptureResult:
    return BrowserCaptureResult(
        requested_url="https://www.google.com/search?q=baby+wipes",
        final_url="https://www.google.com/search?q=baby+wipes",
        status=200,
        html=BODY,
        content_type="text/html",
        captured_at=CAPTURED_AT,
        page_type="serp",
        profile_id="google-desktop-in",
        challenge=ChallengeState(ChallengeKind.CAPTCHA, "captcha")
        if challenge
        else ChallengeState(),
    )


def _claim(
    engine: Engine, *, tracking_status: KeywordTrackingStatus = KeywordTrackingStatus.ACTIVE
) -> tuple[sessionmaker[Session], Keyword, AttemptClaim]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        keyword = Keyword(
            keyword_text="baby wipes",
            normalized_text="baby wipes",
            marketplace=Marketplace.AMAZON_IN,
            tier=TrackingTier.T1,
            tracking_status=tracking_status,
            intent_cluster=IntentCluster.GENERIC_CATEGORY,
        )
        session.add(keyword)
        session.flush()
        job = CollectionJob(
            idempotency_key=f"google-serp-runtime:{keyword.id}",
            job_type=CollectionJobType.SERP,
            source_tier=CollectionSourceTier.PUBLIC_PAGE,
            platform="google",
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
    factory: sessionmaker[Session],
    browser_factory: Callable[..., Any],
    *,
    settings: Settings | None = None,
) -> tuple[GoogleSerpExecutor, MemoryStore]:
    store = MemoryStore()
    return (
        GoogleSerpExecutor(
            settings=settings or _settings(),
            session_factory=factory,
            object_store=store,
            browser_session_factory=browser_factory,
        ),
        store,
    )


@pytest.mark.asyncio
async def test_executor_runs_one_raw_first_google_flow_with_lineage(engine: Engine) -> None:
    factory, keyword, claim = _claim(engine)
    browser = FakeBrowserSession(_capture())
    browser_kwargs: dict[str, object] = {}

    def browser_factory(**kwargs: object) -> FakeBrowserSession:
        browser_kwargs.update(kwargs)
        return browser

    executor, store = _executor(factory, browser_factory)
    result = await executor.execute(claim.item)

    assert result.quarantine is None
    assert result.metadata["publication"] == "created"
    assert browser.entered == browser.closed == 1
    assert len(browser.requests) == 1
    request = browser.requests[0]
    assert request.requested_url == "https://www.google.com/search?q=baby+wipes"
    assert request.profile.device_type is BrowserDeviceType.DESKTOP
    assert request.profile.country_code == "IN"
    assert request.profile.locale == "en-IN"
    assert browser_kwargs["max_concurrency"] == 1
    assert store.bodies == [BODY]
    with factory() as session:
        raw = session.scalars(select(RawEvidence)).one()
        parser = session.scalars(select(ParserVersion)).one()
        capture = session.scalars(select(GoogleSerpCapture)).one()
        assert capture.keyword_id == keyword.id
        assert capture.raw_evidence_id == raw.id
        assert capture.parser_version_id == parser.id
        assert capture.source_job_id == claim.job.id
        assert capture.result_count == 2
        assert [row.identity_match for row in capture.results] == ["novel", "competitor"]


@pytest.mark.asyncio
async def test_challenge_keeps_raw_evidence_without_google_rows(engine: Engine) -> None:
    factory, _, claim = _claim(engine)
    browser = FakeBrowserSession(_capture(challenge=True))
    executor, store = _executor(factory, lambda **_: browser)
    with pytest.raises(CollectionExecutionError) as raised:
        await executor.execute(claim.item)
    assert raised.value.code == "challenge_detected"
    assert browser.closed == 1
    assert store.bodies == [BODY]
    with factory() as session:
        assert len(session.scalars(select(RawEvidence)).all()) == 1
        assert session.scalars(select(GoogleSerpCapture)).all() == []
        assert session.scalars(select(GoogleSerpResult)).all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "failure_type", "code", "retryable"),
    [
        (
            BrowserNavigationTimeoutError("secret"),
            "timeout",
            "google_serp_navigation_timeout",
            True,
        ),
        (
            BrowserNavigationError("secret"),
            "network",
            "google_serp_navigation_failed",
            True,
        ),
        (
            BrowserConfigurationError("secret"),
            "validation_error",
            "google_serp_browser_configuration_invalid",
            False,
        ),
        (
            BrowserLifecycleError("secret"),
            "unknown",
            "google_serp_browser_unavailable",
            False,
        ),
    ],
)
async def test_executor_maps_browser_errors_and_closes(
    engine: Engine,
    error: Exception,
    failure_type: str,
    code: str,
    retryable: bool,
) -> None:
    factory, _, claim = _claim(engine)
    browser = RaisingBrowserSession(error)
    executor, _ = _executor(factory, lambda **_: browser)
    with pytest.raises(CollectionExecutionError) as raised:
        await executor.execute(claim.item)
    assert raised.value.failure_type.value == failure_type
    assert raised.value.code == code
    assert raised.value.retryable is retryable
    assert "secret" not in str(raised.value)
    assert browser.closed == 1


@pytest.mark.asyncio
async def test_missing_inactive_and_malformed_keyword_work_items_are_rejected(
    engine: Engine,
) -> None:
    factory, _, claim = _claim(engine)
    executor, _ = _executor(factory, lambda **_: FakeBrowserSession(_capture()))
    missing = CollectionWorkItem(**{**claim.item.__dict__, "keyword_id": uuid4()})
    with pytest.raises(CollectionExecutionError) as raised:
        await executor.execute(missing)
    assert raised.value.code == "google_serp_keyword_not_found"

    malformed = CollectionWorkItem(**{**claim.item.__dict__, "platform": "amazon_in"})
    with pytest.raises(CollectionExecutionError) as raised:
        await executor.execute(malformed)
    assert raised.value.code == "google_serp_invalid_work_item"

    with factory() as session:
        keyword = session.get(Keyword, claim.item.keyword_id)
        assert keyword is not None
        keyword.tracking_status = KeywordTrackingStatus.PAUSED
        session.commit()
    inactive, _ = _executor(factory, lambda **_: FakeBrowserSession(_capture()))
    with pytest.raises(CollectionExecutionError) as raised:
        await inactive.execute(claim.item)
    assert raised.value.code == "google_serp_keyword_inactive"


@pytest.mark.asyncio
async def test_mobile_profile_and_registry_coexist_with_amazon(engine: Engine) -> None:
    factory, _, claim = _claim(engine)
    browser = FakeBrowserSession(_capture())
    executor, _ = _executor(
        factory,
        lambda **_: browser,
        settings=_settings(google_serp_device_profile="mobile", google_serp_geo_code="MYS"),
    )
    await executor.execute(claim.item)
    assert browser.requests[0].profile.device_type is BrowserDeviceType.MOBILE
    assert browser.requests[0].profile.profile_id == "google-mobile-mys"
    importlib.reload(collection_tasks)
    assert isinstance(get_executor("google", CollectionJobType.SERP), GoogleSerpExecutor)
    assert get_executor("amazon_in", CollectionJobType.SERP) is not None
    assert get_executor("amazon_in", CollectionJobType.PRODUCT_DETAIL) is not None


@pytest.mark.asyncio
async def test_planned_google_job_claims_and_completes_offline_vertical(engine: Engine) -> None:
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
        product = Product(
            internal_sku="GOOGLE-ACCEPT-1",
            name="Novel Wipes",
            brand="Novel",
            category="Baby Care",
            marketplace=Marketplace.AMAZON_IN,
            marketplace_product_id="B0GOOGLE01",
            tracking_tier=TrackingTier.T1,
        )
        session.add_all([keyword, product])
        session.flush()
        session.add(
            TrackingTarget(
                keyword=keyword,
                product=product,
                cadence_minutes=60,
                enabled=True,
            )
        )
        session.flush()
        planned = CollectionPlanningService(session).plan_due(at=CAPTURED_AT)
        session.commit()
        google_job = next(job for job in planned.jobs if job.platform == "google")
        claim = CollectionLifecycleService(session).claim_attempt(
            google_job.id, worker_id="offline-test", at=CAPTURED_AT
        )
        assert claim is not None
        assert claim.item.keyword_id == keyword.id
        assert claim.item.attempt_id == claim.attempt.id
        session.commit()

    importlib.reload(collection_tasks)
    assert isinstance(get_executor("google", CollectionJobType.SERP), GoogleSerpExecutor)
    browser = FakeBrowserSession(_capture())
    executor, store = _executor(factory, lambda **_: browser)
    result = await executor.execute(claim.item)

    assert result.metadata["publication"] == "created"
    assert len(browser.requests) == 1
    assert store.bodies == [BODY]
    with factory() as session:
        raw = session.scalars(select(RawEvidence)).one()
        capture = session.scalars(select(GoogleSerpCapture)).one()
        assert capture.raw_evidence_id == raw.id
        assert capture.source_job_id == google_job.id
        assert capture.capture_metadata is not None
        assert capture.capture_metadata["attempt_id"] == str(claim.attempt.id)

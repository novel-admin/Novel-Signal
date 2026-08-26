"""Runtime wiring for one configured public Amazon India SERP collection job."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from novel_signal.collectors.amazon_serp import AmazonSerpCollectionRequest, AmazonSerpCollector
from novel_signal.collectors.base import CaptureRequest, CaptureResult
from novel_signal.collectors.playwright_browser import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
    BrowserConfigurationError,
    BrowserDeviceType,
    BrowserLifecycleError,
    BrowserNavigationError,
    BrowserNavigationTimeoutError,
    BrowserProfile,
    PlaywrightBrowserSession,
)
from novel_signal.config import Settings, get_settings
from novel_signal.db import SessionLocal
from novel_signal.modules.collection.execution import (
    CollectionExecutionError,
    CollectionExecutionResult,
    CollectionWorkItem,
)
from novel_signal.modules.collection.models import CollectionFailureType, CollectionJobType
from novel_signal.modules.collection.parsing import EnvelopeValidator, ParserRegistry
from novel_signal.modules.collection.pipeline import EvidencePipeline
from novel_signal.modules.collection.storage import RawObjectStore, S3RawObjectStore
from novel_signal.modules.keywords.models import Keyword
from novel_signal.modules.rank_visibility.models import DeviceProfile
from novel_signal.modules.rank_visibility.publication import (
    AmazonSerpPublicationConfig,
    AmazonSerpPublisher,
)
from novel_signal.parsers.amazon_serp import AmazonSerpParser


class BrowserSession(Protocol):
    async def __aenter__(self) -> BrowserSession: ...

    async def __aexit__(self, *_: object) -> None: ...

    async def capture(self, request: BrowserCaptureRequest) -> BrowserCaptureResult: ...


BrowserSessionFactory = Callable[..., BrowserSession]


class AmazonSerpExecutor:
    """Execute one allowlisted Amazon India SERP job through the raw-first pipeline."""

    PLATFORM = "amazon_in"
    PAGE_TYPE = "serp"
    PAGE_NUMBER = 1

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        session_factory: sessionmaker[Session] = SessionLocal,
        object_store: RawObjectStore | None = None,
        browser_session_factory: BrowserSessionFactory = PlaywrightBrowserSession,
    ) -> None:
        self.settings = settings or get_settings()
        self.session_factory = session_factory
        self.object_store = object_store or S3RawObjectStore()
        self.browser_session_factory = browser_session_factory

    async def execute(self, item: CollectionWorkItem) -> CollectionExecutionResult:
        self._validate_item(item)
        keyword = self._keyword(item)
        profile = self._profile()
        try:
            async with self.browser_session_factory(
                policy=AmazonSerpCollector._target_policy,
                max_concurrency=self.settings.amazon_in_concurrency,
                min_delay_seconds=self.settings.amazon_in_min_delay_seconds,
                navigation_timeout_seconds=self.settings.collector_timeout_seconds,
            ) as browser:
                captured = await AmazonSerpCollector(browser).capture(
                    AmazonSerpCollectionRequest(
                        keyword_id=keyword.id,
                        query=keyword.keyword_text,
                        profile=profile,
                        page_number=self.PAGE_NUMBER,
                    )
                )
        except BrowserNavigationTimeoutError:
            raise CollectionExecutionError(
                "Amazon SERP collection timed out",
                failure_type=CollectionFailureType.TIMEOUT,
                code="amazon_serp_navigation_timeout",
                retryable=True,
            ) from None
        except BrowserNavigationError:
            raise CollectionExecutionError(
                "Amazon SERP navigation failed",
                failure_type=CollectionFailureType.NETWORK,
                code="amazon_serp_navigation_failed",
                retryable=True,
            ) from None
        except (BrowserLifecycleError, BrowserConfigurationError):
            raise CollectionExecutionError(
                "Amazon SERP browser configuration failed",
                failure_type=CollectionFailureType.UNKNOWN,
                code="amazon_serp_browser_unavailable",
                retryable=False,
            ) from None
        except Exception:
            raise CollectionExecutionError(
                "Amazon SERP browser capture failed",
                failure_type=CollectionFailureType.UNKNOWN,
                code="amazon_serp_browser_failed",
                retryable=False,
            ) from None

        registry = ParserRegistry()
        registry.register(AmazonSerpParser(page_number=self.PAGE_NUMBER))
        pipeline = EvidencePipeline(
            parser_registry=registry,
            object_store=self.object_store,
            session_factory=self.session_factory,
        )
        publisher = AmazonSerpPublisher(
            config=AmazonSerpPublicationConfig(
                keyword_id=keyword.id,
                geo_code=self.settings.amazon_in_geo_code,
                device_profile=_rank_device_profile(profile.device_type),
                query=keyword.keyword_text,
                page_number=self.PAGE_NUMBER,
                profile_id=profile.profile_id,
                pincode=_optional_value(self.settings.amazon_in_pincode),
                location_label=_optional_value(self.settings.amazon_in_location_label),
            ),
            session_factory=self.session_factory,
        )
        browser_capture = captured.browser_capture
        try:
            return pipeline.process(
                job_id=item.job_id,
                attempt_id=item.attempt_id,
                platform=self.PLATFORM,
                request=CaptureRequest(
                    url=browser_capture.requested_url,
                    target_id=str(keyword.id),
                    page_type=self.PAGE_TYPE,
                ),
                capture=CaptureResult(
                    final_url=browser_capture.final_url,
                    body=browser_capture.html,
                    content_type=browser_capture.content_type,
                    challenge_detected=browser_capture.challenge_detected,
                ),
                validator=EnvelopeValidator(
                    required_fields=(
                        "absolute_position",
                        "page_number",
                        "marketplace_product_id",
                        "placement_type",
                    )
                ),
                publisher=publisher,
                captured_at=browser_capture.captured_at,
            )
        except CollectionExecutionError:
            raise
        except Exception:
            raise CollectionExecutionError(
                "Amazon SERP evidence processing failed",
                failure_type=CollectionFailureType.UNKNOWN,
                code="amazon_serp_processing_failed",
                retryable=False,
            ) from None

    def _validate_item(self, item: CollectionWorkItem) -> None:
        if item.job_type is not CollectionJobType.SERP or item.platform != self.PLATFORM:
            raise CollectionExecutionError(
                "Collection work item is not an Amazon SERP job",
                failure_type=CollectionFailureType.UNKNOWN,
                code="amazon_serp_invalid_work_item",
                retryable=False,
            )
        if item.keyword_id is None:
            raise CollectionExecutionError(
                "Amazon SERP collection requires a keyword",
                failure_type=CollectionFailureType.UNKNOWN,
                code="amazon_serp_keyword_required",
                retryable=False,
            )

    def _keyword(self, item: CollectionWorkItem) -> Keyword:
        assert item.keyword_id is not None
        with self.session_factory() as session:
            keyword = session.get(Keyword, item.keyword_id)
            if keyword is None:
                raise CollectionExecutionError(
                    "Amazon SERP keyword was not found",
                    failure_type=CollectionFailureType.UNKNOWN,
                    code="amazon_serp_keyword_not_found",
                    retryable=False,
                )
            session.expunge(keyword)
            return keyword

    def _profile(self) -> BrowserProfile:
        try:
            device = BrowserDeviceType(self.settings.amazon_in_device_profile.strip().lower())
        except ValueError:
            raise CollectionExecutionError(
                "Amazon SERP device profile must be desktop or mobile",
                failure_type=CollectionFailureType.UNKNOWN,
                code="amazon_serp_device_profile_invalid",
                retryable=False,
            ) from None
        geo_code = self.settings.amazon_in_geo_code.strip()
        if not geo_code:
            raise CollectionExecutionError(
                "Amazon SERP geo code is required",
                failure_type=CollectionFailureType.UNKNOWN,
                code="amazon_serp_geo_code_required",
                retryable=False,
            )
        return BrowserProfile(
            profile_id=f"amazon-in-{device.value}-{geo_code.lower()}",
            device_type=device,
            country_code=geo_code,
            pincode=_optional_value(self.settings.amazon_in_pincode),
            location_label=_optional_value(self.settings.amazon_in_location_label),
        )


def _optional_value(value: str) -> str | None:
    normalized = value.strip()
    return normalized or None


def _rank_device_profile(device: BrowserDeviceType) -> DeviceProfile:
    return DeviceProfile(device.value)

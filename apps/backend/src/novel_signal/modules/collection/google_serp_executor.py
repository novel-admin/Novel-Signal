"""Runtime wiring for one configured public Google organic SERP job."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from novel_signal.collectors.base import CaptureRequest, CaptureResult
from novel_signal.collectors.google_serp import GoogleSerpCollectionRequest, GoogleSerpCollector
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
    UnsupportedTargetError,
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
from novel_signal.modules.keywords.models import Keyword, KeywordTrackingStatus
from novel_signal.modules.rank_visibility.google_publication import (
    GoogleSerpPublicationConfig,
    GoogleSerpPublisher,
)
from novel_signal.modules.rank_visibility.models import DeviceProfile
from novel_signal.parsers.google_serp import GoogleSerpParser


class BrowserSession(Protocol):
    async def __aenter__(self) -> BrowserSession: ...

    async def __aexit__(self, *_: object) -> None: ...

    async def capture(self, request: BrowserCaptureRequest) -> BrowserCaptureResult: ...


BrowserSessionFactory = Callable[..., BrowserSession]


class GoogleSerpExecutor:
    PLATFORM = "google"
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
        parser = self._parser()
        try:
            async with self.browser_session_factory(
                policy=GoogleSerpCollector._target_policy,
                max_concurrency=self.settings.google_serp_concurrency,
                min_delay_seconds=self.settings.google_serp_min_delay_seconds,
                navigation_timeout_seconds=self.settings.collector_timeout_seconds,
            ) as browser:
                captured = await GoogleSerpCollector(browser).capture(
                    GoogleSerpCollectionRequest(
                        keyword_id=keyword.id,
                        query=keyword.keyword_text,
                        profile=profile,
                        page_number=self.PAGE_NUMBER,
                    )
                )
        except BrowserNavigationTimeoutError:
            raise CollectionExecutionError(
                "Google SERP collection timed out",
                failure_type=CollectionFailureType.TIMEOUT,
                code="google_serp_navigation_timeout",
                retryable=True,
            ) from None
        except BrowserNavigationError:
            raise CollectionExecutionError(
                "Google SERP navigation failed",
                failure_type=CollectionFailureType.NETWORK,
                code="google_serp_navigation_failed",
                retryable=True,
            ) from None
        except (BrowserConfigurationError, UnsupportedTargetError):
            raise CollectionExecutionError(
                "Google SERP browser configuration is invalid",
                failure_type=CollectionFailureType.VALIDATION_ERROR,
                code="google_serp_browser_configuration_invalid",
                retryable=False,
            ) from None
        except BrowserLifecycleError:
            raise CollectionExecutionError(
                "Google SERP browser is unavailable",
                failure_type=CollectionFailureType.UNKNOWN,
                code="google_serp_browser_unavailable",
                retryable=False,
            ) from None
        except Exception:
            raise CollectionExecutionError(
                "Google SERP browser capture failed",
                failure_type=CollectionFailureType.UNKNOWN,
                code="google_serp_browser_failed",
                retryable=False,
            ) from None

        registry = ParserRegistry()
        registry.register(parser)
        pipeline = EvidencePipeline(
            parser_registry=registry,
            object_store=self.object_store,
            session_factory=self.session_factory,
        )
        publisher = GoogleSerpPublisher(
            config=GoogleSerpPublicationConfig(
                keyword_id=keyword.id,
                geo_code=self.settings.google_serp_geo_code,
                device_profile=DeviceProfile(profile.device_type.value),
                query=keyword.keyword_text,
                page_number=self.PAGE_NUMBER,
                profile_id=profile.profile_id,
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
                        "result_type",
                        "title",
                        "url",
                        "displayed_domain",
                    )
                ),
                publisher=publisher,
                captured_at=browser_capture.captured_at,
            )
        except CollectionExecutionError:
            raise
        except Exception:
            raise CollectionExecutionError(
                "Google SERP evidence processing failed",
                failure_type=CollectionFailureType.UNKNOWN,
                code="google_serp_processing_failed",
                retryable=False,
            ) from None

    def _validate_item(self, item: CollectionWorkItem) -> None:
        if item.job_type is not CollectionJobType.SERP or item.platform != self.PLATFORM:
            raise CollectionExecutionError(
                "Collection work item is not a Google SERP job",
                failure_type=CollectionFailureType.VALIDATION_ERROR,
                code="google_serp_invalid_work_item",
                retryable=False,
            )
        if item.keyword_id is None:
            raise CollectionExecutionError(
                "Google SERP collection requires a keyword",
                failure_type=CollectionFailureType.VALIDATION_ERROR,
                code="google_serp_keyword_required",
                retryable=False,
            )
        if item.product_id is not None or item.competitor_product_id is not None:
            raise CollectionExecutionError(
                "Google SERP collection does not accept a product subject",
                failure_type=CollectionFailureType.VALIDATION_ERROR,
                code="google_serp_product_subject_invalid",
                retryable=False,
            )

    def _keyword(self, item: CollectionWorkItem) -> Keyword:
        assert item.keyword_id is not None
        with self.session_factory() as session:
            keyword = session.get(Keyword, item.keyword_id)
            if keyword is None:
                raise CollectionExecutionError(
                    "Google SERP keyword was not found",
                    failure_type=CollectionFailureType.VALIDATION_ERROR,
                    code="google_serp_keyword_not_found",
                    retryable=False,
                )
            if (
                keyword.archived_at is not None
                or keyword.tracking_status is not KeywordTrackingStatus.ACTIVE
            ):
                raise CollectionExecutionError(
                    "Google SERP keyword is not active",
                    failure_type=CollectionFailureType.VALIDATION_ERROR,
                    code="google_serp_keyword_inactive",
                    retryable=False,
                )
            session.expunge(keyword)
            return keyword

    def _profile(self) -> BrowserProfile:
        try:
            device = BrowserDeviceType(self.settings.google_serp_device_profile.strip().lower())
        except ValueError:
            raise CollectionExecutionError(
                "Google SERP device profile must be desktop or mobile",
                failure_type=CollectionFailureType.VALIDATION_ERROR,
                code="google_serp_device_profile_invalid",
                retryable=False,
            ) from None
        geo_code = self.settings.google_serp_geo_code.strip()
        if not geo_code:
            raise CollectionExecutionError(
                "Google SERP geo code is required",
                failure_type=CollectionFailureType.VALIDATION_ERROR,
                code="google_serp_geo_code_required",
                retryable=False,
            )
        try:
            return BrowserProfile(
                profile_id=f"google-{device.value}-{geo_code.lower()}",
                device_type=device,
                locale=self.settings.google_serp_locale,
                timezone_id=self.settings.google_serp_timezone_id,
                country_code="IN",
            )
        except BrowserConfigurationError:
            raise CollectionExecutionError(
                "Google SERP browser profile is invalid",
                failure_type=CollectionFailureType.VALIDATION_ERROR,
                code="google_serp_profile_invalid",
                retryable=False,
            ) from None

    def _parser(self) -> GoogleSerpParser:
        try:
            return GoogleSerpParser(
                page_number=self.PAGE_NUMBER,
                novel_domains=_domains(self.settings.google_serp_novel_domains),
                competitor_domains=_domains(self.settings.google_serp_competitor_domains),
            )
        except ValueError:
            raise CollectionExecutionError(
                "Google SERP identity-domain configuration is invalid",
                failure_type=CollectionFailureType.VALIDATION_ERROR,
                code="google_serp_identity_domains_invalid",
                retryable=False,
            ) from None


def _domains(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())

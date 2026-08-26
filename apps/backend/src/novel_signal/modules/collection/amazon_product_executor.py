"""Runtime wiring for one configured public Amazon India product-detail job."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from novel_signal.collectors.amazon_product import (
    AmazonProductCollectionRequest,
    AmazonProductCollector,
)
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
    UnsupportedTargetError,
)
from novel_signal.config import Settings, get_settings
from novel_signal.db import SessionLocal
from novel_signal.modules.collection.amazon_product_publication import (
    AmazonProductPublicationConfig,
    AmazonProductPublisher,
)
from novel_signal.modules.collection.execution import (
    CollectionExecutionError,
    CollectionExecutionResult,
    CollectionWorkItem,
)
from novel_signal.modules.collection.models import CollectionFailureType, CollectionJobType
from novel_signal.modules.collection.parsing import EnvelopeValidator, ParserRegistry
from novel_signal.modules.collection.pipeline import EvidencePipeline
from novel_signal.modules.collection.storage import RawObjectStore, S3RawObjectStore
from novel_signal.modules.universe.models import CompetitorProduct, Marketplace, Product
from novel_signal.parsers.amazon_product import AmazonProductParser

_ASIN = re.compile(r"^[A-Z0-9]{10}$")


class BrowserSession(Protocol):
    async def __aenter__(self) -> BrowserSession: ...

    async def __aexit__(self, *_: object) -> None: ...

    async def capture(self, request: BrowserCaptureRequest) -> BrowserCaptureResult: ...


BrowserSessionFactory = Callable[..., BrowserSession]


@dataclass(frozen=True)
class _Target:
    marketplace_product_id: str
    product_id: UUID | None
    competitor_product_id: UUID | None


class AmazonProductExecutor:
    """Execute one Amazon product-detail work item through the raw-first pipeline."""

    PLATFORM = "amazon_in"
    PAGE_TYPE = "product_detail"

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
        attempt_id = item.attempt_id
        if attempt_id is None:
            raise self._target_invalid()
        target = self._target(item)
        profile = self._profile()
        try:
            async with self.browser_session_factory(
                policy=AmazonProductCollector._target_policy,
                max_concurrency=self.settings.amazon_in_concurrency,
                min_delay_seconds=self.settings.amazon_in_min_delay_seconds,
                navigation_timeout_seconds=self.settings.collector_timeout_seconds,
            ) as browser:
                captured = await AmazonProductCollector(browser).capture(
                    AmazonProductCollectionRequest(
                        marketplace_product_id=target.marketplace_product_id,
                        product_id=target.product_id,
                        competitor_product_id=target.competitor_product_id,
                        profile=profile,
                        capture_screenshot=False,
                    )
                )
        except BrowserNavigationTimeoutError:
            raise self._error(
                "Amazon product collection timed out",
                CollectionFailureType.TIMEOUT,
                "amazon_product_navigation_timeout",
                True,
            ) from None
        except BrowserNavigationError:
            raise self._error(
                "Amazon product navigation failed",
                CollectionFailureType.NETWORK,
                "amazon_product_navigation_failed",
                True,
            ) from None
        except (BrowserConfigurationError, UnsupportedTargetError):
            raise self._error(
                "Amazon product browser configuration failed",
                CollectionFailureType.VALIDATION_ERROR,
                "amazon_product_browser_configuration_invalid",
                False,
            ) from None
        except BrowserLifecycleError:
            raise self._error(
                "Amazon product browser is unavailable",
                CollectionFailureType.UNKNOWN,
                "amazon_product_browser_unavailable",
                False,
            ) from None
        except Exception:
            raise self._error(
                "Amazon product browser capture failed",
                CollectionFailureType.UNKNOWN,
                "amazon_product_browser_failed",
                False,
            ) from None

        registry = ParserRegistry()
        registry.register(AmazonProductParser())
        pipeline = EvidencePipeline(
            parser_registry=registry,
            object_store=self.object_store,
            session_factory=self.session_factory,
        )
        publisher = AmazonProductPublisher(
            config=AmazonProductPublicationConfig(
                marketplace_product_id=target.marketplace_product_id,
                geo_code=self.settings.amazon_in_geo_code.strip() or None,
                device_profile=profile.device_type.value,
                product_id=target.product_id,
                competitor_product_id=target.competitor_product_id,
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
                attempt_id=attempt_id,
                platform=self.PLATFORM,
                request=CaptureRequest(
                    url=browser_capture.requested_url,
                    target_id=str(target.product_id or target.competitor_product_id),
                    page_type=self.PAGE_TYPE,
                ),
                capture=CaptureResult(
                    final_url=browser_capture.final_url,
                    body=browser_capture.html,
                    content_type=browser_capture.content_type,
                    challenge_detected=browser_capture.challenge_detected,
                ),
                validator=EnvelopeValidator(
                    required_fields=("marketplace_product_id",), minimum_rows=1
                ),
                publisher=publisher,
                captured_at=browser_capture.captured_at,
            )
        except CollectionExecutionError:
            raise
        except Exception:
            raise self._error(
                "Amazon product evidence processing failed",
                CollectionFailureType.UNKNOWN,
                "amazon_product_processing_failed",
                False,
            ) from None

    def _validate_item(self, item: CollectionWorkItem) -> None:
        if (
            item.platform != self.PLATFORM
            or item.job_type is not CollectionJobType.PRODUCT_DETAIL
            or item.job_id is None
            or item.attempt_id is None
            or (item.product_id is None) == (item.competitor_product_id is None)
        ):
            raise self._target_invalid()

    def _target(self, item: CollectionWorkItem) -> _Target:
        with self.session_factory() as session:
            model: Product | CompetitorProduct | None
            if item.product_id is not None:
                model = session.get(Product, item.product_id)
            else:
                assert item.competitor_product_id is not None
                model = session.get(CompetitorProduct, item.competitor_product_id)
            marketplace_product_id = (
                model.marketplace_product_id.strip().upper()
                if model is not None and model.marketplace_product_id is not None
                else ""
            )
            if (
                model is None
                or model.archived_at is not None
                or model.marketplace is not Marketplace.AMAZON_IN
                or not _ASIN.fullmatch(marketplace_product_id)
            ):
                raise self._target_invalid()
            return _Target(
                marketplace_product_id=marketplace_product_id,
                product_id=item.product_id,
                competitor_product_id=item.competitor_product_id,
            )

    def _profile(self) -> BrowserProfile:
        try:
            device = BrowserDeviceType(self.settings.amazon_in_device_profile.strip().lower())
        except ValueError:
            raise self._error(
                "Amazon product device profile must be desktop or mobile",
                CollectionFailureType.VALIDATION_ERROR,
                "amazon_product_device_profile_invalid",
                False,
            ) from None
        geo_code = self.settings.amazon_in_geo_code.strip()
        if not geo_code:
            raise self._error(
                "Amazon product geo code is required",
                CollectionFailureType.VALIDATION_ERROR,
                "amazon_product_geo_code_required",
                False,
            )
        return BrowserProfile(
            profile_id=f"amazon-in-{device.value}-{geo_code.lower()}",
            device_type=device,
            country_code="IN",
            pincode=_optional_value(self.settings.amazon_in_pincode),
            location_label=_optional_value(self.settings.amazon_in_location_label),
        )

    def _target_invalid(self) -> CollectionExecutionError:
        return self._error(
            "Amazon product collection target is invalid",
            CollectionFailureType.VALIDATION_ERROR,
            "product_detail_target_invalid",
            False,
        )

    @staticmethod
    def _error(
        message: str, failure_type: CollectionFailureType, code: str, retryable: bool
    ) -> CollectionExecutionError:
        return CollectionExecutionError(
            message, failure_type=failure_type, code=code, retryable=retryable
        )


def _optional_value(value: str) -> str | None:
    normalized = value.strip()
    return normalized or None

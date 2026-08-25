"""Public Amazon India product-detail collector wrapper.

This collector only builds the canonical public product URL and delegates one
navigation to the supplied browser client. It does not parse or persist output.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from novel_signal.collectors.playwright_browser import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
    BrowserProfile,
    BrowserTargetPolicy,
)

_ASIN = re.compile(r"^[A-Z0-9]{10}$")


class BrowserCaptureClient(Protocol):
    """Small seam for the shared browser session and deterministic tests."""

    def capture(self, request: BrowserCaptureRequest) -> Awaitable[BrowserCaptureResult]: ...


@dataclass(frozen=True)
class AmazonProductCollectionRequest:
    marketplace_product_id: str
    profile: BrowserProfile
    capture_screenshot: bool = False
    product_id: UUID | None = None
    competitor_product_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.product_id is not None and self.competitor_product_id is not None:
            raise ValueError("Amazon product request cannot target both product identities")
        object.__setattr__(
            self,
            "marketplace_product_id",
            _normalize_asin(self.marketplace_product_id),
        )


@dataclass(frozen=True)
class AmazonProductCapture:
    """Normalized identity plus the exact browser result returned by the client."""

    marketplace_product_id: str
    browser_capture: BrowserCaptureResult
    product_id: UUID | None = None
    competitor_product_id: UUID | None = None


class AmazonProductCollector:
    """Capture one canonical public Amazon India product detail page."""

    _target_policy = BrowserTargetPolicy(
        allowed_domains=frozenset({"amazon.in"}),
        allowed_page_types=frozenset({"product_detail"}),
    )

    def __init__(self, browser: BrowserCaptureClient) -> None:
        self._browser = browser

    async def capture(self, request: AmazonProductCollectionRequest) -> AmazonProductCapture:
        requested_url = amazon_product_url(marketplace_product_id=request.marketplace_product_id)
        self._target_policy.validate(url=requested_url, page_type="product_detail")
        browser_capture = await self._browser.capture(
            BrowserCaptureRequest(
                requested_url=requested_url,
                page_type="product_detail",
                profile=request.profile,
                capture_screenshot=request.capture_screenshot,
            )
        )
        return AmazonProductCapture(
            marketplace_product_id=request.marketplace_product_id,
            product_id=request.product_id,
            competitor_product_id=request.competitor_product_id,
            browser_capture=browser_capture,
        )


def amazon_product_url(*, marketplace_product_id: str) -> str:
    """Build the sole canonical public Amazon India product endpoint."""
    return f"https://www.amazon.in/dp/{_normalize_asin(marketplace_product_id)}"


def _normalize_asin(value: str) -> str:
    normalized = value.strip().upper()
    if not _ASIN.fullmatch(normalized):
        raise ValueError("Amazon marketplace product identity must be a valid ASIN")
    return normalized

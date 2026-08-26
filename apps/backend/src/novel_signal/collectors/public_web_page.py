"""Strictly allowlisted public competitor website collector."""

from __future__ import annotations

from collections.abc import Awaitable, Iterable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from novel_signal.collectors.playwright_browser import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
    BrowserProfile,
    BrowserTargetPolicy,
    UnsupportedTargetError,
)


class BrowserCaptureClient(Protocol):
    def capture(self, request: BrowserCaptureRequest) -> Awaitable[BrowserCaptureResult]: ...


@dataclass(frozen=True)
class PublicWebPageCollectionRequest:
    url: str
    profile: BrowserProfile
    capture_screenshot: bool = False
    competitor_id: UUID | None = None

    def __post_init__(self) -> None:
        normalized = self.url.strip()
        if not normalized:
            raise ValueError("Public website URL must not be blank")
        object.__setattr__(self, "url", normalized)


@dataclass(frozen=True)
class PublicWebPageCapture:
    url: str
    browser_capture: BrowserCaptureResult
    competitor_id: UUID | None = None


class PublicWebPageCollector:
    """Capture one public page without permitting caller-controlled target scope."""

    def __init__(self, browser: BrowserCaptureClient, *, allowed_domains: Iterable[str]) -> None:
        self._browser = browser
        self.target_policy = BrowserTargetPolicy(
            allowed_domains=frozenset(allowed_domains),
            allowed_page_types=frozenset({"public_web_page"}),
        )

    async def capture(self, request: PublicWebPageCollectionRequest) -> PublicWebPageCapture:
        self.target_policy.validate(url=request.url, page_type="public_web_page")
        browser_capture = await self._browser.capture(
            BrowserCaptureRequest(
                requested_url=request.url,
                page_type="public_web_page",
                profile=request.profile,
                capture_screenshot=request.capture_screenshot,
            )
        )
        try:
            self.target_policy.validate(
                url=browser_capture.final_url,
                page_type="public_web_page",
            )
        except UnsupportedTargetError:
            raise UnsupportedTargetError(
                "Public website redirect left the configured allowlist."
            ) from None
        return PublicWebPageCapture(
            url=request.url,
            competitor_id=request.competitor_id,
            browser_capture=browser_capture,
        )

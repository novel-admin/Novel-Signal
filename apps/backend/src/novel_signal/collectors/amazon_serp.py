"""Public Amazon India SERP collector wrapper.

The collector builds an allowlisted search URL and delegates navigation to the
shared Playwright browser foundation. It intentionally does not parse or persist
the returned HTML.
"""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode
from uuid import UUID

from novel_signal.collectors.playwright_browser import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
    BrowserProfile,
    BrowserTargetPolicy,
)


class BrowserCaptureClient(Protocol):
    """Small seam for the existing browser session and deterministic unit tests."""

    def capture(self, request: BrowserCaptureRequest) -> Awaitable[BrowserCaptureResult]: ...


@dataclass(frozen=True)
class AmazonSerpCollectionRequest:
    keyword_id: UUID
    query: str
    profile: BrowserProfile
    page_number: int = 1
    capture_screenshot: bool = False

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("Amazon SERP query must not be blank")
        if self.page_number < 1:
            raise ValueError("Amazon SERP page number must be positive")


@dataclass(frozen=True)
class AmazonSerpCapture:
    """Request context plus the one unmodified browser capture result."""

    keyword_id: UUID
    query: str
    page_number: int
    browser_capture: BrowserCaptureResult


class AmazonSerpCollector:
    """Capture one public Amazon India SERP through the shared browser session."""

    _target_policy = BrowserTargetPolicy(
        allowed_domains=frozenset({"amazon.in"}),
        allowed_page_types=frozenset({"serp"}),
    )

    def __init__(self, browser: BrowserCaptureClient) -> None:
        self._browser = browser

    async def capture(self, request: AmazonSerpCollectionRequest) -> AmazonSerpCapture:
        requested_url = amazon_search_url(query=request.query, page_number=request.page_number)
        self._target_policy.validate(url=requested_url, page_type="serp")
        browser_capture = await self._browser.capture(
            BrowserCaptureRequest(
                requested_url=requested_url,
                page_type="serp",
                profile=request.profile,
                capture_screenshot=request.capture_screenshot,
            )
        )
        return AmazonSerpCapture(
            keyword_id=request.keyword_id,
            query=request.query,
            page_number=request.page_number,
            browser_capture=browser_capture,
        )


def amazon_search_url(*, query: str, page_number: int = 1) -> str:
    """Build the only public endpoint this collector can request."""
    if not query.strip():
        raise ValueError("Amazon SERP query must not be blank")
    if page_number < 1:
        raise ValueError("Amazon SERP page number must be positive")
    parameters: list[tuple[str, str]] = [("k", query)]
    if page_number > 1:
        parameters.append(("page", str(page_number)))
    return f"https://www.amazon.in/s?{urlencode(parameters)}"

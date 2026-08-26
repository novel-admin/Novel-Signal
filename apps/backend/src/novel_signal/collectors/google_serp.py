"""Public Google organic-SERP collector wrapper with no parsing or persistence."""

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
    """Minimal browser seam for deterministic callers and tests."""

    def capture(self, request: BrowserCaptureRequest) -> Awaitable[BrowserCaptureResult]: ...


@dataclass(frozen=True)
class GoogleSerpCollectionRequest:
    query: str
    profile: BrowserProfile
    page_number: int = 1
    capture_screenshot: bool = False
    keyword_id: UUID | None = None

    def __post_init__(self) -> None:
        normalized = self.query.strip()
        if not normalized:
            raise ValueError("Google SERP query must not be blank")
        if self.page_number < 1:
            raise ValueError("Google SERP page number must be positive")
        object.__setattr__(self, "query", normalized)


@dataclass(frozen=True)
class GoogleSerpCapture:
    query: str
    page_number: int
    keyword_id: UUID | None
    browser_capture: BrowserCaptureResult


class GoogleSerpCollector:
    """Build one allowlisted Google search request through a supplied browser client."""

    _target_policy = BrowserTargetPolicy(
        allowed_domains=frozenset({"google.com"}),
        allowed_page_types=frozenset({"serp"}),
    )

    def __init__(self, browser: BrowserCaptureClient) -> None:
        self._browser = browser

    async def capture(self, request: GoogleSerpCollectionRequest) -> GoogleSerpCapture:
        requested_url = google_search_url(query=request.query, page_number=request.page_number)
        self._target_policy.validate(url=requested_url, page_type="serp")
        browser_capture = await self._browser.capture(
            BrowserCaptureRequest(
                requested_url=requested_url,
                page_type="serp",
                profile=request.profile,
                capture_screenshot=request.capture_screenshot,
            )
        )
        return GoogleSerpCapture(
            query=request.query,
            page_number=request.page_number,
            keyword_id=request.keyword_id,
            browser_capture=browser_capture,
        )


def google_search_url(*, query: str, page_number: int = 1) -> str:
    """Build the sole public Google search endpoint with deterministic pagination."""
    normalized = query.strip()
    if not normalized:
        raise ValueError("Google SERP query must not be blank")
    if page_number < 1:
        raise ValueError("Google SERP page number must be positive")
    parameters: list[tuple[str, str]] = [("q", normalized)]
    if page_number > 1:
        parameters.append(("start", str((page_number - 1) * 10)))
    return f"https://www.google.com/search?{urlencode(parameters)}"

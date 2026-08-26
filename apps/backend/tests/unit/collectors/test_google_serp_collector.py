from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest
from novel_signal.collectors.google_serp import (
    GoogleSerpCollectionRequest,
    GoogleSerpCollector,
    google_search_url,
)
from novel_signal.collectors.playwright_browser import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
    BrowserProfile,
    ChallengeKind,
    ChallengeState,
)

KEYWORD_ID = UUID("12345678-1234-5678-1234-567812345678")
PROFILE = BrowserProfile(profile_id="google-desktop")


class FakeBrowser:
    def __init__(self, result: BrowserCaptureResult) -> None:
        self.result = result
        self.requests: list[BrowserCaptureRequest] = []

    async def capture(self, request: BrowserCaptureRequest) -> BrowserCaptureResult:
        self.requests.append(request)
        return self.result


def capture_result(*, challenge: ChallengeState | None = None) -> BrowserCaptureResult:
    return BrowserCaptureResult(
        requested_url="https://www.google.com/search?q=fixture",
        final_url="https://www.google.com/search?q=fixture&redirect=1",
        status=200,
        html=b"<html>exact bytes</html>",
        content_type="text/html",
        captured_at=datetime(2026, 8, 31, tzinfo=UTC),
        page_type="serp",
        profile_id=PROFILE.profile_id,
        challenge=challenge or ChallengeState(),
        screenshot=b"exact screenshot",
    )


def request(**changes: object) -> GoogleSerpCollectionRequest:
    values: dict[str, object] = {
        "query": "baby wipes",
        "profile": PROFILE,
        "keyword_id": KEYWORD_ID,
    }
    values.update(changes)
    return GoogleSerpCollectionRequest(**values)  # type: ignore[arg-type]


def test_google_url_is_canonical_paged_and_deterministic() -> None:
    assert google_search_url(query="baby wipes") == "https://www.google.com/search?q=baby+wipes"
    assert google_search_url(query="baby wipes", page_number=2) == (
        "https://www.google.com/search?q=baby+wipes&start=10"
    )
    assert google_search_url(query="baby wipes", page_number=3) == (
        "https://www.google.com/search?q=baby+wipes&start=20"
    )
    assert google_search_url(query="baby wipes") == google_search_url(query="baby wipes")


def test_query_is_trimmed_encoded_and_cannot_control_host_or_path() -> None:
    item = request(query="  wipes & https://evil.example/x?y=1  ")
    url = google_search_url(query=item.query)
    parsed = urlsplit(url)
    assert item.query == "wipes & https://evil.example/x?y=1"
    assert parsed.scheme == "https"
    assert parsed.hostname == "www.google.com"
    assert parsed.path == "/search"
    assert parse_qs(parsed.query) == {"q": [item.query]}


def test_request_is_immutable_after_query_normalization() -> None:
    item = request(query="  baby wipes  ")

    assert item.query == "baby wipes"
    with pytest.raises(FrozenInstanceError):
        item.query = "another query"  # type: ignore[misc]


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_blank_query_is_rejected(query: str) -> None:
    with pytest.raises(ValueError, match="query"):
        request(query=query)
    with pytest.raises(ValueError, match="query"):
        google_search_url(query=query)


@pytest.mark.parametrize("page_number", [0, -1])
def test_invalid_page_number_is_rejected(page_number: int) -> None:
    with pytest.raises(ValueError, match="page number"):
        request(page_number=page_number)
    with pytest.raises(ValueError, match="page number"):
        google_search_url(query="wipes", page_number=page_number)


@pytest.mark.asyncio
async def test_collector_forwards_one_canonical_request_and_exact_capture() -> None:
    browser = FakeBrowser(capture_result())
    collector = GoogleSerpCollector(browser)
    item = request(query="  baby wipes  ", page_number=2, capture_screenshot=True)

    result = await collector.capture(item)

    assert result.query == "baby wipes"
    assert result.page_number == 2
    assert result.keyword_id == KEYWORD_ID
    assert result.browser_capture is browser.result
    assert result.browser_capture.html is browser.result.html
    assert result.browser_capture.screenshot is browser.result.screenshot
    assert result.browser_capture.final_url == "https://www.google.com/search?q=fixture&redirect=1"
    assert browser.requests == [
        BrowserCaptureRequest(
            requested_url="https://www.google.com/search?q=baby+wipes&start=10",
            page_type="serp",
            profile=PROFILE,
            capture_screenshot=True,
        )
    ]


@pytest.mark.asyncio
async def test_challenge_is_preserved_without_inspection_or_retry() -> None:
    challenge = ChallengeState(ChallengeKind.CAPTCHA, "captcha")
    browser = FakeBrowser(capture_result(challenge=challenge))
    result = await GoogleSerpCollector(browser).capture(request())
    assert result.browser_capture.challenge is challenge
    assert result.browser_capture.challenge_detected is True
    assert len(browser.requests) == 1

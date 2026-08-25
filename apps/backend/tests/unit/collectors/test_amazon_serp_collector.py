from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest
from novel_signal.collectors.amazon_serp import (
    AmazonSerpCollectionRequest,
    AmazonSerpCollector,
    amazon_search_url,
)
from novel_signal.collectors.playwright_browser import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
    BrowserProfile,
    ChallengeKind,
    ChallengeState,
)


class FakeBrowserCaptureClient:
    def __init__(self, result: BrowserCaptureResult) -> None:
        self.result = result
        self.requests: list[BrowserCaptureRequest] = []

    async def capture(self, request: BrowserCaptureRequest) -> BrowserCaptureResult:
        self.requests.append(request)
        return self.result


KEYWORD_ID = UUID("12345678-1234-5678-1234-567812345678")
PROFILE = BrowserProfile(profile_id="desktop-mysore", pincode="570001", location_label="Mysore")


def capture_result(*, challenge: ChallengeState | None = None) -> BrowserCaptureResult:
    return BrowserCaptureResult(
        requested_url="https://www.amazon.in/s?k=fixture",
        final_url="https://www.amazon.in/s?k=fixture&ref=redirect",
        status=200,
        html=b"<html>fixture</html>",
        content_type="text/html",
        captured_at=datetime(2026, 8, 27, tzinfo=UTC),
        page_type="serp",
        profile_id=PROFILE.profile_id,
        challenge=challenge or ChallengeState(),
    )


def collection_request(**changes: object) -> AmazonSerpCollectionRequest:
    values: dict[str, object] = {
        "keyword_id": KEYWORD_ID,
        "query": "baby wipes",
        "profile": PROFILE,
    }
    values.update(changes)
    return AmazonSerpCollectionRequest(**values)  # type: ignore[arg-type]


def test_amazon_search_url_is_deterministic_and_uses_only_public_serp_endpoint() -> None:
    assert amazon_search_url(query="baby wipes") == "https://www.amazon.in/s?k=baby+wipes"
    assert amazon_search_url(query="baby wipes", page_number=2) == (
        "https://www.amazon.in/s?k=baby+wipes&page=2"
    )
    assert amazon_search_url(query="baby wipes") == amazon_search_url(query="baby wipes")


def test_amazon_search_url_encodes_query_without_allowing_host_injection() -> None:
    requested_url = amazon_search_url(query="wipes & https://evil.example/?x=1")
    parsed = urlsplit(requested_url)

    assert parsed.scheme == "https"
    assert parsed.hostname == "www.amazon.in"
    assert parsed.path == "/s"
    assert parse_qs(parsed.query) == {"k": ["wipes & https://evil.example/?x=1"]}


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_blank_query_is_rejected(query: str) -> None:
    with pytest.raises(ValueError, match="query"):
        collection_request(query=query)
    with pytest.raises(ValueError, match="query"):
        amazon_search_url(query=query)


@pytest.mark.parametrize("page_number", [0, -1])
def test_invalid_page_number_is_rejected(page_number: int) -> None:
    with pytest.raises(ValueError, match="page number"):
        collection_request(page_number=page_number)
    with pytest.raises(ValueError, match="page number"):
        amazon_search_url(query="baby wipes", page_number=page_number)


@pytest.mark.asyncio
async def test_collector_passes_serp_url_profile_and_screenshot_to_browser() -> None:
    browser = FakeBrowserCaptureClient(capture_result())
    collector = AmazonSerpCollector(browser)
    request = collection_request(page_number=3, capture_screenshot=True)

    result = await collector.capture(request)

    assert result.keyword_id == KEYWORD_ID
    assert result.query == "baby wipes"
    assert result.page_number == 3
    assert result.browser_capture is browser.result
    assert browser.requests == [
        BrowserCaptureRequest(
            requested_url="https://www.amazon.in/s?k=baby+wipes&page=3",
            page_type="serp",
            profile=PROFILE,
            capture_screenshot=True,
        )
    ]


@pytest.mark.asyncio
async def test_challenge_and_redirect_are_preserved_without_retry() -> None:
    challenge = ChallengeState(ChallengeKind.CAPTCHA, "captcha_signal")
    browser = FakeBrowserCaptureClient(capture_result(challenge=challenge))
    collector = AmazonSerpCollector(browser)

    result = await collector.capture(collection_request())

    assert result.browser_capture.final_url == "https://www.amazon.in/s?k=fixture&ref=redirect"
    assert result.browser_capture.challenge is challenge
    assert result.browser_capture.challenge_detected is True
    assert len(browser.requests) == 1

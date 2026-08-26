from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from novel_signal.collectors.playwright_browser import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
    BrowserConfigurationError,
    BrowserProfile,
    ChallengeState,
    UnsupportedTargetError,
)
from novel_signal.collectors.public_web_page import (
    PublicWebPageCollectionRequest,
    PublicWebPageCollector,
)

PROFILE = BrowserProfile(profile_id="public-web-desktop")
COMPETITOR_ID = UUID("12345678-1234-5678-1234-567812345678")


class FakeBrowser:
    def __init__(self, result: BrowserCaptureResult) -> None:
        self.result = result
        self.requests: list[BrowserCaptureRequest] = []

    async def capture(self, request: BrowserCaptureRequest) -> BrowserCaptureResult:
        self.requests.append(request)
        return self.result


def result(*, final_url: str = "https://shop.acme.example/products/wipes") -> BrowserCaptureResult:
    return BrowserCaptureResult(
        requested_url="https://shop.acme.example/products/wipes",
        final_url=final_url,
        status=200,
        html=b"<html>exact body</html>",
        content_type="text/html",
        captured_at=datetime(2026, 8, 26, tzinfo=UTC),
        page_type="public_web_page",
        profile_id=PROFILE.profile_id,
        challenge=ChallengeState(),
        screenshot=b"exact screenshot",
    )


@pytest.mark.asyncio
async def test_allowlisted_capture_forwards_once_and_preserves_exact_result() -> None:
    browser = FakeBrowser(result())
    collector = PublicWebPageCollector(browser, allowed_domains=("acme.example",))
    request = PublicWebPageCollectionRequest(
        url="  https://shop.acme.example/products/wipes  ",
        profile=PROFILE,
        capture_screenshot=True,
        competitor_id=COMPETITOR_ID,
    )
    captured = await collector.capture(request)

    assert captured.url == "https://shop.acme.example/products/wipes"
    assert captured.competitor_id == COMPETITOR_ID
    assert captured.browser_capture is browser.result
    assert captured.browser_capture.html is browser.result.html
    assert captured.browser_capture.screenshot is browser.result.screenshot
    assert browser.requests == [
        BrowserCaptureRequest(
            requested_url="https://shop.acme.example/products/wipes",
            page_type="public_web_page",
            profile=PROFILE,
            capture_screenshot=True,
        )
    ]


@pytest.mark.parametrize(
    "url",
    [
        "https://acme.example.evil.test/x",
        "https://user:password@acme.example/x",
        "file:///etc/passwd",
        "http://localhost/x",
        "http://127.0.0.1/x",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/x",
    ],
)
@pytest.mark.asyncio
async def test_non_public_or_non_allowlisted_targets_never_reach_browser(url: str) -> None:
    browser = FakeBrowser(result())
    allowed = ("acme.example", "localhost", "127.0.0.1", "169.254.169.254", "10.0.0.1")
    collector = PublicWebPageCollector(browser, allowed_domains=allowed)
    with pytest.raises(UnsupportedTargetError):
        await collector.capture(PublicWebPageCollectionRequest(url=url, profile=PROFILE))
    assert browser.requests == []


@pytest.mark.asyncio
async def test_redirect_must_remain_inside_configured_domain() -> None:
    browser = FakeBrowser(result(final_url="https://evil.example/redirected"))
    collector = PublicWebPageCollector(browser, allowed_domains=("acme.example",))
    with pytest.raises(UnsupportedTargetError, match="redirect"):
        await collector.capture(
            PublicWebPageCollectionRequest(
                url="https://shop.acme.example/products/wipes", profile=PROFILE
            )
        )
    assert len(browser.requests) == 1


def test_blank_url_and_empty_allowlist_are_rejected() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        PublicWebPageCollectionRequest(url="  ", profile=PROFILE)
    with pytest.raises(BrowserConfigurationError):
        PublicWebPageCollector(FakeBrowser(result()), allowed_domains=())

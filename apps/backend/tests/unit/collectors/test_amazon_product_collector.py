from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from novel_signal.collectors.amazon_product import (
    AmazonProductCollectionRequest,
    AmazonProductCollector,
    amazon_product_url,
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


PROFILE = BrowserProfile(profile_id="product-desktop")
PRODUCT_ID = UUID("12345678-1234-5678-1234-567812345678")
COMPETITOR_PRODUCT_ID = UUID("87654321-4321-8765-4321-876543218765")


def browser_result(*, challenge: ChallengeState | None = None) -> BrowserCaptureResult:
    return BrowserCaptureResult(
        requested_url="https://www.amazon.in/dp/B0ABC12345",
        final_url="https://www.amazon.in/gp/product/B0ABC12345?ref=redirect",
        status=200,
        html=b"<html>sanitized fixture</html>",
        content_type="text/html; charset=utf-8",
        captured_at=datetime(2026, 8, 29, tzinfo=UTC),
        page_type="product_detail",
        profile_id=PROFILE.profile_id,
        challenge=challenge or ChallengeState(),
        screenshot=b"fixture-screenshot",
    )


def product_request(**changes: object) -> AmazonProductCollectionRequest:
    values: dict[str, object] = {"marketplace_product_id": "B0ABC12345", "profile": PROFILE}
    values.update(changes)
    return AmazonProductCollectionRequest(**values)  # type: ignore[arg-type]


def test_canonical_product_url_is_deterministic_and_safe() -> None:
    url = amazon_product_url(marketplace_product_id=" b0abc12345 ")
    parsed = urlsplit(url)
    assert url == "https://www.amazon.in/dp/B0ABC12345"
    assert parsed.scheme == "https"
    assert parsed.hostname == "www.amazon.in"
    assert parsed.path == "/dp/B0ABC12345"
    assert parsed.query == ""
    assert parsed.fragment == ""
    assert amazon_product_url(marketplace_product_id="b0abc12345") == url


def test_request_normalizes_uppercase_asin_and_preserves_optional_identity() -> None:
    request = product_request(marketplace_product_id="  b0abc12345\t", product_id=PRODUCT_ID)
    assert request.marketplace_product_id == "B0ABC12345"
    assert request.product_id == PRODUCT_ID
    assert request.competitor_product_id is None


@pytest.mark.parametrize(
    "asin",
    [
        "",
        "   ",
        "\n\t",
        "B0ABC1234",
        "B0ABC123456",
        "B0ABC12/45",
        "https://evil.example",
        "B0ABC12345?x=1",
        "B0ABC12345#x",
        "../B0ABC12345",
        "B0ABC12_45",
        "B0ABC 2345",
        "user@B0ABC12345",
        "/dp/B0ABC12345",
    ],
)
def test_invalid_or_injection_style_asins_are_rejected(asin: str) -> None:
    with pytest.raises(ValueError, match="valid ASIN"):
        product_request(marketplace_product_id=asin)
    with pytest.raises(ValueError, match="valid ASIN"):
        amazon_product_url(marketplace_product_id=asin)


def test_conflicting_contextual_identities_are_rejected() -> None:
    with pytest.raises(ValueError, match="both product identities"):
        product_request(product_id=PRODUCT_ID, competitor_product_id=COMPETITOR_PRODUCT_ID)


@pytest.mark.asyncio
async def test_collector_forwards_one_canonical_product_capture_unchanged() -> None:
    browser = FakeBrowserCaptureClient(browser_result())
    request = product_request(
        marketplace_product_id="b0abc12345",
        capture_screenshot=True,
        competitor_product_id=COMPETITOR_PRODUCT_ID,
    )

    result = await AmazonProductCollector(browser).capture(request)

    assert result.marketplace_product_id == "B0ABC12345"
    assert result.competitor_product_id == COMPETITOR_PRODUCT_ID
    assert result.product_id is None
    assert result.browser_capture is browser.result
    assert browser.requests == [
        BrowserCaptureRequest(
            requested_url="https://www.amazon.in/dp/B0ABC12345",
            page_type="product_detail",
            profile=PROFILE,
            capture_screenshot=True,
        )
    ]
    assert result.browser_capture.final_url == "https://www.amazon.in/gp/product/B0ABC12345?ref=redirect"
    assert result.browser_capture.html == b"<html>sanitized fixture</html>"
    assert result.browser_capture.status == 200
    assert result.browser_capture.content_type == "text/html; charset=utf-8"
    assert result.browser_capture.captured_at == datetime(2026, 8, 29, tzinfo=UTC)
    assert result.browser_capture.screenshot == b"fixture-screenshot"


@pytest.mark.asyncio
async def test_challenge_result_is_returned_without_retry_or_mutation() -> None:
    challenge = ChallengeState(ChallengeKind.CAPTCHA, "captcha_signal")
    browser = FakeBrowserCaptureClient(browser_result(challenge=challenge))

    result = await AmazonProductCollector(browser).capture(product_request())

    assert result.browser_capture is browser.result
    assert result.browser_capture.challenge is challenge
    assert result.browser_capture.challenge_detected is True
    assert len(browser.requests) == 1

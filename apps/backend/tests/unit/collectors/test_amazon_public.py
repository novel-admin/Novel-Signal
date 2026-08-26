from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from novel_signal.collectors.amazon_in.public_pages import (
    AmazonChallengeError,
    AmazonPublicCollector,
)
from novel_signal.collectors.base import CaptureRequest
from novel_signal.parsers.amazon_public import AmazonProductParser, AmazonSearchParser


def test_url_builders_are_allowlisted() -> None:
    assert AmazonPublicCollector.search_url("baby wipes") == (
        "https://www.amazon.in/s?k=baby+wipes"
    )
    assert AmazonPublicCollector.product_url("b0abc12345") == "https://www.amazon.in/dp/B0ABC12345"


@pytest.mark.asyncio
async def test_collector_returns_public_html() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, content=b"<html>ok</html>")

    collector = AmazonPublicCollector(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        min_delay_seconds=0,
        max_delay_seconds=0,
    )
    result = await collector.capture(
        CaptureRequest(AmazonPublicCollector.search_url("wipes"), "keyword-1", "serp")
    )
    assert result.body == b"<html>ok</html>"
    await collector.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_collector_stops_on_challenge() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, text="Please complete the CAPTCHA")

    collector = AmazonPublicCollector(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        min_delay_seconds=0,
        max_delay_seconds=0,
    )
    with pytest.raises(AmazonChallengeError):
        await collector.capture(
            CaptureRequest(AmazonPublicCollector.search_url("wipes"), "keyword-1", "serp")
        )
    await collector.client.aclose()  # type: ignore[union-attr]


def test_search_parser_extracts_rank_and_commercial_signals() -> None:
    html = (
        b'''<div data-asin="B0ABC12345"><span>Sponsored</span><span>Amazon's Choice</span>
        <span>4.4 out of 5</span><span>1,234 ratings</span><span>'''
        + "₹499.00".encode()
        + b"</span></div>"
    )
    result = AmazonSearchParser().parse(html).records[0]
    assert result["marketplace_product_id"] == "B0ABC12345"
    assert result["absolute_position"] == 1
    assert result["placement_type"].value == "sponsored_product"
    assert result["rating"] == Decimal("4.4")
    assert result["review_count"] == 1234
    assert result["displayed_price"] == Decimal("499")


def test_product_parser_returns_unknown_when_asin_is_missing() -> None:
    assert AmazonProductParser().parse(b"<html>blocked</html>").records == ()

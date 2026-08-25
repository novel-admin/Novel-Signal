from datetime import UTC, datetime

import httpx
import pytest

# Keep source imports grouped after third-party imports for ruff/isort.
from novel_signal.sources.amazon.ads_api import (
    AmazonAdsClient,
    AmazonAdsConfig,
    AmazonAdsPermissionError,
    AmazonAdsReportError,
)
from novel_signal.sources.base import SyncRequest
from novel_signal.sources.meta.marketing_api import MetaMarketingClient, MetaMarketingConfig


def window() -> SyncRequest:
    return SyncRequest(
        "campaigns",
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 2, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_amazon_fetches_all_cursor_pages_without_logging_secret() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "api.amazon.com":
            return httpx.Response(200, json={"access_token": "test-token"})
        if "nextToken" in str(request.url):
            return httpx.Response(200, json={"campaigns": [{"id": "2"}]})
        return httpx.Response(200, json={"campaigns": [{"id": "1"}], "nextToken": "next"})

    config = AmazonAdsConfig("client", "secret", "refresh", ("profile",))
    async with AmazonAdsClient(config, transport=httpx.MockTransport(handler)) as client:
        pages = await client.fetch(window())
    assert len(pages) == 2
    assert pages[0].next_cursor == {"profile": "next"}
    assert all("secret" not in call for call in calls)


@pytest.mark.asyncio
async def test_amazon_report_uses_profile_scope_and_downloads_raw_document() -> None:
    scoped_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.amazon.com":
            return httpx.Response(200, json={"access_token": "test-token"})
        if request.url.host == "download.test":
            return httpx.Response(200, content=b"campaignId,impressions\n1,10")
        scoped_requests.append(request)
        if request.method == "POST":
            return httpx.Response(202, json={"reportId": "report-1"})
        return httpx.Response(
            200,
            json={"reportId": "report-1", "status": "COMPLETED", "url": "https://download.test/r"},
        )

    async with AmazonAdsClient(
        AmazonAdsConfig("client", "secret", "refresh", ("profile",)),
        transport=httpx.MockTransport(handler),
    ) as client:
        report_id = await client.create_report(
            profile_id="profile",
            name="search terms",
            start_date="2026-08-24",
            end_date="2026-08-25",
            configuration={"reportTypeId": "spSearchTerm"},
        )
        page = await client.fetch_report_document(
            profile_id="profile", report_id=report_id, poll_interval_seconds=0
        )
    assert page.body.startswith(b"campaignId")
    assert all(
        request.headers["Amazon-Advertising-API-Scope"] == "profile" for request in scoped_requests
    )


@pytest.mark.asyncio
async def test_amazon_failed_report_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.amazon.com":
            return httpx.Response(200, json={"access_token": "test-token"})
        return httpx.Response(200, json={"status": "FAILURE", "failureReason": "bad columns"})

    async with AmazonAdsClient(
        AmazonAdsConfig("client", "secret", "refresh", ("profile",)),
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(AmazonAdsReportError, match="bad columns"):
            await client.fetch_report_document(
                profile_id="profile", report_id="report-1", poll_interval_seconds=0
            )


@pytest.mark.asyncio
async def test_amazon_permission_error_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})

    async with AmazonAdsClient(
        AmazonAdsConfig("client", "secret", "refresh", ("profile",)),
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(AmazonAdsPermissionError):
            await client.verify_connection()


@pytest.mark.asyncio
async def test_meta_fetch_follows_next_link() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "after=next" in str(request.url):
            return httpx.Response(200, json={"data": [{"id": "2"}]})
        return httpx.Response(
            200,
            json={"data": [{"id": "1"}], "paging": {"next": "https://graph.test/next?after=next"}},
        )

    async with MetaMarketingClient(
        MetaMarketingConfig("token", ("123",), api_base_url="https://graph.test"),
        transport=httpx.MockTransport(handler),
    ) as client:
        pages = await client.fetch(window())
    assert len(pages) == 2
    assert pages[0].next_cursor == {"123": "next"}

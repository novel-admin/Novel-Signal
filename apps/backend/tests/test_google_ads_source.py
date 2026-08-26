from datetime import UTC, datetime

import httpx
import pytest
from novel_signal.sources.base import SyncRequest
from novel_signal.sources.google.ads_api import (
    GoogleAdsClient,
    GoogleAdsConfig,
    GoogleAdsConfigurationError,
    GoogleAdsPermissionError,
)


def config() -> GoogleAdsConfig:
    return GoogleAdsConfig(
        developer_token="developer-token",
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        customer_id="1234567890",
        login_customer_id="9876543210",
        api_base_url="https://googleads.test/v18",
        token_url="https://oauth.test/token",
    )


@pytest.mark.asyncio
async def test_google_ads_verifies_and_fetches_raw_pages() -> None:
    raw = b'[{"results":[{"campaign":{"id":"1"}}]}]'

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth.test":
            assert request.method == "POST"
            return httpx.Response(200, json={"access_token": "access-token"})
        assert request.headers["authorization"] == "Bearer access-token"
        assert request.headers["developer-token"] == "developer-token"
        assert request.headers["login-customer-id"] == "9876543210"
        return httpx.Response(200, content=raw, headers={"content-type": "application/json"})

    async with GoogleAdsClient(config(), transport=httpx.MockTransport(handler)) as source:
        await source.verify_connection()
        pages = await source.fetch(
            SyncRequest(
                "campaigns",
                datetime(2026, 8, 1, tzinfo=UTC),
                datetime(2026, 8, 2, tzinfo=UTC),
            )
        )

    assert pages[0].source.value == "google_ads_api"
    assert pages[0].body == raw


@pytest.mark.asyncio
async def test_google_ads_requires_configuration_and_maps_permission_failure() -> None:
    incomplete = GoogleAdsConfig("", "", "", "", "")
    transport = httpx.MockTransport(lambda _: httpx.Response(200))
    async with GoogleAdsClient(incomplete, transport=transport) as source:
        with pytest.raises(GoogleAdsConfigurationError):
            await source.verify_connection()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth.test":
            return httpx.Response(200, json={"access_token": "access-token"})
        return httpx.Response(403)

    async with GoogleAdsClient(config(), transport=httpx.MockTransport(handler)) as source:
        with pytest.raises(GoogleAdsPermissionError):
            await source.verify_connection()

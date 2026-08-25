from datetime import UTC, datetime

import httpx
import pytest

# Keep source imports grouped after third-party imports for ruff/isort.
from novel_signal.sources.amazon.sp_api import (
    AmazonSpApiAuthenticationError,
    AmazonSpApiClient,
    AmazonSpApiConfig,
    AmazonSpApiConfigurationError,
    AmazonSpApiCursorError,
    AmazonSpApiMalformedResponseError,
    AmazonSpApiNetworkError,
    AmazonSpApiPermissionError,
    AmazonSpApiRateLimitError,
    AmazonSpApiUnsupportedResourceError,
)
from novel_signal.sources.base import SyncRequest


def config(**overrides: str) -> AmazonSpApiConfig:
    values = {
        "lwa_client_id": "client-id",
        "lwa_client_secret": "client-secret",
        "lwa_refresh_token": "refresh-token",
        "aws_access_key_id": "access-key",
        "aws_secret_access_key": "aws-secret-key",
        "marketplace_id": "A21TJRUUN4KGV",
        "region": "eu-west-1",
        "api_base_url": "https://sp-api.test",
        "token_url": "https://lwa.test/token",
    }
    values.update(overrides)
    return AmazonSpApiConfig(**values)


def token_response() -> httpx.Response:
    return httpx.Response(200, json={"access_token": "access-token"})


def sync_request(resource_type: str, cursor: dict[str, str] | None) -> SyncRequest:
    return SyncRequest(
        resource_type=resource_type,
        window_start=datetime(2026, 8, 25, tzinfo=UTC),
        window_end=datetime(2026, 8, 26, tzinfo=UTC),
        cursor=cursor,
    )


@pytest.mark.asyncio
async def test_sp_api_verifies_lwa_and_signed_marketplace_access() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "lwa.test":
            return token_response()
        return httpx.Response(
            200,
            json={"payload": [{"marketplace": {"id": "A21TJRUUN4KGV"}}]},
        )

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(handler)) as client:
        await client.verify_connection()

    assert len(requests) == 2
    verification_request = requests[1]
    assert verification_request.url.path == "/sellers/v1/marketplaceParticipations"
    assert verification_request.headers["x-amz-access-token"] == "access-token"
    assert verification_request.headers["authorization"].startswith("AWS4-HMAC-SHA256")


@pytest.mark.asyncio
async def test_sp_api_rejected_lwa_credentials_are_typed_and_safe() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client"})

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AmazonSpApiAuthenticationError) as error:
            await client.verify_connection()

    assert_no_secrets(str(error.value))


@pytest.mark.asyncio
async def test_sp_api_missing_configuration_is_typed_and_safe() -> None:
    incomplete = config(lwa_client_id="")
    async with AmazonSpApiClient(incomplete) as client:
        with pytest.raises(AmazonSpApiConfigurationError) as error:
            await client.verify_connection()

    assert_no_secrets(str(error.value))


@pytest.mark.asyncio
async def test_sp_api_permission_denial_is_typed_and_safe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        return httpx.Response(403, json={"errors": [{"code": "Unauthorized"}]})

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AmazonSpApiPermissionError) as error:
            await client.verify_connection()

    assert_no_secrets(str(error.value))


@pytest.mark.asyncio
async def test_sp_api_rate_limit_preserves_retry_after_without_secrets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        return httpx.Response(429, headers={"Retry-After": "30"})

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AmazonSpApiRateLimitError) as error:
            await client.verify_connection()

    assert error.value.retry_after == "30"
    assert_no_secrets(str(error.value))


@pytest.mark.asyncio
async def test_sp_api_malformed_token_response_is_typed_and_safe() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token_type": "bearer"})

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AmazonSpApiMalformedResponseError) as error:
            await client.verify_connection()

    assert_no_secrets(str(error.value))


@pytest.mark.asyncio
async def test_sp_api_timeout_is_typed_and_safe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AmazonSpApiNetworkError) as error:
            await client.verify_connection()

    assert_no_secrets(str(error.value))


@pytest.mark.asyncio
async def test_sp_api_empty_marketplace_response_denies_access() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        return httpx.Response(200, json={"payload": []})

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AmazonSpApiPermissionError):
            await client.verify_connection()


@pytest.mark.asyncio
async def test_sp_api_fetches_catalog_raw_bytes_with_deterministic_fingerprint() -> None:
    raw_body = b'{"payload":{"asin":"B012345678"}}'
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "lwa.test":
            return token_response()
        return httpx.Response(200, content=raw_body, headers={"content-type": "application/json"})

    request = sync_request("catalog_items", {"asin": "B012345678"})
    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(handler)) as client:
        first = await client.fetch(request)
        second = await client.fetch(request)

    assert len(first) == 1
    assert first[0].source.value == "amazon_sp_api"
    assert first[0].resource_type == "catalog_items"
    assert first[0].body == raw_body
    assert first[0].content_type == "application/json"
    assert first[0].next_cursor is None
    assert first[0].request_fingerprint == second[0].request_fingerprint
    assert requests[1].url.path == "/catalog/2022-04-01/items/B012345678"
    assert requests[1].url.params["marketplaceIds"] == "A21TJRUUN4KGV"


@pytest.mark.asyncio
async def test_sp_api_fetches_pricing_offers_raw_bytes() -> None:
    raw_body = b'{"payload":[{"ListingPrice":{"Amount":299}}]}'

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        return httpx.Response(200, content=raw_body)

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(handler)) as client:
        pages = await client.fetch(sync_request("pricing_offers", {"asin": "B012345678"}))

    assert pages[0].body == raw_body
    assert pages[0].resource_type == "pricing_offers"


@pytest.mark.asyncio
async def test_sp_api_fetches_paginated_inventory_and_terminates() -> None:
    requests: list[httpx.Request] = []
    first_body = b'{"payload":{"inventorySummaries":[]},"pagination":{"nextToken":"next-1"}}'
    second_body = b'{"payload":{"inventorySummaries":[]},"pagination":{}}'

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "lwa.test":
            return token_response()
        if request.url.params.get("nextToken") == "next-1":
            return httpx.Response(200, content=second_body)
        return httpx.Response(200, content=first_body)

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(handler)) as client:
        pages = await client.fetch(sync_request("inventory_summaries", {"seller_sku": "NOVEL-001"}))

    assert [page.body for page in pages] == [first_body, second_body]
    assert pages[0].next_cursor == {"seller_sku": "NOVEL-001", "next_token": "next-1"}
    assert pages[1].next_cursor is None
    assert requests[-1].url.params["nextToken"] == "next-1"


@pytest.mark.asyncio
async def test_sp_api_inventory_cursor_continuation_uses_next_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "lwa.test":
            return token_response()
        return httpx.Response(200, content=b'{"payload":{},"pagination":{}}')

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(handler)) as client:
        pages = await client.fetch(
            sync_request("inventory_summaries", {"seller_sku": "NOVEL-001", "next_token": "resume"})
        )

    assert len(pages) == 1
    assert requests[-1].url.params["nextToken"] == "resume"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (401, AmazonSpApiAuthenticationError),
        (403, AmazonSpApiPermissionError),
    ],
)
async def test_sp_api_raw_fetch_auth_and_permission_errors_are_typed_and_safe(
    status_code: int, error_type: type[Exception]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        return httpx.Response(status_code)

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(error_type) as error:
            await client.fetch(sync_request("catalog_items", {"asin": "B012345678"}))
    assert_no_secrets(str(error.value))


@pytest.mark.asyncio
async def test_sp_api_raw_fetch_rate_limit_timeout_and_transport_are_safe() -> None:
    def rate_limited(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        return httpx.Response(429, headers={"Retry-After": "12"})

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(rate_limited)) as client:
        with pytest.raises(AmazonSpApiRateLimitError) as rate_error:
            await client.fetch(sync_request("catalog_items", {"asin": "B012345678"}))
    assert rate_error.value.retry_after == "12"
    assert_no_secrets(str(rate_error.value))

    def timeout(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        raise httpx.ReadTimeout("timeout", request=request)

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(AmazonSpApiNetworkError) as timeout_error:
            await client.fetch(sync_request("catalog_items", {"asin": "B012345678"}))
    assert_no_secrets(str(timeout_error.value))

    def unavailable(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        raise httpx.ConnectError("unavailable", request=request)

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(unavailable)) as client:
        with pytest.raises(AmazonSpApiNetworkError) as network_error:
            await client.fetch(sync_request("catalog_items", {"asin": "B012345678"}))
    assert_no_secrets(str(network_error.value))


@pytest.mark.asyncio
async def test_sp_api_inventory_malformed_and_empty_raw_responses() -> None:
    def malformed(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        return httpx.Response(200, content=b"not-json")

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(malformed)) as client:
        with pytest.raises(AmazonSpApiMalformedResponseError):
            await client.fetch(sync_request("inventory_summaries", {"seller_sku": "NOVEL-001"}))

    def empty(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        return httpx.Response(200, content=b"")

    async with AmazonSpApiClient(config(), transport=httpx.MockTransport(empty)) as client:
        pages = await client.fetch(sync_request("inventory_summaries", {"seller_sku": "NOVEL-001"}))
    assert pages[0].body == b"" and pages[0].next_cursor is None


@pytest.mark.asyncio
async def test_sp_api_rejects_unsupported_resources_and_malformed_cursors() -> None:
    async with AmazonSpApiClient(config()) as client:
        with pytest.raises(AmazonSpApiUnsupportedResourceError):
            await client.fetch(sync_request("orders", {"asin": "B012345678"}))
        with pytest.raises(AmazonSpApiCursorError):
            await client.fetch(sync_request("catalog_items", None))
        with pytest.raises(AmazonSpApiCursorError):
            await client.fetch(sync_request("inventory_summaries", {"seller_sku": ""}))


def assert_no_secrets(message: str) -> None:
    for secret in ("client-secret", "refresh-token", "aws-secret-key"):
        assert secret not in message

import gzip
import json
from datetime import UTC, datetime

import httpx
import pytest
from novel_signal.sources.amazon.brand_analytics import (
    BrandAnalyticsAuthenticationError,
    BrandAnalyticsClient,
    BrandAnalyticsCompressionError,
    BrandAnalyticsConfig,
    BrandAnalyticsEmptyResponseError,
    BrandAnalyticsMalformedResponseError,
    BrandAnalyticsNetworkError,
    BrandAnalyticsPermissionError,
    BrandAnalyticsRateLimitError,
    BrandAnalyticsReportFailedError,
)
from novel_signal.sources.amazon.sp_api import (
    AmazonSpApiAuthenticationError,
    AmazonSpApiConfig,
    AmazonSpApiConfigurationError,
    AmazonSpApiMalformedResponseError,
    AmazonSpApiPermissionError,
)
from novel_signal.sources.base import SyncRequest


def config(**overrides: str) -> BrandAnalyticsConfig:
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
    return BrandAnalyticsConfig(AmazonSpApiConfig(**values))


def token_response() -> httpx.Response:
    return httpx.Response(200, json={"access_token": "access-token"})


def marketplace_response() -> httpx.Response:
    return httpx.Response(200, json={"payload": [{"marketplace": {"id": "A21TJRUUN4KGV"}}]})


def raw_request() -> SyncRequest:
    return SyncRequest(
        "brand_analytics_search_query_performance",
        datetime(2026, 8, 1, tzinfo=UTC),
        datetime(2026, 8, 8, tzinfo=UTC),
        {
            "data_start_time": "2026-08-01T00:00:00+00:00",
            "data_end_time": "2026-08-08T00:00:00+00:00",
        },
    )


@pytest.mark.asyncio
async def test_brand_analytics_verifies_report_request_access() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "lwa.test":
            return token_response()
        if request.url.path == "/sellers/v1/marketplaceParticipations":
            return marketplace_response()
        return httpx.Response(202, json={"reportId": "report-123"})

    async with BrandAnalyticsClient(config(), transport=httpx.MockTransport(handler)) as client:
        await client.verify_connection()

    report_request = requests[-1]
    assert report_request.url.path == "/reports/2021-06-30/reports"
    assert report_request.headers["authorization"].startswith("AWS4-HMAC-SHA256")
    assert json.loads(report_request.content)["reportType"] == (
        "GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT"
    )


@pytest.mark.asyncio
async def test_brand_analytics_missing_configuration_is_safe() -> None:
    async with BrandAnalyticsClient(config(lwa_client_id="")) as client:
        with pytest.raises(AmazonSpApiConfigurationError) as error:
            await client.verify_connection()
    assert_no_secrets(str(error.value))


@pytest.mark.asyncio
async def test_brand_analytics_lwa_rejection_is_safe() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client"})

    async with BrandAnalyticsClient(config(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AmazonSpApiAuthenticationError) as error:
            await client.verify_connection()
    assert_no_secrets(str(error.value))


@pytest.mark.asyncio
async def test_brand_analytics_sp_api_authentication_rejection_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        return httpx.Response(401, json={"errors": []})

    async with BrandAnalyticsClient(config(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AmazonSpApiAuthenticationError):
            await client.verify_connection()


@pytest.mark.asyncio
async def test_brand_analytics_report_permission_denial_is_safe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        if request.url.path == "/sellers/v1/marketplaceParticipations":
            return marketplace_response()
        return httpx.Response(403, json={"errors": []})

    async with BrandAnalyticsClient(config(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BrandAnalyticsPermissionError) as error:
            await client.verify_connection()
    assert_no_secrets(str(error.value))


@pytest.mark.asyncio
async def test_brand_analytics_report_authentication_rejection_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        if request.url.path == "/sellers/v1/marketplaceParticipations":
            return marketplace_response()
        return httpx.Response(401, json={"errors": []})

    async with BrandAnalyticsClient(config(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BrandAnalyticsAuthenticationError):
            await client.verify_connection()


@pytest.mark.asyncio
async def test_brand_analytics_unavailable_marketplace_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        return httpx.Response(200, json={"payload": []})

    async with BrandAnalyticsClient(config(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AmazonSpApiPermissionError):
            await client.verify_connection()


@pytest.mark.asyncio
async def test_brand_analytics_rate_limit_preserves_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        if request.url.path == "/sellers/v1/marketplaceParticipations":
            return marketplace_response()
        return httpx.Response(429, headers={"Retry-After": "20"})

    async with BrandAnalyticsClient(config(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BrandAnalyticsRateLimitError) as error:
            await client.verify_connection()
    assert error.value.retry_after == "20"
    assert_no_secrets(str(error.value))


@pytest.mark.asyncio
async def test_brand_analytics_timeout_and_transport_failures_are_safe() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        if request.url.path == "/sellers/v1/marketplaceParticipations":
            return marketplace_response()
        raise httpx.ReadTimeout("timed out", request=request)

    async with BrandAnalyticsClient(
        config(), transport=httpx.MockTransport(timeout_handler)
    ) as client:
        with pytest.raises(BrandAnalyticsNetworkError) as error:
            await client.verify_connection()
    assert_no_secrets(str(error.value))

    def transport_handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        if request.url.path == "/sellers/v1/marketplaceParticipations":
            return marketplace_response()
        raise httpx.ConnectError("unreachable", request=request)

    async with BrandAnalyticsClient(
        config(), transport=httpx.MockTransport(transport_handler)
    ) as client:
        with pytest.raises(BrandAnalyticsNetworkError) as transport_error:
            await client.verify_connection()
    assert_no_secrets(str(transport_error.value))


@pytest.mark.asyncio
async def test_brand_analytics_malformed_token_and_report_responses_are_typed() -> None:
    def malformed_token(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    async with BrandAnalyticsClient(
        config(), transport=httpx.MockTransport(malformed_token)
    ) as client:
        with pytest.raises(AmazonSpApiMalformedResponseError) as token_error:
            await client.verify_connection()
    assert_no_secrets(str(token_error.value))

    def malformed_report(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        if request.url.path == "/sellers/v1/marketplaceParticipations":
            return marketplace_response()
        return httpx.Response(202, content=b"not-json")

    async with BrandAnalyticsClient(
        config(), transport=httpx.MockTransport(malformed_report)
    ) as client:
        with pytest.raises(BrandAnalyticsMalformedResponseError):
            await client.verify_connection()


@pytest.mark.asyncio
async def test_brand_analytics_empty_valid_report_response_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        if request.url.path == "/sellers/v1/marketplaceParticipations":
            return marketplace_response()
        return httpx.Response(202, json={})

    async with BrandAnalyticsClient(config(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BrandAnalyticsEmptyResponseError):
            await client.verify_connection()


def assert_no_secrets(message: str) -> None:
    for secret in ("client-secret", "refresh-token", "aws-secret-key"):
        assert secret not in message


@pytest.mark.asyncio
async def test_brand_analytics_fetches_done_report_document_as_exact_raw_bytes() -> None:
    raw = b'{"report":"raw"}'

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        if request.url.host == "download.test":
            return httpx.Response(200, content=raw, headers={"content-type": "application/json"})
        if request.url.path == "/sellers/v1/marketplaceParticipations":
            return marketplace_response()
        if request.url.path == "/reports/2021-06-30/reports":
            return httpx.Response(202, json={"reportId": "r1"})
        if request.url.path.endswith("/r1"):
            return httpx.Response(200, json={"processingStatus": "DONE", "reportDocumentId": "d1"})
        if request.url.path.endswith("/d1"):
            return httpx.Response(200, json={"url": "https://download.test/d1"})
        raise AssertionError(f"Unexpected request: {request.url}")

    async with BrandAnalyticsClient(config(), transport=httpx.MockTransport(handler)) as client:
        first = await client.fetch(raw_request())
        second = await client.fetch(raw_request())
    assert first[0].body == raw and first[0].source.value == "amazon_brand_analytics"
    assert first[0].request_fingerprint == second[0].request_fingerprint


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["CANCELLED", "FATAL"])
async def test_brand_analytics_fetch_rejects_terminal_failure(status: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "lwa.test":
            return token_response()
        if request.url.path == "/sellers/v1/marketplaceParticipations":
            return marketplace_response()
        if request.url.path == "/reports/2021-06-30/reports":
            return httpx.Response(202, json={"reportId": "r1"})
        return httpx.Response(200, json={"processingStatus": status})

    async with BrandAnalyticsClient(config(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BrandAnalyticsReportFailedError):
            await client.fetch(raw_request())


@pytest.mark.asyncio
async def test_brand_analytics_download_handles_gzip_and_rejects_invalid_compression() -> None:
    payload = b'{"report":"decompressed"}'

    async with BrandAnalyticsClient(
        config(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=gzip.compress(payload))
        ),
    ) as client:
        body, _ = await client._download("https://download.test/report", "GZIP")
    assert body == payload

    async with BrandAnalyticsClient(
        config(), transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"not-gzip"))
    ) as client:
        with pytest.raises(BrandAnalyticsCompressionError):
            await client._download("https://download.test/report", "GZIP")
        with pytest.raises(BrandAnalyticsCompressionError):
            await client._download("https://download.test/report", "ZIP")

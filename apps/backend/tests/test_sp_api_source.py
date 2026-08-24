import httpx
import pytest

# Keep source imports grouped after third-party imports for ruff/isort.
from novel_signal.sources.amazon.sp_api import (
    AmazonSpApiAuthenticationError,
    AmazonSpApiClient,
    AmazonSpApiConfig,
    AmazonSpApiConfigurationError,
    AmazonSpApiMalformedResponseError,
    AmazonSpApiNetworkError,
    AmazonSpApiPermissionError,
    AmazonSpApiRateLimitError,
)


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


def assert_no_secrets(message: str) -> None:
    for secret in ("client-secret", "refresh-token", "aws-secret-key"):
        assert secret not in message

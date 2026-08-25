import json
from datetime import UTC, datetime

import httpx
import pytest
from novel_signal.sources.base import SyncRequest
from novel_signal.sources.google.search_console import (
    GoogleSearchConsoleAuthenticationError,
    GoogleSearchConsoleClient,
    GoogleSearchConsoleConfig,
    GoogleSearchConsoleConfigurationError,
    GoogleSearchConsoleEmptyResponseError,
    GoogleSearchConsoleMalformedResponseError,
    GoogleSearchConsoleNetworkError,
    GoogleSearchConsolePermissionError,
    GoogleSearchConsolePropertyUnavailableError,
    GoogleSearchConsoleRateLimitError,
)


class FakeCredentials:
    token: str | None = None

    def __init__(self, _: object) -> None:
        pass

    def refresh(self, _: object) -> None:
        self.token = "gsc-access-token"


class RejectedCredentials:
    token: str | None = None

    def __init__(self, _: object) -> None:
        pass

    def refresh(self, _: object) -> None:
        raise ValueError("credential rejected")


def credentials_json(**overrides: str) -> str:
    values = {
        "type": "service_account",
        "client_email": "service@example.test",
        "private_key": "private-key-value",
        "token_uri": "https://oauth2.test/token",
        "private_key_id": "private-key-id",
    }
    values.update(overrides)
    return json.dumps(values)


def config(sites: tuple[str, ...] = ("sc-domain:noveltissues.com",)) -> GoogleSearchConsoleConfig:
    return GoogleSearchConsoleConfig(credentials_json(), sites, "https://gsc.test/sites")


def client(
    configuration: GoogleSearchConsoleConfig,
    handler: httpx.MockTransport,
    *,
    credential_factory: object = FakeCredentials,
) -> GoogleSearchConsoleClient:
    return GoogleSearchConsoleClient(
        configuration,
        transport=handler,
        credential_factory=credential_factory,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_gsc_verifies_one_configured_property() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer gsc-access-token"
        return httpx.Response(200, json={"siteEntry": [{"siteUrl": "sc-domain:noveltissues.com"}]})

    async with client(config(), httpx.MockTransport(handler)) as source:
        await source.verify_connection()


@pytest.mark.asyncio
async def test_gsc_verifies_every_configured_property() -> None:
    sites = ("sc-domain:noveltissues.com", "https://www.noveltissues.com/")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"siteEntry": [{"siteUrl": site} for site in sites]})

    async with client(config(sites), httpx.MockTransport(handler)) as source:
        await source.verify_connection()


@pytest.mark.asyncio
async def test_gsc_reports_one_inaccessible_property() -> None:
    sites = ("sc-domain:noveltissues.com", "https://www.noveltissues.com/")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"siteEntry": [{"siteUrl": sites[0]}]})

    async with client(config(sites), httpx.MockTransport(handler)) as source:
        with pytest.raises(GoogleSearchConsolePropertyUnavailableError) as error:
            await source.verify_connection()
    assert_no_secrets(str(error.value))


@pytest.mark.asyncio
async def test_gsc_missing_or_malformed_configuration_is_safe() -> None:
    missing = GoogleSearchConsoleConfig("", ("sc-domain:noveltissues.com",))
    async with client(missing, httpx.MockTransport(lambda _: httpx.Response(200))) as source:
        with pytest.raises(GoogleSearchConsoleConfigurationError) as missing_error:
            await source.verify_connection()
    assert_no_secrets(str(missing_error.value))

    malformed = GoogleSearchConsoleConfig("not-json", ("sc-domain:noveltissues.com",))
    async with client(malformed, httpx.MockTransport(lambda _: httpx.Response(200))) as source:
        with pytest.raises(GoogleSearchConsoleConfigurationError):
            await source.verify_connection()


@pytest.mark.asyncio
async def test_gsc_incomplete_credentials_and_token_rejection_are_typed() -> None:
    incomplete = GoogleSearchConsoleConfig(
        credentials_json(private_key=""), ("sc-domain:noveltissues.com",)
    )
    async with client(incomplete, httpx.MockTransport(lambda _: httpx.Response(200))) as source:
        with pytest.raises(GoogleSearchConsoleConfigurationError):
            await source.verify_connection()

    async with client(
        config(),
        httpx.MockTransport(lambda _: httpx.Response(200)),
        credential_factory=RejectedCredentials,
    ) as source:
        with pytest.raises(GoogleSearchConsoleAuthenticationError) as error:
            await source.verify_connection()
    assert_no_secrets(str(error.value))


@pytest.mark.asyncio
async def test_gsc_permission_and_property_errors_are_typed() -> None:
    async with client(config(), httpx.MockTransport(lambda _: httpx.Response(403))) as source:
        with pytest.raises(GoogleSearchConsolePermissionError):
            await source.verify_connection()


@pytest.mark.asyncio
async def test_gsc_rate_limit_preserves_retry_after() -> None:
    async with client(
        config(), httpx.MockTransport(lambda _: httpx.Response(429, headers={"Retry-After": "15"}))
    ) as source:
        with pytest.raises(GoogleSearchConsoleRateLimitError) as error:
            await source.verify_connection()
    assert error.value.retry_after == "15"
    assert_no_secrets(str(error.value))


@pytest.mark.asyncio
async def test_gsc_timeout_and_transport_failure_are_safe() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with client(config(), httpx.MockTransport(timeout_handler)) as source:
        with pytest.raises(GoogleSearchConsoleNetworkError) as error:
            await source.verify_connection()
    assert_no_secrets(str(error.value))

    def transport_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    async with client(config(), httpx.MockTransport(transport_handler)) as source:
        with pytest.raises(GoogleSearchConsoleNetworkError) as transport_error:
            await source.verify_connection()
    assert_no_secrets(str(transport_error.value))


@pytest.mark.asyncio
async def test_gsc_malformed_and_empty_responses_are_typed() -> None:
    async with client(
        config(), httpx.MockTransport(lambda _: httpx.Response(200, content=b"not-json"))
    ) as source:
        with pytest.raises(GoogleSearchConsoleMalformedResponseError):
            await source.verify_connection()

    async with client(
        config(), httpx.MockTransport(lambda _: httpx.Response(200, json={"siteEntry": []}))
    ) as source:
        with pytest.raises(GoogleSearchConsoleEmptyResponseError):
            await source.verify_connection()


def assert_no_secrets(message: str) -> None:
    for secret in ("private-key-value", "private-key-id", "gsc-access-token"):
        assert secret not in message


def raw_request(start_row: int = 0) -> SyncRequest:
    return SyncRequest(
        "search_analytics",
        datetime(2026, 8, 1, tzinfo=UTC),
        datetime(2026, 8, 2, tzinfo=UTC),
        {
            "site": "sc-domain:noveltissues.com",
            "dimensions": ["query", "page"],
            "start_row": start_row,
        },
    )


@pytest.mark.asyncio
async def test_gsc_fetches_raw_search_analytics_page_and_keeps_body_exact() -> None:
    raw = b'{"rows":[{"keys":["wipes"]}]}'

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200, json={"siteEntry": [{"siteUrl": "sc-domain:noveltissues.com"}]}
            )
        return httpx.Response(200, content=raw, headers={"content-type": "application/json"})

    async with client(config(), httpx.MockTransport(handler)) as source:
        first = await source.fetch(raw_request())
        second = await source.fetch(raw_request())
        different = await source.fetch(raw_request(1))
    assert first[0].body == raw and first[0].source.value == "google_search_console"
    assert first[0].request_fingerprint == second[0].request_fingerprint
    assert first[0].request_fingerprint != different[0].request_fingerprint


def test_gsc_pagination_accepts_no_data_and_remains_deterministic() -> None:
    source = GoogleSearchConsoleClient(config())
    cursor = {"site": "sc-domain:noveltissues.com", "dimensions": ("query",), "start_row": 0}
    assert source._next_search_cursor(cursor, b"{}") is None
    assert source._next_search_cursor(cursor, b'{"rows": []}') is None
    assert source._next_search_cursor(cursor, b'{"rows": [{"keys": []}]}') is None
    with pytest.raises(GoogleSearchConsoleMalformedResponseError):
        source._next_search_cursor(cursor, b'{"rows": {}}')
    full_rows = json.dumps({"rows": [{}] * 25_000}).encode()
    assert source._next_search_cursor(cursor, full_rows)["start_row"] == 25_000

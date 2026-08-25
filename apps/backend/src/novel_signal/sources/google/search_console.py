"""Google Search Console connection and property-access verification."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx
import urllib3
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.urllib3 import Request as GoogleAuthRequest
from google.oauth2 import service_account

from novel_signal.config import Settings, get_settings
from novel_signal.sources.base import RawSourcePage, SourceType, SyncRequest

SOURCE_TYPE = SourceType.GOOGLE_SEARCH_CONSOLE
_GSC_READONLY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
_SITES_URL = "https://searchconsole.googleapis.com/webmasters/v3/sites"
_SEARCH_ANALYTICS_RESOURCE = "search_analytics"
_SEARCH_ANALYTICS_DIMENSIONS = ("query", "page", "country", "device", "date")
_SEARCH_ANALYTICS_ROW_LIMIT = 25_000


class GoogleSearchConsoleError(RuntimeError):
    """Base error raised while verifying Google Search Console access."""


class GoogleSearchConsoleConfigurationError(GoogleSearchConsoleError):
    """Credentials or configured properties are missing or unusable."""


class GoogleSearchConsoleAuthenticationError(GoogleSearchConsoleError):
    """Google rejected the configured service-account credentials."""


class GoogleSearchConsolePermissionError(GoogleSearchConsoleError):
    """Credentials cannot access the Search Console Sites resource."""


class GoogleSearchConsolePropertyUnavailableError(GoogleSearchConsoleError):
    """At least one configured property is not accessible to the credentials."""


class GoogleSearchConsoleRateLimitError(GoogleSearchConsoleError):
    """Google asked the caller to retry later."""

    def __init__(self, retry_after: str | None) -> None:
        self.retry_after = retry_after
        delay = retry_after or "an unspecified delay"
        super().__init__(f"Google Search Console rate limit; retry after {delay}.")


class GoogleSearchConsoleMalformedResponseError(GoogleSearchConsoleError):
    """Google returned a response that cannot establish property access."""


class GoogleSearchConsoleEmptyResponseError(GoogleSearchConsoleError):
    """Google returned a valid Sites response with no accessible properties."""


class GoogleSearchConsoleNetworkError(GoogleSearchConsoleError):
    """The verification request could not reach Google."""


class GoogleSearchConsoleUnsupportedOperationError(GoogleSearchConsoleError):
    """Collection is intentionally outside this verification-only slice."""


class GoogleSearchConsoleCursorError(GoogleSearchConsoleError):
    """The raw Search Analytics request cursor is missing or malformed."""


CredentialFactory = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class GoogleSearchConsoleConfig:
    """Service-account JSON and exact GSC properties to verify."""

    credentials_json: str = field(repr=False)
    sites: tuple[str, ...]
    sites_url: str = _SITES_URL

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> GoogleSearchConsoleConfig:
        current = settings or get_settings()
        return cls(
            credentials_json=current.google_search_console_credentials_json.get_secret_value(),
            sites=tuple(
                site.strip()
                for site in current.google_search_console_sites.split(",")
                if site.strip()
            ),
        )

    def credential_info(self) -> dict[str, Any]:
        if not self.credentials_json.strip():
            raise GoogleSearchConsoleConfigurationError(
                "Google Search Console credential configuration is missing."
            )
        try:
            parsed = json.loads(self.credentials_json)
        except json.JSONDecodeError as exc:
            raise GoogleSearchConsoleConfigurationError(
                "Google Search Console credentials are not valid JSON."
            ) from exc
        if not isinstance(parsed, dict):
            raise GoogleSearchConsoleConfigurationError(
                "Google Search Console credentials must be a JSON object."
            )
        required = ("type", "client_email", "private_key", "token_uri")
        if parsed.get("type") != "service_account" or any(
            not isinstance(parsed.get(field), str) or not parsed[field].strip()
            for field in required[1:]
        ):
            raise GoogleSearchConsoleConfigurationError(
                "Google Search Console credentials are not a usable service-account configuration."
            )
        return parsed

    def validate(self) -> dict[str, Any]:
        info = self.credential_info()
        if not self.sites:
            raise GoogleSearchConsoleConfigurationError(
                "No Google Search Console properties are configured."
            )
        return info


def _service_account_credentials(info: dict[str, Any]) -> Any:
    return service_account.Credentials.from_service_account_info(
        info,
        scopes=(_GSC_READONLY_SCOPE,),  # type: ignore[no-untyped-call]
    )


class GoogleSearchConsoleClient:
    """Verifies every configured GSC property using the low-cost Sites endpoint."""

    source_type = SOURCE_TYPE

    def __init__(
        self,
        config: GoogleSearchConsoleConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 45.0,
        credential_factory: CredentialFactory = _service_account_credentials,
    ) -> None:
        self.config = config
        self._credential_factory = credential_factory
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout)

    async def __aenter__(self) -> GoogleSearchConsoleClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def verify_connection(self) -> None:
        """Authenticate and confirm exact access to every configured property."""
        credential_info = self.config.validate()
        access_token = await self._access_token(credential_info)
        try:
            response = await self._client.get(
                self.config.sites_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.TimeoutException as exc:
            raise GoogleSearchConsoleNetworkError(
                "Google Search Console verification timed out."
            ) from exc
        except httpx.RequestError as exc:
            raise GoogleSearchConsoleNetworkError(
                "Google Search Console verification request failed."
            ) from exc

        if response.status_code == 401:
            raise GoogleSearchConsoleAuthenticationError(
                "Google Search Console authentication was rejected."
            )
        if response.status_code == 403:
            raise GoogleSearchConsolePermissionError("Google Search Console access was denied.")
        if response.status_code == 429:
            raise GoogleSearchConsoleRateLimitError(response.headers.get("Retry-After"))
        if response.is_error:
            raise GoogleSearchConsoleError(
                "Google Search Console verification request failed with status "
                f"{response.status_code}."
            )
        self._validate_sites_response(response)

    async def fetch(self, request: SyncRequest) -> tuple[RawSourcePage, ...]:
        """Fetch raw Search Analytics pages without parsing or publishing rows."""
        cursor = self._parse_search_cursor(request)
        await self.verify_connection()
        credential_info = self.config.validate()
        access_token = await self._access_token(credential_info)
        pages: list[RawSourcePage] = []
        while True:
            payload = self._search_payload(request, cursor)
            body, content_type = await self._search_analytics(cursor["site"], access_token, payload)
            next_cursor = self._next_search_cursor(cursor, body)
            pages.append(
                RawSourcePage(
                    source=SOURCE_TYPE,
                    resource_type=request.resource_type,
                    body=body,
                    content_type=content_type,
                    request_fingerprint=self._fingerprint(
                        request.resource_type, payload, cursor["site"]
                    ),
                    next_cursor=next_cursor,
                )
            )
            if next_cursor is None:
                return tuple(pages)
            cursor = next_cursor

    def _parse_search_cursor(self, request: SyncRequest) -> dict[str, Any]:
        if request.resource_type != _SEARCH_ANALYTICS_RESOURCE or not isinstance(
            request.cursor, dict
        ):
            raise GoogleSearchConsoleCursorError("Unsupported Google Search Console raw request.")
        site = request.cursor.get("site")
        if not isinstance(site, str) or not site.strip():
            raise GoogleSearchConsoleCursorError(
                "Search Analytics cursor requires a configured site."
            )
        if site not in self.config.sites:
            raise GoogleSearchConsolePropertyUnavailableError(
                "Requested Google Search Console property is not configured."
            )
        dimensions = request.cursor.get("dimensions", list(_SEARCH_ANALYTICS_DIMENSIONS))
        if (
            not isinstance(dimensions, list)
            or not dimensions
            or any(dimension not in _SEARCH_ANALYTICS_DIMENSIONS for dimension in dimensions)
            or len(set(dimensions)) != len(dimensions)
        ):
            raise GoogleSearchConsoleCursorError(
                "Search Analytics cursor contains invalid dimensions."
            )
        start_row = request.cursor.get("start_row", 0)
        if not isinstance(start_row, int) or start_row < 0:
            raise GoogleSearchConsoleCursorError(
                "Search Analytics start_row must be a non-negative integer."
            )
        return {"site": site, "dimensions": tuple(dimensions), "start_row": start_row}

    def _search_payload(self, request: SyncRequest, cursor: dict[str, Any]) -> dict[str, Any]:
        return {
            "startDate": request.window_start.date().isoformat(),
            "endDate": request.window_end.date().isoformat(),
            "dimensions": list(cursor["dimensions"]),
            "startRow": cursor["start_row"],
            "rowLimit": _SEARCH_ANALYTICS_ROW_LIMIT,
        }

    async def _search_analytics(
        self, site: str, access_token: str, payload: dict[str, Any]
    ) -> tuple[bytes, str]:
        base_url = self.config.sites_url.rstrip("/").rsplit("/sites", 1)[0]
        url = f"{base_url}/sites/{quote(site, safe='')}/searchAnalytics/query"
        try:
            response = await self._client.post(
                url, headers={"Authorization": f"Bearer {access_token}"}, json=payload
            )
        except httpx.TimeoutException as exc:
            raise GoogleSearchConsoleNetworkError(
                "Google Search Analytics request timed out."
            ) from exc
        except httpx.RequestError as exc:
            raise GoogleSearchConsoleNetworkError(
                "Google Search Analytics request failed."
            ) from exc
        if response.status_code == 401:
            raise GoogleSearchConsoleAuthenticationError(
                "Google Search Console authentication was rejected."
            )
        if response.status_code == 403:
            raise GoogleSearchConsolePermissionError("Google Search Console access was denied.")
        if response.status_code == 429:
            raise GoogleSearchConsoleRateLimitError(response.headers.get("Retry-After"))
        if response.is_error:
            raise GoogleSearchConsoleError(
                f"Google Search Analytics request failed with status {response.status_code}."
            )
        return response.content, response.headers.get("content-type", "application/json")

    def _next_search_cursor(self, cursor: dict[str, Any], body: bytes) -> dict[str, Any] | None:
        if not body:
            return None
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise GoogleSearchConsoleMalformedResponseError(
                "Google Search Analytics response was not valid JSON."
            ) from exc
        if not isinstance(payload, dict):
            raise GoogleSearchConsoleMalformedResponseError(
                "Google Search Analytics response was not a JSON object."
            )
        rows = payload.get("rows", [])
        if not isinstance(rows, list):
            raise GoogleSearchConsoleMalformedResponseError(
                "Google Search Analytics response did not contain a rows list."
            )
        if len(rows) < _SEARCH_ANALYTICS_ROW_LIMIT:
            return None
        return {
            "site": cursor["site"],
            "dimensions": cursor["dimensions"],
            "start_row": cursor["start_row"] + _SEARCH_ANALYTICS_ROW_LIMIT,
        }

    @staticmethod
    def _fingerprint(resource_type: str, payload: dict[str, Any], site: str) -> str:
        logical_request = json.dumps(
            {"site": site, "payload": payload}, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(f"{resource_type}\0{logical_request}".encode()).hexdigest()

    async def _access_token(self, credential_info: dict[str, Any]) -> str:
        try:
            credentials = self._credential_factory(credential_info)
            request = GoogleAuthRequest(urllib3.PoolManager())  # type: ignore[no-untyped-call]
            await asyncio.to_thread(credentials.refresh, request)
        except GoogleAuthError as exc:
            raise GoogleSearchConsoleAuthenticationError(
                "Google Search Console service-account authentication failed."
            ) from exc
        except (OSError, ValueError) as exc:
            raise GoogleSearchConsoleAuthenticationError(
                "Google Search Console service-account authentication failed."
            ) from exc
        token = getattr(credentials, "token", None)
        if not isinstance(token, str) or not token.strip():
            raise GoogleSearchConsoleAuthenticationError(
                "Google Search Console authentication did not return an access token."
            )
        return token

    def _validate_sites_response(self, response: httpx.Response) -> None:
        try:
            payload = response.json()
        except ValueError as exc:
            raise GoogleSearchConsoleMalformedResponseError(
                "Google Search Console Sites response was not valid JSON."
            ) from exc
        if not isinstance(payload, dict):
            raise GoogleSearchConsoleMalformedResponseError(
                "Google Search Console Sites response was not a JSON object."
            )
        entries = payload.get("siteEntry")
        if entries is None:
            raise GoogleSearchConsoleMalformedResponseError(
                "Google Search Console Sites response did not contain siteEntry."
            )
        if not isinstance(entries, list):
            raise GoogleSearchConsoleMalformedResponseError(
                "Google Search Console Sites response contained an invalid siteEntry value."
            )
        if not entries:
            raise GoogleSearchConsoleEmptyResponseError(
                "Google Search Console returned no accessible properties."
            )
        accessible_sites = {
            entry.get("siteUrl")
            for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("siteUrl"), str)
        }
        unavailable = [site for site in self.config.sites if site not in accessible_sites]
        if unavailable:
            raise GoogleSearchConsolePropertyUnavailableError(
                "Configured Google Search Console properties are unavailable."
            )

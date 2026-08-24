"""Google Search Console connection and property-access verification."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

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
        info, scopes=(_GSC_READONLY_SCOPE,)  # type: ignore[no-untyped-call]
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
        """Keep the source contract explicit until query ingestion is implemented."""
        del request
        raise GoogleSearchConsoleUnsupportedOperationError(
            "Google Search Console collection is not implemented in this verification slice."
        )

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

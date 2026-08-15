"""Small, raw-first Amazon Ads API client.

The client deliberately does not normalize or persist responses. Callers can store each
returned :class:`RawSourcePage` before handing it to a normalizer.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from novel_signal.config import Settings, get_settings
from novel_signal.sources.base import RawSourcePage, SourceType, SyncRequest

SOURCE_TYPE = SourceType.AMAZON_ADS_API


class AmazonAdsError(RuntimeError):
    """Base error raised by the Amazon Ads adapter."""


class AmazonAdsPermissionError(AmazonAdsError):
    """Credentials are valid but lack the requested profile/resource permission."""


class AmazonAdsRateLimitError(AmazonAdsError):
    """Amazon asked the caller to slow down."""


@dataclass(frozen=True)
class AmazonAdsConfig:
    client_id: str
    client_secret: str
    refresh_token: str
    profile_ids: tuple[str, ...]
    region: str = "eu-west-1"
    api_base_url: str = "https://advertising-api.amazon.com"
    token_url: str = "https://api.amazon.com/auth/o2/token"

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> AmazonAdsConfig:
        current = settings or get_settings()
        return cls(
            current.amazon_ads_client_id,
            current.amazon_ads_client_secret.get_secret_value(),
            current.amazon_ads_refresh_token.get_secret_value(),
            tuple(p.strip() for p in current.amazon_ads_profile_ids.split(",") if p.strip()),
            current.amazon_region,
        )


def _fingerprint(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


class AmazonAdsClient:
    source_type = SOURCE_TYPE

    def __init__(
        self, config: AmazonAdsConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.config = config
        self._client = httpx.AsyncClient(transport=transport, timeout=45.0)
        self._access_token: str | None = None

    async def __aenter__(self) -> AmazonAdsClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def _token(self) -> str:
        if self._access_token:
            return self._access_token
        response = await self._client.post(
            self.config.token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.config.refresh_token,
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
            },
        )
        if response.status_code in (401, 403):
            raise AmazonAdsPermissionError("Amazon Ads credentials were rejected")
        if response.status_code == 429:
            raise AmazonAdsRateLimitError("Amazon token endpoint rate limit")
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise AmazonAdsError("Amazon token response did not contain access_token")
        self._access_token = token
        return token

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> httpx.Response:
        token = await self._token()
        response = await self._client.get(
            f"{self.config.api_base_url.rstrip('/')}/{path.lstrip('/')}",
            headers={
                "Authorization": f"Bearer {token}",
                "Amazon-Advertising-API-ClientId": self.config.client_id,
            },
            params=params,
        )
        if response.status_code in (401, 403):
            raise AmazonAdsPermissionError(f"Amazon Ads permission denied for {path}")
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "unknown")
            raise AmazonAdsRateLimitError(f"Amazon Ads rate limit; retry after {retry_after}")
        response.raise_for_status()
        return response

    async def verify_connection(self) -> None:
        if not self.config.profile_ids:
            raise AmazonAdsPermissionError("No Amazon Ads profile is configured")
        response = await self._get("v2/profiles")
        profiles = response.json()
        if not isinstance(profiles, list):
            raise AmazonAdsError("Amazon profiles response was not a list")
        configured = {str(item.get("profileId")) for item in profiles if isinstance(item, dict)}
        missing = [profile for profile in self.config.profile_ids if profile not in configured]
        if missing:
            raise AmazonAdsPermissionError(
                f"Configured Amazon Ads profiles unavailable: {', '.join(missing)}"
            )

    async def fetch(self, request: SyncRequest) -> tuple[RawSourcePage, ...]:
        """Fetch every page for a resource and retain the requested date window."""
        pages: list[RawSourcePage] = []
        for profile_id in self.config.profile_ids:
            cursor: str | None = (request.cursor or {}).get(profile_id)
            async for page in self._pages(request, profile_id, cursor):
                pages.append(page)
        return tuple(pages)

    async def _pages(
        self, request: SyncRequest, profile_id: str, cursor: str | None
    ) -> AsyncIterator[RawSourcePage]:
        while True:
            params: dict[str, Any] = {"profileId": profile_id}
            if cursor:
                params["nextToken"] = cursor
            if request.resource_type in {
                "campaigns",
                "ad_groups",
                "ads",
                "insights",
                "search_terms",
            }:
                params.update(
                    {
                        "startDate": request.window_start.date().isoformat(),
                        "endDate": request.window_end.date().isoformat(),
                    }
                )
            response = await self._get(f"v2/{request.resource_type}", params=params)
            body = response.content
            payload = response.json()
            next_token = payload.get("nextToken") if isinstance(payload, dict) else None
            yield RawSourcePage(
                SOURCE_TYPE,
                request.resource_type,
                body,
                "application/json",
                _fingerprint(body),
                {profile_id: next_token} if next_token else None,
            )
            if not next_token:
                break
            cursor = str(next_token)

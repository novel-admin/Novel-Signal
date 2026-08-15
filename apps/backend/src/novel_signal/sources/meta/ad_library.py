"""Supported public Meta Ad Library adapter.

This adapter only calls the documented public endpoint. It never falls back to scraping
or attempts to use a private Marketing API account token as a substitute.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from novel_signal.config import Settings, get_settings
from novel_signal.sources.base import RawSourcePage, SourceType, SyncRequest

SOURCE_TYPE = SourceType.META_AD_LIBRARY


class MetaAdLibraryError(RuntimeError):
    """Base public Ad Library error."""


class MetaAdLibraryPermissionError(MetaAdLibraryError):
    """The public access token is missing or lacks the required permission."""


class MetaAdLibraryRateLimitError(MetaAdLibraryError):
    """The public endpoint is throttling this connection."""


@dataclass(frozen=True)
class MetaAdLibraryConfig:
    access_token: str
    country: str = "IN"
    api_version: str = "v20.0"
    api_base_url: str = "https://graph.facebook.com"

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> MetaAdLibraryConfig:
        current = settings or get_settings()
        return cls(current.meta_ad_library_access_token.get_secret_value())


def _fingerprint(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


class MetaAdLibraryClient:
    source_type = SOURCE_TYPE

    def __init__(
        self, config: MetaAdLibraryConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.config = config
        self._client = httpx.AsyncClient(transport=transport, timeout=45.0)

    async def __aenter__(self) -> MetaAdLibraryClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def verify_connection(self) -> None:
        if not self.config.access_token:
            raise MetaAdLibraryPermissionError("Meta Ad Library access token is required")
        await self._get(
            "ads_archive",
            {"ad_reached_countries": f'["{self.config.country}"]', "fields": "id", "limit": 1},
        )

    async def fetch(self, request: SyncRequest) -> tuple[RawSourcePage, ...]:
        pages: list[RawSourcePage] = []
        async for page in self._pages(request):
            pages.append(page)
        return tuple(pages)

    async def _pages(self, request: SyncRequest) -> AsyncIterator[RawSourcePage]:
        params: dict[str, Any] = {
            "ad_reached_countries": f'["{self.config.country}"]',
            "fields": "id,ad_creation_time,ad_delivery_start_time,ad_delivery_stop_time,page_id,page_name,ad_snapshot_url,impressions,spend",  # noqa: E501
            "search_terms": request.resource_type,
            "ad_active_status": "ALL",
            "limit": 100,
            "search_page_ids": request.resource_type if request.resource_type.isdigit() else None,
        }
        params = {key: value for key, value in params.items() if value is not None}
        response = await self._get("ads_archive", params)
        while True:
            body = response.content
            payload = response.json()
            paging = payload.get("paging", {}) if isinstance(payload, dict) else {}
            next_url = paging.get("next") if isinstance(paging, dict) else None
            yield RawSourcePage(
                SOURCE_TYPE, "ads_archive", body, "application/json", _fingerprint(body), None
            )
            if not next_url:
                break
            response = await self._get_absolute(next_url)

    async def _get(self, path: str, params: dict[str, Any]) -> httpx.Response:
        response = await self._client.get(
            f"{self.config.api_base_url.rstrip('/')}/{self.config.api_version}/{path}",
            params={**params, "access_token": self.config.access_token},
        )
        return self._validate(response)

    async def _get_absolute(self, url: str) -> httpx.Response:
        return self._validate(await self._client.get(url))

    @staticmethod
    def _validate(response: httpx.Response) -> httpx.Response:
        if response.status_code in (401, 403):
            raise MetaAdLibraryPermissionError("Meta Ad Library permission denied")
        if response.status_code == 429:
            raise MetaAdLibraryRateLimitError("Meta Ad Library rate limit")
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise MetaAdLibraryPermissionError(str(payload["error"]))
        return response

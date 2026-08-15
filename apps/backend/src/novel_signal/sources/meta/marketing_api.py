"""Raw-first Meta Marketing API adapter for owned ad accounts."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from novel_signal.config import Settings, get_settings
from novel_signal.sources.base import RawSourcePage, SourceType, SyncRequest

SOURCE_TYPE = SourceType.META_MARKETING_API


class MetaMarketingError(RuntimeError):
    """Base Meta API adapter error."""


class MetaMarketingPermissionError(MetaMarketingError):
    """The token or requested account/resource is not permitted."""


class MetaMarketingRateLimitError(MetaMarketingError):
    """Meta requested a retry after throttling."""


@dataclass(frozen=True)
class MetaMarketingConfig:
    access_token: str
    account_ids: tuple[str, ...]
    api_version: str = "v20.0"
    api_base_url: str = "https://graph.facebook.com"

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> MetaMarketingConfig:
        current = settings or get_settings()
        return cls(
            current.meta_access_token.get_secret_value(),
            tuple(
                p.strip().removeprefix("act_")
                for p in current.meta_ad_account_ids.split(",")
                if p.strip()
            ),
        )


def _fingerprint(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


class MetaMarketingClient:
    source_type = SOURCE_TYPE

    def __init__(
        self, config: MetaMarketingConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.config = config
        self._client = httpx.AsyncClient(transport=transport, timeout=45.0)

    async def __aenter__(self) -> MetaMarketingClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        response = await self._client.get(
            f"{self.config.api_base_url.rstrip('/')}/{self.config.api_version}/{path.lstrip('/')}",
            params={**(params or {}), "access_token": self.config.access_token},
        )
        if response.status_code in (401, 403):
            raise MetaMarketingPermissionError(f"Meta permission denied for {path}")
        if response.status_code == 429:
            raise MetaMarketingRateLimitError("Meta Marketing API rate limit")
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            error = payload["error"]
            if isinstance(error, dict) and error.get("code") in {10, 190, 200, 294}:
                raise MetaMarketingPermissionError(
                    str(error.get("message", "Meta permission denied"))
                )
        return response

    async def verify_connection(self) -> None:
        if not self.config.access_token or not self.config.account_ids:
            raise MetaMarketingPermissionError("Meta access token and ad account are required")
        for account_id in self.config.account_ids:
            await self._get(f"act_{account_id}", {"fields": "id,name,account_status"})

    async def fetch(self, request: SyncRequest) -> tuple[RawSourcePage, ...]:
        pages: list[RawSourcePage] = []
        for account_id in self.config.account_ids:
            async for page in self._pages(request, account_id):
                pages.append(page)
        return tuple(pages)

    async def _pages(self, request: SyncRequest, account_id: str) -> AsyncIterator[RawSourcePage]:
        params: dict[str, Any] = {
            "fields": self._fields(request.resource_type),
            "time_range": (
                f'{{"since":"{request.window_start.date().isoformat()}",'
                f'"until":"{request.window_end.date().isoformat()}"}}'
            ),
        }
        if request.cursor and account_id in request.cursor:
            params["after"] = request.cursor[account_id]
        response = await self._get(f"act_{account_id}/{request.resource_type}", params)
        while True:
            body = response.content
            payload = response.json()
            paging = payload.get("paging", {}) if isinstance(payload, dict) else {}
            next_url = paging.get("next") if isinstance(paging, dict) else None
            next_cursor = None
            if isinstance(paging, dict) and isinstance(paging.get("cursors"), dict):
                next_cursor = paging["cursors"].get("after")
            if next_cursor is None and isinstance(next_url, str):
                next_cursor = parse_qs(urlparse(next_url).query).get("after", [None])[0]
            yield RawSourcePage(
                SOURCE_TYPE,
                request.resource_type,
                body,
                "application/json",
                _fingerprint(body),
                {account_id: next_cursor} if next_cursor else None,
            )
            if not next_url:
                break
            response = await self._get_absolute(next_url)

    async def _get_absolute(self, url: str) -> httpx.Response:
        response = await self._client.get(url)
        if response.status_code in (401, 403):
            raise MetaMarketingPermissionError("Meta permission denied while following pagination")
        if response.status_code == 429:
            raise MetaMarketingRateLimitError("Meta Marketing API rate limit")
        response.raise_for_status()
        return response

    @staticmethod
    def _fields(resource_type: str) -> str:
        return {
            "campaigns": "id,name,status,objective,updated_time",
            "adsets": "id,campaign_id,name,status,targeting,updated_time",
            "ads": "id,adset_id,campaign_id,name,status,creative,updated_time",
            "creatives": "id,name,object_story_spec,asset_feed_spec",
            "insights": "account_id,campaign_id,adset_id,ad_id,impressions,clicks,spend,actions,date_start,date_stop",  # noqa: E501
        }.get(resource_type, "id,name,updated_time")

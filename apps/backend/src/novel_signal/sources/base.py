from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class SourceType(StrEnum):
    AMAZON_SP_API = "amazon_sp_api"
    AMAZON_ADS_API = "amazon_ads_api"
    AMAZON_BRAND_ANALYTICS = "amazon_brand_analytics"
    GOOGLE_SEARCH_CONSOLE = "google_search_console"
    META_MARKETING_API = "meta_marketing_api"
    META_AD_LIBRARY = "meta_ad_library"
    AMAZON_PUBLIC_PAGES = "amazon_public_pages"


@dataclass(frozen=True)
class SyncRequest:
    resource_type: str
    window_start: datetime
    window_end: datetime
    cursor: dict[str, Any] | None = None


@dataclass(frozen=True)
class RawSourcePage:
    source: SourceType
    resource_type: str
    body: bytes
    content_type: str
    request_fingerprint: str
    next_cursor: dict[str, Any] | None = None


class SourceAdapter(Protocol):
    source_type: SourceType

    async def verify_connection(self) -> None: ...

    async def fetch(self, request: SyncRequest) -> tuple[RawSourcePage, ...]: ...

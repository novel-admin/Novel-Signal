from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from novel_signal.config import get_settings
from novel_signal.sources.amazon.ads_api import AmazonAdsConfig
from novel_signal.sources.meta.ad_library import MetaAdLibraryConfig
from novel_signal.sources.meta.marketing_api import MetaMarketingConfig

router = APIRouter(prefix="/ads", tags=["S4 Ads"])


class SyncRequestBody(BaseModel):
    source: Literal["amazon_ads_api", "meta_marketing_api", "meta_ad_library"]
    resource_type: str
    window_start: datetime
    window_end: datetime


@router.get("/meta", name="S4 Ads_module_meta")
def module_meta() -> dict[str, str]:
    return {"module": "S4 Ads", "owner": "Palguna", "status": "ready"}


@router.get("/connections")
def connection_status() -> list[dict[str, object]]:
    settings = get_settings()
    amazon = AmazonAdsConfig.from_settings(settings)
    meta = MetaMarketingConfig.from_settings(settings)
    library = MetaAdLibraryConfig.from_settings(settings)
    return [
        {
            "source": "amazon_ads_api",
            "configured": bool(amazon.client_id and amazon.refresh_token and amazon.profile_ids),
        },
        {
            "source": "meta_marketing_api",
            "configured": bool(meta.access_token and meta.account_ids),
        },
        {"source": "meta_ad_library", "configured": bool(library.access_token)},
    ]


@router.post("/sync", status_code=202)
def request_sync(body: SyncRequestBody) -> dict[str, object]:
    """Queue boundary for the worker; persistence/queue wiring is owned by integration."""
    return {
        "status": "accepted",
        "source": body.source,
        "resource_type": body.resource_type,
        "accepted_at": datetime.now(UTC),
    }

# ruff: noqa: B008
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from novel_signal.config import get_settings
from novel_signal.db import get_db
from novel_signal.sources.amazon.ads_api import AmazonAdsConfig
from novel_signal.sources.meta.ad_library import MetaAdLibraryConfig
from novel_signal.sources.meta.marketing_api import MetaMarketingConfig

from .repository import (
    list_estimates,
    list_observations,
    list_presence,
    list_search_term_contributions,
)
from .schemas import (
    AdObservationCreate,
    AdObservationRead,
    AdPresenceRead,
    AdSummaryRead,
    DaypartDerive,
    DaypartRead,
    OwnPerformanceCreate,
    OwnPerformanceRead,
    PresenceDerive,
    PresenceUpsert,
    SearchTermContributionRead,
    SpendEstimateCreate,
    SpendEstimateRead,
)
from .service import (
    create_spend_estimate,
    derive_dayparts,
    derive_presence,
    record_observation,
    record_own_performance,
    summarize_ads,
    upsert_presence,
)

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


@router.post("/observations", response_model=AdObservationRead, status_code=201)
def create_observation(
    body: AdObservationCreate, db: Session = Depends(get_db)
) -> AdObservationRead:
    return AdObservationRead.model_validate(record_observation(db, body))


@router.get("/observations", response_model=list[AdObservationRead])
def get_observations(
    competitor_id: str | None = None,
    keyword_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[AdObservationRead]:
    return [
        AdObservationRead.model_validate(row)
        for row in list_observations(
            db, competitor_id=competitor_id, keyword_id=keyword_id, limit=limit
        )
    ]


@router.put("/presence/daily", response_model=AdPresenceRead, status_code=200)
def put_presence(body: PresenceUpsert, db: Session = Depends(get_db)) -> AdPresenceRead:
    return AdPresenceRead.model_validate(upsert_presence(db, body))


@router.post("/presence/derive", response_model=AdPresenceRead)
def post_derived_presence(body: PresenceDerive, db: Session = Depends(get_db)) -> AdPresenceRead:
    return AdPresenceRead.model_validate(derive_presence(db, body))


@router.post("/dayparts/derive", response_model=list[DaypartRead])
def post_derived_dayparts(body: DaypartDerive, db: Session = Depends(get_db)) -> list[DaypartRead]:
    return [DaypartRead.model_validate(row) for row in derive_dayparts(db, body)]


@router.get("/summary/{competitor_id}", response_model=AdSummaryRead)
def get_summary(competitor_id: str, db: Session = Depends(get_db)) -> AdSummaryRead:
    return summarize_ads(db, competitor_id)


@router.get("/presence/daily", response_model=list[AdPresenceRead])
def get_presence(
    competitor_id: str,
    keyword_id: str,
    limit: int = Query(default=90, ge=1, le=366),
    db: Session = Depends(get_db),
) -> list[AdPresenceRead]:
    return [
        AdPresenceRead.model_validate(row)
        for row in list_presence(
            db, competitor_id=competitor_id, keyword_id=keyword_id, limit=limit
        )
    ]


@router.post("/spend-estimates", response_model=SpendEstimateRead, status_code=201)
def post_estimate(body: SpendEstimateCreate, db: Session = Depends(get_db)) -> SpendEstimateRead:
    try:
        return SpendEstimateRead.model_validate(create_spend_estimate(db, body))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/spend-estimates", response_model=list[SpendEstimateRead])
def get_estimates(
    competitor_id: str, limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)
) -> list[SpendEstimateRead]:
    return [
        SpendEstimateRead.model_validate(row)
        for row in list_estimates(db, competitor_id=competitor_id, limit=limit)
    ]


@router.post("/own-performance", response_model=OwnPerformanceRead, status_code=201)
def post_own_performance(
    body: OwnPerformanceCreate, db: Session = Depends(get_db)
) -> OwnPerformanceRead:
    return OwnPerformanceRead.model_validate(record_own_performance(db, body))


@router.get("/search-term-contributions", response_model=list[SearchTermContributionRead])
def get_search_term_contributions(
    profile_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[SearchTermContributionRead]:
    return [
        SearchTermContributionRead.model_validate(row)
        for row in list_search_term_contributions(db, profile_id=profile_id, limit=limit)
    ]

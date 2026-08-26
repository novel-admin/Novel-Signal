import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from novel_signal.db import get_db
from novel_signal.modules.rank_visibility.errors import (
    RankVisibilityConflictError,
    RankVisibilityNotFoundError,
    RankVisibilityValidationError,
)
from novel_signal.modules.rank_visibility.models import (
    BadgeEventType,
    BadgeType,
    DeviceProfile,
)
from novel_signal.modules.rank_visibility.repository import RankVisibilityRepository
from novel_signal.modules.rank_visibility.schemas import (
    AmazonShareOfVoice,
    BadgeEventList,
    BadgeEventRead,
    BrandPresence,
    CaptureDetail,
    CaptureIngest,
    CaptureList,
    CaptureSummary,
    KeywordGapAnalysis,
    NewEntrantList,
    NewEntrantRead,
    RankHistory,
    ReverseAsinIntelligence,
    VisibilityMetrics,
)
from novel_signal.modules.rank_visibility.service import RankVisibilityService
from novel_signal.modules.universe.models import Marketplace

router = APIRouter(prefix="/rank-visibility", tags=["S3 Rank & Visibility"])
SessionDep = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]
FromDate = Annotated[datetime | None, Query(alias="from")]
ToDate = Annotated[datetime | None, Query(alias="to")]


def get_service(session: SessionDep) -> RankVisibilityService:
    return RankVisibilityService(session)


ServiceDep = Annotated[RankVisibilityService, Depends(get_service)]


def execute[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except RankVisibilityNotFoundError as error:
        raise HTTPException(404, detail={"code": error.code, "message": error.message}) from error
    except RankVisibilityConflictError as error:
        raise HTTPException(409, detail={"code": error.code, "message": error.message}) from error
    except RankVisibilityValidationError as error:
        raise HTTPException(422, detail={"code": error.code, "message": error.message}) from error


@router.get("/meta")
def module_meta() -> dict[str, str]:
    return {"module": "S3 Rank & Visibility", "status": "implemented"}


@router.post("/captures", response_model=CaptureDetail, status_code=201)
def ingest_capture(payload: CaptureIngest, service: ServiceDep) -> CaptureDetail:
    return CaptureDetail.model_validate(execute(lambda: service.ingest(payload)))


@router.get("/captures", response_model=CaptureList)
def list_captures(
    session: SessionDep,
    limit: Limit = 50,
    offset: Offset = 0,
    keyword_id: uuid.UUID | None = None,
    marketplace: Marketplace | None = None,
    geo_code: str | None = None,
    device_profile: DeviceProfile | None = None,
    from_at: FromDate = None,
    to_at: ToDate = None,
) -> CaptureList:
    items, total = RankVisibilityRepository(session).list_captures(
        limit=limit,
        offset=offset,
        keyword_id=keyword_id,
        marketplace=marketplace,
        geo_code=geo_code,
        device_profile=device_profile,
        from_at=from_at,
        to_at=to_at,
    )
    return CaptureList(
        items=[CaptureSummary.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/captures/{capture_id}", response_model=CaptureDetail)
def get_capture(capture_id: uuid.UUID, service: ServiceDep) -> CaptureDetail:
    return CaptureDetail.model_validate(execute(lambda: service.get_capture(capture_id)))


def history_filters(
    keyword_id: uuid.UUID,
    product_id: uuid.UUID | None,
    competitor_product_id: uuid.UUID | None,
    marketplace_product_id: str | None,
    marketplace: Marketplace | None,
    geo_code: str | None,
    device_profile: DeviceProfile | None,
    from_at: datetime | None,
    to_at: datetime | None,
) -> dict[str, object]:
    return {
        "keyword_id": keyword_id,
        "product_id": product_id,
        "competitor_product_id": competitor_product_id,
        "marketplace_product_id": marketplace_product_id,
        "marketplace": marketplace,
        "geo_code": geo_code,
        "device_profile": device_profile,
        "from_at": from_at,
        "to_at": to_at,
    }


@router.get("/rank-history", response_model=RankHistory)
def rank_history(
    service: ServiceDep,
    keyword_id: uuid.UUID,
    product_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
    marketplace_product_id: str | None = None,
    marketplace: Marketplace | None = None,
    geo_code: str | None = None,
    device_profile: DeviceProfile | None = None,
    from_at: FromDate = None,
    to_at: ToDate = None,
) -> RankHistory:
    filters = history_filters(
        keyword_id,
        product_id,
        competitor_product_id,
        marketplace_product_id,
        marketplace,
        geo_code,
        device_profile,
        from_at,
        to_at,
    )
    return execute(lambda: service.rank_history(**filters))  # type: ignore[arg-type]


@router.get("/visibility", response_model=VisibilityMetrics)
def visibility(
    service: ServiceDep,
    keyword_id: uuid.UUID,
    product_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
    marketplace_product_id: str | None = None,
    marketplace: Marketplace | None = None,
    geo_code: str | None = None,
    device_profile: DeviceProfile | None = None,
    from_at: FromDate = None,
    to_at: ToDate = None,
) -> VisibilityMetrics:
    filters = history_filters(
        keyword_id,
        product_id,
        competitor_product_id,
        marketplace_product_id,
        marketplace,
        geo_code,
        device_profile,
        from_at,
        to_at,
    )
    return execute(lambda: service.visibility(**filters))


@router.get("/brand-presence", response_model=BrandPresence)
def brand_presence(
    service: ServiceDep,
    capture_id: uuid.UUID | None = None,
    keyword_id: uuid.UUID | None = None,
    from_at: FromDate = None,
    to_at: ToDate = None,
) -> BrandPresence:
    return execute(
        lambda: service.brand_presence(
            capture_id=capture_id, keyword_id=keyword_id, from_at=from_at, to_at=to_at
        )
    )


@router.get("/reverse-asin", response_model=ReverseAsinIntelligence)
def reverse_asin(
    service: ServiceDep,
    product_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
    marketplace_product_id: str | None = None,
    marketplace: Marketplace | None = Marketplace.AMAZON_IN,
    geo_code: str | None = None,
    device_profile: DeviceProfile | None = None,
    from_at: FromDate = None,
    to_at: ToDate = None,
) -> ReverseAsinIntelligence:
    return execute(
        lambda: service.reverse_asin(
            product_id=product_id,
            competitor_product_id=competitor_product_id,
            marketplace_product_id=marketplace_product_id,
            marketplace=marketplace,
            geo_code=geo_code,
            device_profile=device_profile,
            from_at=from_at,
            to_at=to_at,
        )
    )


@router.get("/amazon-share-of-voice", response_model=AmazonShareOfVoice)
def amazon_share_of_voice(
    service: ServiceDep,
    capture_id: uuid.UUID,
    brand: str | None = None,
    product_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
    marketplace_product_id: str | None = None,
) -> AmazonShareOfVoice:
    return execute(
        lambda: service.share_of_voice(
            capture_id=capture_id,
            brand=brand,
            product_id=product_id,
            competitor_product_id=competitor_product_id,
            marketplace_product_id=marketplace_product_id,
        )
    )


@router.get("/keyword-gaps", response_model=KeywordGapAnalysis)
def keyword_gaps(
    service: ServiceDep,
    owned_product_id: uuid.UUID,
    competitor_product_id: uuid.UUID,
    geo_code: str | None = None,
    device_profile: DeviceProfile | None = None,
    from_at: FromDate = None,
    to_at: ToDate = None,
) -> KeywordGapAnalysis:
    return execute(
        lambda: service.keyword_gaps(
            owned_product_id=owned_product_id,
            competitor_product_id=competitor_product_id,
            geo_code=geo_code,
            device_profile=device_profile,
            from_at=from_at,
            to_at=to_at,
        )
    )


@router.get("/badge-events", response_model=BadgeEventList)
def badge_events(
    session: SessionDep,
    limit: Limit = 50,
    offset: Offset = 0,
    keyword_id: uuid.UUID | None = None,
    marketplace_product_id: str | None = None,
    badge_type: BadgeType | None = None,
    event_type: BadgeEventType | None = None,
    from_at: FromDate = None,
    to_at: ToDate = None,
) -> BadgeEventList:
    items, total = RankVisibilityRepository(session).list_badge_events(
        limit=limit,
        offset=offset,
        keyword_id=keyword_id,
        marketplace_product_id=marketplace_product_id,
        badge_type=badge_type,
        event_type=event_type,
        from_at=from_at,
        to_at=to_at,
    )
    return BadgeEventList(
        items=[BadgeEventRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/new-entrants", response_model=NewEntrantList)
def new_entrants(
    session: SessionDep,
    limit: Limit = 50,
    offset: Offset = 0,
    keyword_id: uuid.UUID | None = None,
    brand: str | None = None,
    mapped: bool | None = None,
    from_at: FromDate = None,
    to_at: ToDate = None,
) -> NewEntrantList:
    items, total = RankVisibilityRepository(session).list_new_entrants(
        limit=limit,
        offset=offset,
        keyword_id=keyword_id,
        brand=brand,
        mapped=mapped,
        from_at=from_at,
        to_at=to_at,
    )
    return NewEntrantList(
        items=[NewEntrantRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )

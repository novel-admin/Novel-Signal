import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from novel_signal.db import get_db
from novel_signal.modules.price_monitoring.errors import (
    PriceConflict,
    PriceNotFound,
    PriceValidation,
)
from novel_signal.modules.price_monitoring.models import AvailabilityStatus, PriceEventType
from novel_signal.modules.price_monitoring.repository import PriceRepository
from novel_signal.modules.price_monitoring.schemas import (
    LatestPrice,
    PriceChangeEventList,
    PriceChangeEventRead,
    PriceComparison,
    PriceHistoryList,
    PriceHistoryRow,
    PriceMetrics,
    PriceObservationIn,
    PriceObservationList,
    PriceObservationRead,
    SellerOfferRead,
)
from novel_signal.modules.price_monitoring.service import PriceService
from novel_signal.modules.universe.models import Marketplace

router = APIRouter(prefix="/price-monitoring", tags=["S6 Price Monitoring"])
SessionDep = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]
FromDate = Annotated[datetime | None, Query(alias="from")]
ToDate = Annotated[datetime | None, Query(alias="to")]


def service(session: SessionDep) -> PriceService:
    return PriceService(session)


ServiceDep = Annotated[PriceService, Depends(service)]


def execute[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except PriceNotFound as error:
        raise HTTPException(404, detail={"code": error.code, "message": error.message}) from error
    except PriceConflict as error:
        raise HTTPException(409, detail={"code": error.code, "message": error.message}) from error
    except PriceValidation as error:
        raise HTTPException(422, detail={"code": error.code, "message": error.message}) from error


def validate_dates(from_at: datetime | None, to_at: datetime | None) -> None:
    if from_at and to_at and from_at > to_at:
        raise PriceValidation("from must not be after to")


@router.get("/meta")
def meta() -> dict[str, str]:
    return {"module": "S6 Price Monitoring", "status": "implemented"}


@router.post("/observations", response_model=PriceObservationRead, status_code=201)
def ingest(payload: PriceObservationIn, s: ServiceDep) -> PriceObservationRead:
    return PriceObservationRead.model_validate(execute(lambda: s.ingest(payload)))


@router.get("/observations", response_model=PriceObservationList)
def observations(
    session: SessionDep,
    limit: Limit = 50,
    offset: Offset = 0,
    product_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
    marketplace_product_id: str | None = None,
    marketplace: Marketplace | None = None,
    geo_code: str | None = None,
    availability: AvailabilityStatus | None = None,
    from_at: FromDate = None,
    to_at: ToDate = None,
) -> PriceObservationList:
    execute(lambda: validate_dates(from_at, to_at))
    items, total = PriceRepository(session).observations(
        limit=limit,
        offset=offset,
        product_id=product_id,
        competitor_product_id=competitor_product_id,
        marketplace_product_id=marketplace_product_id,
        marketplace=marketplace,
        geo_code=geo_code,
        availability=availability,
        from_at=from_at,
        to_at=to_at,
    )
    return PriceObservationList(
        items=[PriceObservationRead.model_validate(x) for x in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/observations/{observation_id}", response_model=PriceObservationRead)
def observation(observation_id: uuid.UUID, s: ServiceDep) -> PriceObservationRead:
    return PriceObservationRead.model_validate(execute(lambda: s.get(observation_id)))


@router.get("/observations/{observation_id}/offers", response_model=list[SellerOfferRead])
def offers(observation_id: uuid.UUID, session: SessionDep, s: ServiceDep) -> list[SellerOfferRead]:
    execute(lambda: s.get(observation_id))
    return [
        SellerOfferRead.model_validate(x) for x in PriceRepository(session).offers(observation_id)
    ]


@router.get("/latest", response_model=LatestPrice)
def latest(
    s: ServiceDep,
    product_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
    marketplace_product_id: str | None = None,
    geo_code: str | None = None,
) -> LatestPrice:
    item = execute(
        lambda: s.latest(product_id, competitor_product_id, marketplace_product_id, geo_code)
    )
    return LatestPrice(
        observation=PriceObservationRead.model_validate(item), freshness=s.freshness(item)
    )


@router.get("/history", response_model=PriceHistoryList)
def history(
    session: SessionDep,
    s: ServiceDep,
    limit: Limit = 50,
    offset: Offset = 0,
    product_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
    marketplace_product_id: str | None = None,
    geo_code: str | None = None,
    from_at: FromDate = None,
    to_at: ToDate = None,
) -> PriceHistoryList:
    execute(lambda: s.identity(product_id, competitor_product_id, marketplace_product_id))
    execute(lambda: validate_dates(from_at, to_at))
    rows, total = PriceRepository(session).observations(
        limit=limit,
        offset=offset,
        product_id=product_id,
        competitor_product_id=competitor_product_id,
        marketplace_product_id=marketplace_product_id,
        geo_code=geo_code,
        from_at=from_at,
        to_at=to_at,
        ascending=True,
    )
    return PriceHistoryList(
        items=[
            PriceHistoryRow(
                id=x.id,
                observed_at=x.observed_at,
                primary_price=x.primary_price,
                mrp=x.list_price,
                effective_price=x.effective_price,
                discount_percent=x.discount_percent,
                coupon_text=x.coupon_text,
                shipping_amount=x.shipping_amount,
                availability_status=x.availability_status,
                seller_count=x.seller_count,
                primary_seller_name=x.primary_seller_name,
                geo_code=x.geo_code,
                currency=x.currency,
            )
            for x in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/metrics", response_model=PriceMetrics)
def metrics(
    s: ServiceDep,
    product_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
    marketplace_product_id: str | None = None,
    geo_code: str | None = None,
    from_at: FromDate = None,
    to_at: ToDate = None,
) -> PriceMetrics:
    return execute(
        lambda: s.metrics(
            product_id=product_id,
            competitor_product_id=competitor_product_id,
            marketplace_product_id=marketplace_product_id,
            geo_code=geo_code,
            from_at=from_at,
            to_at=to_at,
        )
    )


@router.get("/events", response_model=PriceChangeEventList)
def events(
    session: SessionDep,
    limit: Limit = 50,
    offset: Offset = 0,
    product_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
    marketplace_product_id: str | None = None,
    event_type: PriceEventType | None = None,
    geo_code: str | None = None,
    from_at: FromDate = None,
    to_at: ToDate = None,
) -> PriceChangeEventList:
    execute(lambda: validate_dates(from_at, to_at))
    items, total = PriceRepository(session).events(
        limit=limit,
        offset=offset,
        product_id=product_id,
        competitor_product_id=competitor_product_id,
        marketplace_product_id=marketplace_product_id,
        event_type=event_type,
        geo_code=geo_code,
        from_at=from_at,
        to_at=to_at,
    )
    return PriceChangeEventList(
        items=[PriceChangeEventRead.model_validate(x) for x in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/comparison", response_model=PriceComparison)
def comparison(
    product_id: uuid.UUID,
    competitor_product_id: uuid.UUID,
    s: ServiceDep,
    geo_code: str | None = None,
) -> PriceComparison:
    return execute(lambda: s.comparison(product_id, competitor_product_id, geo_code))

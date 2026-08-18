import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from novel_signal.db import get_db
from novel_signal.modules.listings.errors import ListingConflict, ListingNotFound, ListingValidation
from novel_signal.modules.listings.models import ListingChangeType
from novel_signal.modules.listings.repository import ListingRepository
from novel_signal.modules.listings.schemas import (
    ChangeList,
    ChangeRead,
    Comparison,
    Completeness,
    HistoryList,
    HistoryRow,
    SnapshotIn,
    SnapshotList,
    SnapshotRead,
)
from novel_signal.modules.listings.service import ListingService
from novel_signal.modules.universe.models import Marketplace

router = APIRouter(prefix="/listing-intelligence", tags=["S5 Listing Intelligence"])
legacy_router = APIRouter(prefix="/listings", tags=["S5 Listing Intelligence"])
SessionDep = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]
FromDate = Annotated[datetime | None, Query(alias="from")]
ToDate = Annotated[datetime | None, Query(alias="to")]


def service(session: SessionDep) -> ListingService:
    return ListingService(session)


ServiceDep = Annotated[ListingService, Depends(service)]


def execute[T](op: Callable[[], T]) -> T:
    try:
        return op()
    except ListingNotFound as e:
        raise HTTPException(404, detail={"code": e.code, "message": e.message}) from e
    except ListingConflict as e:
        raise HTTPException(409, detail={"code": e.code, "message": e.message}) from e
    except ListingValidation as e:
        raise HTTPException(422, detail={"code": e.code, "message": e.message}) from e


@router.get("/meta")
@legacy_router.get("/meta")
def meta() -> dict[str, str]:
    return {"module": "S5 Listing Intelligence", "status": "implemented"}


@router.post("/snapshots", response_model=SnapshotRead, status_code=201)
def ingest(payload: SnapshotIn, s: ServiceDep) -> SnapshotRead:
    return SnapshotRead.model_validate(execute(lambda: s.ingest(payload)))


@router.get("/snapshots", response_model=SnapshotList)
def snapshots(
    session: SessionDep,
    limit: Limit = 50,
    offset: Offset = 0,
    product_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
    marketplace_product_id: str | None = None,
    marketplace: Marketplace | None = None,
    from_at: FromDate = None,
    to_at: ToDate = None,
) -> SnapshotList:
    items, total = ListingRepository(session).snapshots(
        limit=limit,
        offset=offset,
        product_id=product_id,
        competitor_product_id=competitor_product_id,
        marketplace_product_id=marketplace_product_id,
        marketplace=marketplace,
        from_at=from_at,
        to_at=to_at,
    )
    return SnapshotList(
        items=[SnapshotRead.model_validate(x) for x in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotRead)
def snapshot(snapshot_id: uuid.UUID, s: ServiceDep) -> SnapshotRead:
    return SnapshotRead.model_validate(execute(lambda: s.get(snapshot_id)))


@router.get("/latest", response_model=SnapshotRead)
def latest(
    s: ServiceDep,
    product_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
    marketplace_product_id: str | None = None,
) -> SnapshotRead:
    return SnapshotRead.model_validate(
        execute(lambda: s.latest(product_id, competitor_product_id, marketplace_product_id))
    )


@router.get("/history", response_model=HistoryList)
def history(
    session: SessionDep,
    s: ServiceDep,
    limit: Limit = 50,
    offset: Offset = 0,
    product_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
    marketplace_product_id: str | None = None,
    from_at: FromDate = None,
    to_at: ToDate = None,
) -> HistoryList:
    execute(lambda: s.identity(product_id, competitor_product_id, marketplace_product_id))
    items, total = ListingRepository(session).snapshots(
        limit=limit,
        offset=offset,
        product_id=product_id,
        competitor_product_id=competitor_product_id,
        marketplace_product_id=marketplace_product_id,
        from_at=from_at,
        to_at=to_at,
        ascending=True,
    )
    return HistoryList(
        items=[
            HistoryRow(
                id=x.id,
                captured_at=x.captured_at,
                title=x.title,
                bullet_count=len(x.bullets),
                image_count=x.image_count,
                a_plus_present=x.a_plus_present,
                video_present=x.video_present,
                variation_count=x.variation_count,
                completeness_score=x.completeness_score,
            )
            for x in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/changes", response_model=ChangeList)
def changes(
    session: SessionDep,
    limit: Limit = 50,
    offset: Offset = 0,
    product_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
    marketplace_product_id: str | None = None,
    field_name: str | None = None,
    change_type: ListingChangeType | None = None,
    from_at: FromDate = None,
    to_at: ToDate = None,
) -> ChangeList:
    items, total = ListingRepository(session).changes(
        limit=limit,
        offset=offset,
        product_id=product_id,
        competitor_product_id=competitor_product_id,
        marketplace_product_id=marketplace_product_id,
        field_name=field_name,
        change_type=change_type,
        from_at=from_at,
        to_at=to_at,
    )
    return ChangeList(
        items=[ChangeRead.model_validate(x) for x in items], total=total, limit=limit, offset=offset
    )


@router.get("/comparison", response_model=Comparison)
def comparison(
    product_id: uuid.UUID, competitor_product_id: uuid.UUID, s: ServiceDep
) -> Comparison:
    return execute(lambda: s.comparison(product_id, competitor_product_id))


@router.get("/completeness", response_model=Completeness)
def completeness(
    s: ServiceDep,
    product_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
    marketplace_product_id: str | None = None,
) -> Completeness:
    return execute(
        lambda: s.completeness(
            product_id=product_id,
            competitor_product_id=competitor_product_id,
            marketplace_product_id=marketplace_product_id,
        )
    )

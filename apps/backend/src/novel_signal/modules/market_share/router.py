# ruff: noqa: B008

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from novel_signal.db import get_db

from .models import MarketShareDaily, ModelBacktest, UnitsEstimate, UnitsModelFit
from .schemas import (
    BacktestCreate,
    BacktestRead,
    MarketShareCreate,
    MarketShareRead,
    ModelFitCreate,
    ModelFitRead,
    Page,
    UnitsEstimateCreate,
    UnitsEstimateRead,
)
from .service import (
    MarketShareError,
    create_backtest,
    create_estimate,
    create_model_fit,
    create_share,
    list_items,
)

router = APIRouter(prefix="/market-share", tags=["S8 Market Share"])


@router.get("/meta")
def module_meta() -> dict[str, str]:
    return {"module": "S8 Market Share", "owner": "Palguna", "status": "ready"}


def page(items: list[Any], limit: int, schema: type[Any]) -> Page:
    has_more = len(items) > limit
    visible = items[:limit]
    return Page(
        items=[schema.model_validate(item) for item in visible],
        next_cursor=visible[-1].id if has_more and visible else None,
    )


@router.post("/model-fits", response_model=ModelFitRead, status_code=status.HTTP_201_CREATED)
def post_model_fit(data: ModelFitCreate, db: Session = Depends(get_db)) -> ModelFitRead:
    return ModelFitRead.model_validate(create_model_fit(db, data))


@router.get("/model-fits", response_model=Page)
def get_model_fits(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    db: Session = Depends(get_db),
) -> Page:
    return page(list_items(db, UnitsModelFit, limit=limit, cursor=cursor), limit, ModelFitRead)


@router.post("/estimates", response_model=UnitsEstimateRead, status_code=status.HTTP_201_CREATED)
def post_estimate(data: UnitsEstimateCreate, db: Session = Depends(get_db)) -> UnitsEstimateRead:
    try:
        return UnitsEstimateRead.model_validate(create_estimate(db, data))
    except MarketShareError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/estimates", response_model=Page)
def get_estimates(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    db: Session = Depends(get_db),
) -> Page:
    return page(list_items(db, UnitsEstimate, limit=limit, cursor=cursor), limit, UnitsEstimateRead)


@router.post("/shares", response_model=MarketShareRead, status_code=status.HTTP_201_CREATED)
def post_share(data: MarketShareCreate, db: Session = Depends(get_db)) -> MarketShareRead:
    return MarketShareRead.model_validate(create_share(db, data))


@router.get("/shares", response_model=Page)
def get_shares(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    db: Session = Depends(get_db),
) -> Page:
    return page(
        list_items(db, MarketShareDaily, limit=limit, cursor=cursor),
        limit,
        MarketShareRead,
    )


@router.post("/backtests", response_model=BacktestRead, status_code=status.HTTP_201_CREATED)
def post_backtest(data: BacktestCreate, db: Session = Depends(get_db)) -> BacktestRead:
    try:
        return BacktestRead.model_validate(create_backtest(db, data))
    except MarketShareError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/backtests", response_model=Page)
def get_backtests(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    db: Session = Depends(get_db),
) -> Page:
    return page(list_items(db, ModelBacktest, limit=limit, cursor=cursor), limit, BacktestRead)

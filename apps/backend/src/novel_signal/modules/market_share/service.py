from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import MarketShareDaily, ModelBacktest, UnitsEstimate, UnitsModelFit
from .schemas import BacktestCreate, MarketShareCreate, ModelFitCreate, UnitsEstimateCreate


class MarketShareError(Exception):
    """Expected domain error exposed as a 4xx response."""


def create_model_fit(session: Session, data: ModelFitCreate) -> UnitsModelFit:
    existing = session.scalar(
        select(UnitsModelFit).where(
            UnitsModelFit.platform == data.platform,
            UnitsModelFit.marketplace == data.marketplace,
            UnitsModelFit.category_node == data.category_node,
            UnitsModelFit.model_version == data.model_version,
        )
    )
    if existing:
        return existing
    fit = UnitsModelFit(**data.model_dump())
    session.add(fit)
    session.commit()
    session.refresh(fit)
    return fit


def create_estimate(session: Session, data: UnitsEstimateCreate) -> UnitsEstimate:
    fit = session.get(UnitsModelFit, data.model_fit_id)
    if not fit:
        raise MarketShareError("model fit not found")
    if fit.status != "active" or fit.model_version != data.model_version:
        raise MarketShareError("estimate must use the matching active model version")
    existing = session.scalar(
        select(UnitsEstimate).where(
            UnitsEstimate.entity_id == data.entity_id,
            UnitsEstimate.observed_on == data.observed_on,
            UnitsEstimate.model_version == data.model_version,
        )
    )
    if existing:
        return existing
    estimate = UnitsEstimate(**data.model_dump())
    session.add(estimate)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(UnitsEstimate).where(
                UnitsEstimate.entity_id == data.entity_id,
                UnitsEstimate.observed_on == data.observed_on,
                UnitsEstimate.model_version == data.model_version,
            )
        )
        if existing:
            return existing
        raise
    session.refresh(estimate)
    return estimate


def create_share(session: Session, data: MarketShareCreate) -> MarketShareDaily:
    existing = session.scalar(
        select(MarketShareDaily).where(
            MarketShareDaily.entity_id == data.entity_id,
            MarketShareDaily.observed_on == data.observed_on,
            MarketShareDaily.segment_key == data.segment_key,
            MarketShareDaily.model_version == data.model_version,
        )
    )
    if existing:
        return existing
    share = MarketShareDaily(**data.model_dump())
    session.add(share)
    session.commit()
    session.refresh(share)
    return share


def create_backtest(session: Session, data: BacktestCreate) -> ModelBacktest:
    if not session.get(UnitsModelFit, data.model_fit_id):
        raise MarketShareError("model fit not found")
    backtest = ModelBacktest(**data.model_dump())
    session.add(backtest)
    session.commit()
    session.refresh(backtest)
    return backtest


def list_items(session: Session, model: Any, *, limit: int, cursor: str | None) -> list[Any]:
    query: Any = select(model).order_by(model.id).limit(limit + 1)
    if cursor:
        query = query.where(model.id > cursor)
    return list(session.scalars(query))

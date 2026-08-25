# ruff: noqa: B008

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from novel_signal.db import get_db

from . import repository, service
from .schemas import (
    AlertEventCreate,
    AlertEventRead,
    AlertPage,
    AlertRuleCreate,
    AlertRuleRead,
    AlertTransition,
)

router = APIRouter(prefix="/alerts", tags=["S11 Alerts"])


@router.get("/meta")
def module_meta() -> dict[str, str]:
    return {"module": "S11 Alerts", "owner": "Palguna", "status": "implemented"}


@router.post("/rules", response_model=AlertRuleRead, status_code=status.HTTP_201_CREATED)
def post_rule(data: AlertRuleCreate, session: Session = Depends(get_db)) -> AlertRuleRead:
    return AlertRuleRead.model_validate(service.create_rule(session, data))


@router.get("/rules", response_model=list[AlertRuleRead])
def get_rules(session: Session = Depends(get_db)) -> list[AlertRuleRead]:
    return [AlertRuleRead.model_validate(row) for row in repository.list_rules(session)]


@router.post("", response_model=AlertEventRead, status_code=status.HTTP_201_CREATED)
def post_alert(data: AlertEventCreate, session: Session = Depends(get_db)) -> AlertEventRead:
    try:
        return AlertEventRead.model_validate(service.open_alert(session, data))
    except service.AlertError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("", response_model=AlertPage)
def get_alerts(
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    session: Session = Depends(get_db),
) -> AlertPage:
    rows = repository.list_alerts(session, limit=limit, cursor=cursor, status=status_filter)
    has_next = len(rows) > limit
    page = rows[:limit]
    return AlertPage(
        items=[AlertEventRead.model_validate(row) for row in page],
        next_cursor=page[-1].id if has_next and page else None,
    )


@router.post("/{alert_id}/transition", response_model=AlertEventRead)
def transition(
    alert_id: str, data: AlertTransition, session: Session = Depends(get_db)
) -> AlertEventRead:
    event = repository.get_alert(session, alert_id)
    if not event:
        raise HTTPException(status_code=404, detail="alert not found")
    try:
        return AlertEventRead.model_validate(service.transition_alert(session, event, data))
    except service.AlertError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

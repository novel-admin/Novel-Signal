# ruff: noqa: B008

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from novel_signal.db import get_db

from . import repository, service
from .schemas import (
    ActionCreate,
    ActionDetail,
    ActionRead,
    ActionTransition,
    ChangeEventCreate,
    ChangeEventRead,
    Page,
)

router = APIRouter(tags=["S10 Actions"])


@router.get("/actions/meta", name="S10 Actions_module_meta")
def module_meta() -> dict[str, str]:
    return {"module": "S10 Actions", "owner": "Palguna", "status": "ready"}


def _expected_error(error: service.ActionsError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


@router.post("/changes", response_model=ChangeEventRead, status_code=status.HTTP_201_CREATED)
def create_change(data: ChangeEventCreate, session: Session = Depends(get_db)) -> ChangeEventRead:
    return ChangeEventRead.model_validate(service.create_change(session, data))


@router.get("/changes", response_model=Page)
def changes(
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
    event_type: str | None = None,
    session: Session = Depends(get_db),
) -> Page:
    rows = repository.list_changes(session, limit=limit, cursor=cursor, event_type=event_type)
    has_next = len(rows) > limit
    rows = rows[:limit]
    return Page(
        items=[ChangeEventRead.model_validate(row) for row in rows],
        next_cursor=rows[-1].id if has_next and rows else None,
    )


@router.get("/changes/{event_id}", response_model=ChangeEventRead)
def change(event_id: str, session: Session = Depends(get_db)) -> ChangeEventRead:
    row = repository.get_change(session, event_id)
    if not row:
        raise HTTPException(status_code=404, detail="change event not found")
    return ChangeEventRead.model_validate(row)


@router.post(
    "/changes/{event_id}/actions", response_model=ActionRead, status_code=status.HTTP_201_CREATED
)
def create_action_from_change(
    event_id: str, data: ActionCreate, session: Session = Depends(get_db)
) -> ActionRead:
    if data.change_event_id != event_id:
        raise HTTPException(status_code=422, detail="change_event_id must match the path")
    try:
        return ActionRead.model_validate(service.create_action(session, data))
    except service.ActionsError as error:
        raise _expected_error(error) from error


@router.post("/actions", response_model=ActionRead, status_code=status.HTTP_201_CREATED)
def create_action(data: ActionCreate, session: Session = Depends(get_db)) -> ActionRead:
    try:
        return ActionRead.model_validate(service.create_action(session, data))
    except service.ActionsError as error:
        raise _expected_error(error) from error


@router.get("/actions", response_model=Page)
def actions(
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    session: Session = Depends(get_db),
) -> Page:
    rows = repository.list_actions(session, limit=limit, cursor=cursor, status=status_filter)
    has_next = len(rows) > limit
    rows = rows[:limit]
    return Page(
        items=[ActionRead.model_validate(row) for row in rows],
        next_cursor=rows[-1].id if has_next and rows else None,
    )


@router.get("/actions/{action_id}", response_model=ActionDetail)
def action(action_id: str, session: Session = Depends(get_db)) -> ActionDetail:
    row = repository.get_action(session, action_id)
    if not row:
        raise HTTPException(status_code=404, detail="action not found")
    return ActionDetail.model_validate(row)


@router.post("/actions/{action_id}/transition", response_model=ActionRead)
def transition(
    action_id: str, data: ActionTransition, session: Session = Depends(get_db)
) -> ActionRead:
    row = repository.get_action(session, action_id)
    if not row:
        raise HTTPException(status_code=404, detail="action not found")
    try:
        return ActionRead.model_validate(service.transition_action(session, row, data))
    except service.ActionsError as error:
        raise _expected_error(error) from error

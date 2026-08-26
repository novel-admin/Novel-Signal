# ruff: noqa: B008

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from novel_signal.db import get_db

from . import advisory, repository, service
from .schemas import (
    ActionCreate,
    ActionDetail,
    ActionDraftCreate,
    ActionDraftDecision,
    ActionDraftRead,
    ActionRead,
    ActionTransition,
    ChangeEventCreate,
    ChangeEventRead,
    GapCreate,
    GapRead,
    ImpactCreate,
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


@router.post("/gaps", response_model=GapRead, status_code=status.HTTP_201_CREATED)
def create_gap(data: GapCreate, session: Session = Depends(get_db)) -> GapRead:
    return GapRead.model_validate(service.create_gap(session, data))


@router.get("/gaps", response_model=Page)
def gaps(
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    session: Session = Depends(get_db),
) -> Page:
    rows = repository.list_gaps(session, limit=limit, cursor=cursor, status=status_filter)
    has_next = len(rows) > limit
    rows = rows[:limit]
    return Page(
        items=[GapRead.model_validate(row) for row in rows],
        next_cursor=rows[-1].id if has_next and rows else None,
    )


@router.post("/actions/{action_id}/impact", status_code=status.HTTP_201_CREATED)
def add_impact(
    action_id: str, data: ImpactCreate, session: Session = Depends(get_db)
) -> dict[str, str | int]:
    impact = service.add_impact(session, action_id, data)
    return {"id": impact.id, "action_id": impact.action_id, "days_after": impact.days_after}


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


@router.post(
    "/gaps/{gap_id}/actions", response_model=ActionRead, status_code=status.HTTP_201_CREATED
)
def create_action_from_gap(
    gap_id: str, data: ActionCreate, session: Session = Depends(get_db)
) -> ActionRead:
    if data.gap_id != gap_id:
        raise HTTPException(status_code=422, detail="gap_id must match the path")
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


@router.get("/action-drafts", response_model=list[ActionDraftRead])
def action_drafts(
    limit: int = Query(50, ge=1, le=100), session: Session = Depends(get_db)
) -> list[ActionDraftRead]:
    drafts = advisory.list_drafts(session, limit=limit)
    return [ActionDraftRead.model_validate(item) for item in drafts]


@router.post("/action-drafts", response_model=ActionDraftRead, status_code=status.HTTP_201_CREATED)
def create_action_draft(
    data: ActionDraftCreate, session: Session = Depends(get_db)
) -> ActionDraftRead:
    try:
        return ActionDraftRead.model_validate(advisory.create_draft(session, data))
    except advisory.ActionDraftError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/action-drafts/{draft_id}/decision", response_model=ActionDraftRead)
def decide_action_draft(
    draft_id: str, data: ActionDraftDecision, session: Session = Depends(get_db)
) -> ActionDraftRead:
    try:
        return ActionDraftRead.model_validate(
            advisory.decide_draft(session, draft_id, accepted=data.accepted)
        )
    except advisory.ActionDraftError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

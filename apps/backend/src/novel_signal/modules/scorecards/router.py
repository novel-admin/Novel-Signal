# ruff: noqa: B008

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from novel_signal.db import get_db

from .schemas import ScorecardPage, ScorecardRead, ScorecardUpsert
from .service import list_scorecards, upsert_scorecard

router = APIRouter(prefix="/scorecards", tags=["S9 Scorecards"])


@router.get("/meta")
def module_meta() -> dict[str, str]:
    return {"module": "S9 Scorecards", "owner": "Palguna", "status": "ready"}


@router.post("", response_model=ScorecardRead)
def create_scorecard(data: ScorecardUpsert, session: Session = Depends(get_db)) -> ScorecardRead:
    return ScorecardRead.model_validate(upsert_scorecard(session, data))


@router.get("", response_model=ScorecardPage)
def get_scorecards(
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    band: str | None = None,
    session: Session = Depends(get_db),
) -> ScorecardPage:
    rows = list_scorecards(session, limit=limit, cursor=cursor, band=band)
    has_next = len(rows) > limit
    rows = rows[:limit]
    return ScorecardPage(
        items=[ScorecardRead.model_validate(row) for row in rows],
        next_cursor=rows[-1].id if has_next and rows else None,
    )

# ruff: noqa: B008
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from novel_signal.db import get_db

from . import repository, service
from .schemas import Page, ReviewCreate, ReviewMetrics, ReviewRead, TopicSummary, TrendRead

router = APIRouter(prefix="/reviews", tags=["S7 Reviews"])


@router.get("/meta", name="S7 Reviews_module_meta")
def module_meta() -> dict[str, str]:
    return {"module": "S7 Reviews", "owner": "Palguna", "status": "ready"}


@router.post("", response_model=ReviewRead, status_code=201)
def create_review(data: ReviewCreate, session: Session = Depends(get_db)) -> ReviewRead:
    return ReviewRead.model_validate(service.ingest_review(session, data))


@router.get("", response_model=Page)
def list_reviews(
    target_id: str | None = None,
    platform: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
    session: Session = Depends(get_db),
) -> Page:
    rows = repository.list_reviews(
        session, target_id=target_id, platform=platform, limit=limit, cursor=cursor
    )
    has_next = len(rows) > limit
    rows = rows[:limit]
    return Page(
        items=[ReviewRead.model_validate(row) for row in rows],
        next_cursor=rows[-1].id if has_next and rows else None,
    )


@router.get("/topics", response_model=list[TopicSummary])
def topics(
    target_id: str | None = None,
    topic_type: str | None = None,
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_db),
) -> list[TopicSummary]:
    return service.topic_summary(session, target_id, topic_type, start, end)


@router.get("/trends", response_model=list[TrendRead])
def trends(
    target_id: str | None = None,
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_db),
) -> list[TrendRead]:
    return [TrendRead.model_validate(row) for row in service.trends(session, target_id, start, end)]


@router.get("/metrics", response_model=ReviewMetrics)
def metrics(
    target_id: str,
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_db),
) -> ReviewMetrics:
    return service.review_metrics(session, target_id, start, end)

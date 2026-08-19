# ruff: noqa: B008

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from novel_signal.db import get_db

from . import service
from .schemas import KeywordCreate, KeywordPage, KeywordRead

router = APIRouter(prefix="/keywords", tags=["S2 Keywords"])


@router.get("/meta")
def module_meta() -> dict[str, str]:
    return {"module": "S2 Keywords", "owner": "Akanksh", "status": "implemented"}


@router.get("", response_model=KeywordPage)
def list_keywords(
    active: bool | None = Query(True), session: Session = Depends(get_db)
) -> KeywordPage:
    return KeywordPage(
        items=[
            KeywordRead.model_validate(item)
            for item in service.list_keywords(session, active=active)
        ]
    )


@router.post("", response_model=KeywordRead, status_code=status.HTTP_201_CREATED)
def create_keyword(data: KeywordCreate, session: Session = Depends(get_db)) -> KeywordRead:
    try:
        return KeywordRead.model_validate(service.create_keyword(session, data))
    except service.KeywordConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

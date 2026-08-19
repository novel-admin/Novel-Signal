from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Keyword
from .schemas import KeywordCreate


class KeywordConflict(Exception):
    pass


def create_keyword(session: Session, data: KeywordCreate) -> Keyword:
    normalized = data.text.casefold()
    existing = session.scalar(select(Keyword).where(Keyword.normalized_text == normalized))
    if existing:
        raise KeywordConflict("keyword already exists")
    keyword = Keyword(**data.model_dump(), normalized_text=normalized)
    session.add(keyword)
    session.commit()
    session.refresh(keyword)
    return keyword


def list_keywords(session: Session, *, active: bool | None = True) -> list[Keyword]:
    statement = select(Keyword).order_by(Keyword.text)
    if active is not None:
        statement = statement.where(Keyword.active == active)
    return list(session.scalars(statement))

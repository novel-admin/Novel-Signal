from typing import Generic, TypeVar

from pydantic import BaseModel, Field

ItemT = TypeVar("ItemT")


class PageRequest(BaseModel):
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class Page(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    next_cursor: str | None = None
    total: int | None = None

from pydantic import BaseModel, Field


class PageRequest(BaseModel):
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class Page(BaseModel):
    items: list[object]
    next_cursor: str | None = None
    total: int | None = None

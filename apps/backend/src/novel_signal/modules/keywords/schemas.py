from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class KeywordCreate(BaseModel):
    text: str = Field(min_length=1, max_length=255)
    source: str = Field(default="manual", min_length=1, max_length=80)
    intent: str | None = Field(default=None, max_length=80)
    tier: Literal["T1", "T2", "T3"] = "T1"
    notes: str | None = None

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("keyword cannot be blank")
        return value


class KeywordRead(KeywordCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    normalized_text: str
    active: bool
    created_at: datetime


class KeywordPage(BaseModel):
    items: list[KeywordRead]
    next_cursor: str | None = None

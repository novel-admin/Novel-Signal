from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Dimension = Literal[
    "visibility",
    "paid_presence",
    "price",
    "content",
    "social_proof",
    "availability",
    "conversion",
]
Band = Literal["leading", "competitive", "lagging", "critical"]
Level = Literal["sku_keyword", "sku", "brand", "category"]


class ScorecardUpsert(BaseModel):
    level: Level
    entity_id: str
    dimension: Dimension
    keyword_id: str | None = None
    score: float = Field(ge=0, le=100)
    direction: Literal["improving", "flat", "deteriorating"] = "flat"
    velocity: float = 0
    revenue_at_stake: float | None = Field(default=None, ge=0)
    confidence: Literal["measured", "derived", "estimated", "unknown"] = "measured"
    evidence: dict[str, Any] = Field(default_factory=dict)


class ScorecardRead(ScorecardUpsert):
    model_config = ConfigDict(from_attributes=True)
    id: str
    band: Band
    measured_at: datetime


class ScorecardPage(BaseModel):
    items: list[ScorecardRead]
    next_cursor: str | None = None

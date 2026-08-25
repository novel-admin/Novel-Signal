from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Dimension = Literal[
    "visibility",
    "paid_presence",
    "price",
    "content",
    "social_proof",
    "availability",
    "conversion",
]
Band = Literal["leading", "competitive", "lagging", "critical", "unknown"]
Level = Literal["sku_keyword", "sku", "brand", "category"]


class ScorecardUpsert(BaseModel):
    level: Level
    entity_id: str
    dimension: Dimension
    keyword_id: str | None = None
    score: float | None = Field(default=None, ge=0, le=100)
    direction: Literal["improving", "flat", "deteriorating"] = "flat"
    velocity: float = 0
    revenue_at_stake: float | None = Field(default=None, ge=0)
    confidence: Literal["measured", "derived", "estimated", "unknown"] = "measured"
    evidence: dict[str, Any] = Field(default_factory=dict)
    unknown_reason: str | None = None
    formula_version: str = "scorecard-v1"
    freshness_state: Literal["fresh", "stale", "unknown"] = "fresh"

    @model_validator(mode="after")
    def score_or_unknown_is_explicit(self) -> "ScorecardUpsert":
        if self.score is None:
            if not self.unknown_reason:
                raise ValueError("unknown scorecards require unknown_reason")
            self.confidence = "unknown"
            self.freshness_state = (
                "unknown" if self.freshness_state == "fresh" else self.freshness_state
            )
        elif self.unknown_reason:
            raise ValueError("scored scorecards cannot have unknown_reason")
        elif not self.evidence:
            raise ValueError("scored scorecards require evidence")
        return self


class ScorecardRead(ScorecardUpsert):
    model_config = ConfigDict(from_attributes=True)
    id: str
    band: Band
    measured_at: datetime


class ScorecardPage(BaseModel):
    items: list[ScorecardRead]
    next_cursor: str | None = None

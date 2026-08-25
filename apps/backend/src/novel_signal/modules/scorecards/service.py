from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ScorecardCell, ScorecardHistory
from .schemas import ScorecardUpsert


def score_band(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 85:
        return "leading"
    if score >= 65:
        return "competitive"
    if score >= 40:
        return "lagging"
    return "critical"


def upsert_scorecard(session: Session, data: ScorecardUpsert) -> ScorecardCell:
    statement = select(ScorecardCell).where(
        ScorecardCell.level == data.level,
        ScorecardCell.entity_id == data.entity_id,
        ScorecardCell.dimension == data.dimension,
        ScorecardCell.keyword_id == data.keyword_id,
    )
    cell = session.scalar(statement)
    band = score_band(data.score)
    if cell is None:
        cell = ScorecardCell(
            level=data.level,
            entity_id=data.entity_id,
            dimension=data.dimension,
            keyword_id=data.keyword_id,
            score=data.score,
            band=band,
            direction=data.direction,
            velocity=data.velocity,
            revenue_at_stake=data.revenue_at_stake,
            confidence=data.confidence,
            evidence=data.evidence,
            unknown_reason=data.unknown_reason,
            formula_version=data.formula_version,
            freshness_state=data.freshness_state,
        )
        session.add(cell)
        session.flush()
    else:
        session.add(
            ScorecardHistory(
                cell_id=cell.id,
                score=cell.score,
                band=cell.band,
                direction=cell.direction,
                velocity=cell.velocity,
            )
        )
        cell.score = data.score
        cell.band = band
        cell.direction = data.direction
        cell.velocity = data.velocity
        cell.revenue_at_stake = data.revenue_at_stake
        cell.confidence = data.confidence
        cell.evidence = data.evidence
        cell.unknown_reason = data.unknown_reason
        cell.formula_version = data.formula_version
        cell.freshness_state = data.freshness_state
    session.commit()
    session.refresh(cell)
    return cell


def list_scorecards(
    session: Session, *, limit: int = 50, cursor: str | None = None, band: str | None = None
) -> list[ScorecardCell]:
    statement = select(ScorecardCell).order_by(ScorecardCell.id).limit(limit + 1)
    if cursor:
        statement = statement.where(ScorecardCell.id > cursor)
    if band:
        statement = statement.where(ScorecardCell.band == band)
    return list(session.scalars(statement))

import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from novel_signal.modules.actions.models import Action, Gap
from novel_signal.modules.actions.schemas import ActionCreate, GapCreate
from novel_signal.modules.actions.service import create_action, create_gap
from novel_signal.modules.alerts.models import AlertEvent
from novel_signal.modules.alerts.schemas import AlertEventCreate, AlertRuleCreate
from novel_signal.modules.alerts.service import create_rule, open_alert

from .models import ScorecardCell, ScorecardHistory
from .schemas import ScorecardUpsert

PLAYBOOK: dict[str, tuple[str, str]] = {
    "visibility": ("Improve search visibility", "visibility-recovery-v1"),
    "paid_presence": ("Review sponsored keyword coverage", "paid-presence-v1"),
    "price": ("Review price competitiveness", "price-response-v1"),
    "content": ("Improve listing content", "listing-content-v1"),
    "social_proof": ("Address review weakness", "social-proof-v1"),
    "availability": ("Restore product availability", "availability-v1"),
    "conversion": ("Review conversion performance", "conversion-v1"),
}


@dataclass(frozen=True)
class ScorecardEvaluation:
    scorecard: ScorecardCell
    gap: Gap | None = None
    action: Action | None = None
    alert: AlertEvent | None = None
    non_actionable_reason: str | None = None


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


def evaluate_scorecard(session: Session, data: ScorecardUpsert) -> ScorecardEvaluation:
    cell = upsert_scorecard(session, data)
    if cell.band not in {"lagging", "critical"}:
        reason = "scorecard is unknown" if cell.band == "unknown" else "scorecard is not lagging"
        return ScorecardEvaluation(cell, non_actionable_reason=reason)

    fingerprint_source = (
        f"{cell.level}:{cell.entity_id}:{cell.dimension}:{cell.keyword_id or '-'}:"
        f"{cell.formula_version}"
    )
    fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()
    gap = create_gap(
        session,
        GapCreate(
            fingerprint=fingerprint,
            dimension=cell.dimension,
            entity_id=cell.entity_id,
            keyword_id=cell.keyword_id,
            benchmark_value={"minimum_competitive_score": 65},
            current_value={"score": cell.score, "band": cell.band},
            gap_size=65 - cell.score if cell.score is not None else None,
            revenue_at_stake=cell.revenue_at_stake,
            root_cause=f"{cell.dimension}_below_threshold",
            confidence=cell.confidence,
            evidence=cell.evidence,
        ),
    )
    title, playbook = PLAYBOOK[cell.dimension]
    action = create_action(
        session,
        ActionCreate(
            gap_id=gap.id,
            title=title,
            reason=f"{cell.dimension} score is {cell.band}",
            playbook_entry=playbook,
        ),
    )
    alert = None
    if cell.band == "critical":
        rule = create_rule(
            session,
            AlertRuleCreate(
                rule_key="critical-scorecard",
                alert_type="critical_scorecard",
                version="v1",
                severity="critical",
                threshold={"score_below": 40},
            ),
        )
        alert = open_alert(
            session,
            AlertEventCreate(
                rule_id=rule.id,
                alert_type=rule.alert_type,
                severity="critical",
                target_type=cell.level,
                target_id=cell.entity_id,
                keyword_id=cell.keyword_id,
                gap_id=gap.id,
                action_id=action.id,
                title=f"Critical {cell.dimension} score",
                evidence=cell.evidence,
                fingerprint=f"critical-scorecard:{fingerprint}",
            ),
        )
    return ScorecardEvaluation(cell, gap, action, alert)

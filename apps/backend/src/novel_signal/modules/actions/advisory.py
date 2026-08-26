"""Safe action-draft generation with a deterministic fallback.

The draft only reflects supplied evidence.  It does not activate, assign, or
complete an action, and it remains useful before an external model is enabled.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Action, ActionDraft, Gap
from .schemas import ActionDraftCreate


class ActionDraftError(Exception):
    pass


def create_draft(session: Session, data: ActionDraftCreate) -> ActionDraft:
    gap = session.get(Gap, data.gap_id) if data.gap_id else None
    action = session.get(Action, data.action_id) if data.action_id else None
    if data.gap_id and gap is None:
        raise ActionDraftError("gap not found")
    if data.action_id and action is None:
        raise ActionDraftError("action not found")
    evidence = data.evidence or (gap.evidence if gap is not None else {})
    if not evidence:
        raise ActionDraftError("evidence is required for an advisory draft")

    fingerprint_payload = {
        "gap_id": data.gap_id,
        "action_id": data.action_id,
        "signal_type": data.signal_type,
        "evidence": evidence,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    existing = session.scalar(
        select(ActionDraft).where(ActionDraft.input_fingerprint == fingerprint)
    )
    if existing is not None:
        return existing

    title = action.title if action is not None else _title_for_gap(gap, data.signal_type)
    explanation = _explanation_for_gap(gap, data.signal_type)
    draft = ActionDraft(
        gap_id=data.gap_id,
        action_id=data.action_id,
        input_fingerprint=fingerprint,
        provider="deterministic",
        prompt_version="evidence-v1",
        explanation=explanation,
        title=title,
        recommended_steps=_steps_for_gap(gap, data.signal_type),
        evidence=evidence,
        uncertainty_note=(
            "This is a draft based only on the linked evidence. Confirm freshness and "
            "commercial context before activating an action."
        ),
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


def decide_draft(session: Session, draft_id: str, *, accepted: bool) -> ActionDraft:
    draft = session.get(ActionDraft, draft_id)
    if draft is None:
        raise ActionDraftError("action draft not found")
    if draft.status != "draft":
        raise ActionDraftError("action draft has already been decided")
    draft.status = "accepted" if accepted else "rejected"
    now = datetime.now(UTC)
    if accepted:
        draft.accepted_at = now
    else:
        draft.rejected_at = now
    session.commit()
    session.refresh(draft)
    return draft


def list_drafts(session: Session, *, limit: int = 50) -> list[ActionDraft]:
    return list(
        session.scalars(
            select(ActionDraft)
            .order_by(ActionDraft.created_at.desc(), ActionDraft.id.desc())
            .limit(limit)
        )
    )


def _title_for_gap(gap: Gap | None, signal_type: str) -> str:
    if gap is None:
        return f"Review {signal_type.replace('_', ' ')}"
    return f"Review {gap.dimension.replace('_', ' ')} gap"


def _explanation_for_gap(gap: Gap | None, signal_type: str) -> str:
    if gap is None:
        return f"A {signal_type.replace('_', ' ')} signal needs review against its linked evidence."
    return (
        f"The linked evidence indicates a {gap.dimension.replace('_', ' ')} gap "
        f"with status {gap.status}. This draft does not infer causes beyond that evidence."
    )


def _steps_for_gap(gap: Gap | None, signal_type: str) -> list[str]:
    dimension = gap.dimension if gap is not None else signal_type
    return [
        "Open and verify the linked evidence.",
        f"Review the current {dimension.replace('_', ' ')} context with the responsible team.",
        "Set an owner and due date only after the evidence is confirmed.",
    ]

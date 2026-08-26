from novel_signal.db import Base
from novel_signal.modules.actions.advisory import ActionDraftError, create_draft, decide_draft
from novel_signal.modules.actions.models import Action, ActionDraft, ChangeEvent, Gap
from novel_signal.modules.actions.schemas import ActionDraftCreate, GapCreate
from novel_signal.modules.actions.service import create_gap
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            ChangeEvent.__table__,
            Gap.__table__,
            Action.__table__,
            ActionDraft.__table__,
        ],
    )
    return Session(engine)


def test_action_draft_is_evidence_constrained_idempotent_and_requires_a_decision() -> None:
    db = session()
    gap = create_gap(
        db,
        GapCreate(
            fingerprint="visibility:one",
            dimension="visibility",
            entity_id="product-1",
            evidence={"raw_evidence_id": "evidence-1"},
        ),
    )
    data = ActionDraftCreate(gap_id=gap.id, signal_type="rank_drop")
    first = create_draft(db, data)
    second = create_draft(db, data)

    assert first.id == second.id
    assert first.provider == "deterministic"
    assert first.evidence == {"raw_evidence_id": "evidence-1"}
    assert first.status == "draft"

    accepted = decide_draft(db, first.id, accepted=True)
    assert accepted.status == "accepted"
    try:
        decide_draft(db, first.id, accepted=False)
    except ActionDraftError as error:
        assert "already been decided" in str(error)
    else:
        raise AssertionError("an accepted draft cannot be decided again")


def test_action_draft_refuses_missing_evidence() -> None:
    db = session()
    gap = create_gap(
        db,
        GapCreate(fingerprint="price:one", dimension="price", entity_id="product-1"),
    )
    try:
        create_draft(db, ActionDraftCreate(gap_id=gap.id, signal_type="price_drop"))
    except ActionDraftError as error:
        assert "evidence is required" in str(error)
    else:
        raise AssertionError("drafts must not be created without evidence")

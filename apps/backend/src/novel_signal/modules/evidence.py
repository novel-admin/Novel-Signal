from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class EvidenceQuality:
    usable: bool
    reason: str | None = None


def evidence_quality(
    *,
    publication_status: str,
    raw_evidence_id: str | None,
    parser_version: str | None,
    quarantine_reason: str | None,
    observed_at: datetime,
    freshness_window: timedelta,
    identity_mapped: bool = True,
    now: datetime | None = None,
) -> EvidenceQuality:
    if publication_status != "published":
        return EvidenceQuality(False, "observation is not published")
    if not raw_evidence_id:
        return EvidenceQuality(False, "raw evidence is missing")
    if not parser_version:
        return EvidenceQuality(False, "parser version is missing")
    if quarantine_reason:
        return EvidenceQuality(False, "observation is quarantined")
    if not identity_mapped:
        return EvidenceQuality(False, "observation identity is not mapped")
    current = now or datetime.now(UTC)
    comparable = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=UTC)
    if current - comparable.astimezone(UTC) > freshness_window:
        return EvidenceQuality(False, "observation is stale")
    return EvidenceQuality(True)


def require_published_lineage(
    publication_status: str,
    raw_evidence_id: str | None,
    parser_version: str | None,
    quarantine_reason: str | None,
) -> None:
    if publication_status != "published":
        return
    if not raw_evidence_id:
        raise ValueError("published observations require raw evidence")
    if not parser_version:
        raise ValueError("published observations require a parser version")
    if quarantine_reason:
        raise ValueError("published observations cannot have a quarantine reason")

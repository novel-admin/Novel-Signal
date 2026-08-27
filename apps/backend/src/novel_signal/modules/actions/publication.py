from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from novel_signal.modules.actions.models import ChangeEvent


def publish_change_event(
    session: Session,
    *,
    target_type: str,
    target_id: str,
    event_type: str,
    old_observation_type: str,
    old_observation_id: uuid.UUID,
    new_observation_type: str,
    new_observation_id: uuid.UUID,
    field_name: str,
    old_value: object | None,
    new_value: object | None,
    detected_at: datetime,
    severity: str = "info",
) -> ChangeEvent:
    """Add a replay-safe shared event without taking ownership of the transaction."""
    canonical = {
        "target_type": target_type,
        "target_id": target_id,
        "event_type": event_type,
        "old_observation_type": old_observation_type,
        "old_observation_id": str(old_observation_id),
        "new_observation_type": new_observation_type,
        "new_observation_id": str(new_observation_id),
        "field_name": field_name,
        "old_value": _json_value(old_value),
        "new_value": _json_value(new_value),
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    existing = session.scalar(select(ChangeEvent).where(ChangeEvent.fingerprint == fingerprint))
    if existing is not None:
        return existing
    event = ChangeEvent(
        **canonical,
        detected_at=detected_at,
        severity=severity,
        fingerprint=fingerprint,
    )
    session.add(event)
    return event


def target_identity(
    *,
    product_id: uuid.UUID | None,
    competitor_product_id: uuid.UUID | None,
    marketplace: object,
    marketplace_product_id: str,
) -> tuple[str, str]:
    if product_id is not None:
        return "product", str(product_id)
    if competitor_product_id is not None:
        return "competitor_product", str(competitor_product_id)
    # ``ChangeEvent.target_id`` is a UUID-sized shared identifier.  Preserve
    # unknown marketplace identities deterministically without truncation;
    # the linked normalized observation retains the original marketplace ID.
    return (
        "marketplace_product",
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"{marketplace}:{marketplace_product_id}")),
    )


def _json_value(value: object | None) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value

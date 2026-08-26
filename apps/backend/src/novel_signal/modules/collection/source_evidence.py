from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from novel_signal.db import SessionLocal
from novel_signal.modules.collection.execution import (
    CollectionExecutionError,
    CollectionExecutionResult,
)
from novel_signal.modules.collection.models import CollectionFailureType
from novel_signal.modules.collection.raw_evidence import RawEvidenceWriter
from novel_signal.modules.collection.storage import RawObjectStore
from novel_signal.sources.base import SourceAdapter, SyncRequest

SourceErrorMapper = Callable[[Exception], CollectionExecutionError]


class SourceRawEvidenceBridge:
    """Execute one raw source request and persist every returned page without parsing."""

    def __init__(
        self,
        *,
        adapter: SourceAdapter,
        object_store: RawObjectStore | None = None,
        session_factory: sessionmaker[Session] = SessionLocal,
        error_mapper: SourceErrorMapper | None = None,
    ) -> None:
        self.adapter = adapter
        self.error_mapper = error_mapper
        self.writer = RawEvidenceWriter(
            object_store=object_store,
            session_factory=session_factory,
        )

    async def execute(
        self,
        *,
        job_id: uuid.UUID,
        attempt_id: uuid.UUID,
        request: SyncRequest,
        captured_at: datetime | None = None,
    ) -> CollectionExecutionResult:
        try:
            pages = await self.adapter.fetch(request)
        except Exception as error:
            mapped = (
                self.error_mapper(error)
                if self.error_mapper is not None
                else _default_source_error()
            )
            raise mapped from None

        if not pages:
            raise CollectionExecutionError(
                "Source adapter returned no raw evidence pages",
                failure_type=CollectionFailureType.HTTP_ERROR,
                code="source_returned_no_pages",
                retryable=False,
            )

        captured = (captured_at or datetime.now(UTC)).astimezone(UTC)
        evidence_ids: list[str] = []
        for page_index, page in enumerate(pages):
            metadata: dict[str, object] = {
                "source_type": page.source.value,
                "resource_type": page.resource_type,
                "request_fingerprint": page.request_fingerprint,
                "page_index": page_index,
            }
            if page.next_cursor is not None:
                metadata["next_cursor"] = page.next_cursor

            try:
                evidence = self.writer.persist(
                    job_id=job_id,
                    attempt_id=attempt_id,
                    platform=page.source.value,
                    page_type=page.resource_type,
                    body=page.body,
                    content_type=page.content_type,
                    final_url=None,
                    challenge_detected=False,
                    capture_metadata=metadata,
                    captured_at=captured,
                )
            except CollectionExecutionError as error:
                raise CollectionExecutionError(
                    str(error),
                    failure_type=error.failure_type,
                    code=error.code,
                    retryable=error.retryable,
                    details={
                        **error.details,
                        "failed_page_index": page_index,
                        "persisted_page_count": len(evidence_ids),
                        "persisted_raw_evidence_ids": evidence_ids,
                    },
                ) from error
            evidence_ids.append(str(evidence.id))

        result_metadata: dict[str, object] = {
            "raw_evidence_ids": evidence_ids,
            "raw_page_count": len(evidence_ids),
        }
        if len(evidence_ids) == 1:
            result_metadata["raw_evidence_id"] = evidence_ids[0]
        return CollectionExecutionResult(metadata=result_metadata)


def _default_source_error() -> CollectionExecutionError:
    return CollectionExecutionError(
        "Source adapter execution failed",
        failure_type=CollectionFailureType.UNKNOWN,
        code="source_adapter_failed",
        retryable=False,
    )

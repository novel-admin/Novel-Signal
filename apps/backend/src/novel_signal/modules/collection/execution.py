from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, Protocol

from novel_signal.modules.collection.models import CollectionFailureType, CollectionJobType


@dataclass(frozen=True)
class CollectionWorkItem:
    job_id: uuid.UUID
    job_type: CollectionJobType
    platform: str
    keyword_id: uuid.UUID | None
    product_id: uuid.UUID | None
    competitor_product_id: uuid.UUID | None
    tracking_target_id: uuid.UUID | None
    attempt_id: uuid.UUID | None = None


@dataclass(frozen=True)
class QuarantineDecision:
    raw_evidence_id: uuid.UUID
    parser_version_id: uuid.UUID | None
    failure_type: CollectionFailureType
    reason_code: str
    reason: str
    schema_errors: tuple[dict[str, Any], ...] = ()
    parsed_payload: dict[str, Any] | list[Any] | None = None


@dataclass(frozen=True)
class CollectionExecutionResult:
    metadata: dict[str, Any] = field(default_factory=dict)
    quarantine: QuarantineDecision | None = None


class CollectionExecutor(Protocol):
    async def execute(self, item: CollectionWorkItem) -> CollectionExecutionResult: ...


class CollectionExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        failure_type: CollectionFailureType,
        code: str,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_type = failure_type
        self.code = code
        self.retryable = retryable
        self.details = details or {}


ExecutorFactory = Callable[[], CollectionExecutor]
_EXECUTORS: dict[tuple[str, CollectionJobType], ExecutorFactory] = {}


def register_executor(
    platform: str,
    job_type: CollectionJobType,
    factory: ExecutorFactory,
) -> None:
    _EXECUTORS[(platform, job_type)] = factory


def unregister_executor(platform: str, job_type: CollectionJobType) -> None:
    _EXECUTORS.pop((platform, job_type), None)


def clear_executor_registry() -> None:
    _EXECUTORS.clear()


def get_executor(platform: str, job_type: CollectionJobType) -> CollectionExecutor:
    factory = _EXECUTORS.get((platform, job_type))
    if factory is None:
        raise CollectionExecutionError(
            f"No collection executor is registered for {platform}/{job_type.value}",
            failure_type=CollectionFailureType.UNKNOWN,
            code="executor_not_registered",
            retryable=False,
        )
    return factory()


def execute_async(
    awaitable: Coroutine[object, object, CollectionExecutionResult],
) -> CollectionExecutionResult:
    """Run one async executor from the synchronous scheduled-job boundary."""
    return asyncio.run(awaitable)

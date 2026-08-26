from __future__ import annotations

import asyncio
import uuid

import pytest
from novel_signal.modules.collection.execution import (
    CollectionExecutionError,
    CollectionExecutionResult,
    CollectionWorkItem,
    clear_executor_registry,
    execute_async,
    get_executor,
    register_executor,
    unregister_executor,
)
from novel_signal.modules.collection.models import CollectionFailureType, CollectionJobType


class FakeExecutor:
    async def execute(self, item: CollectionWorkItem) -> CollectionExecutionResult:
        await asyncio.sleep(0)
        return CollectionExecutionResult(metadata={"job_id": str(item.job_id), "ok": True})


@pytest.fixture(autouse=True)
def clean_registry() -> None:
    clear_executor_registry()


def work_item() -> CollectionWorkItem:
    return CollectionWorkItem(
        job_id=uuid.uuid4(),
        attempt_id=uuid.uuid4(),
        job_type=CollectionJobType.SERP,
        platform="amazon_in",
        keyword_id=uuid.uuid4(),
        product_id=None,
        competitor_product_id=None,
        tracking_target_id=None,
    )


def test_executor_registry_and_async_boundary() -> None:
    register_executor("amazon_in", CollectionJobType.SERP, FakeExecutor)
    executor = get_executor("amazon_in", CollectionJobType.SERP)
    result = execute_async(executor.execute(work_item()))
    assert result.metadata["ok"] is True

    unregister_executor("amazon_in", CollectionJobType.SERP)
    with pytest.raises(CollectionExecutionError) as raised:
        get_executor("amazon_in", CollectionJobType.SERP)
    assert raised.value.code == "executor_not_registered"
    assert raised.value.retryable is False
    assert raised.value.failure_type is CollectionFailureType.UNKNOWN

"""Small PostgreSQL-backed scheduler for the single Render web service."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from novel_signal.config import Settings
from novel_signal.modules.collection.runner import run_due_collection_jobs

logger = logging.getLogger(__name__)


async def run_scheduler(settings: Settings, stop_event: asyncio.Event) -> None:
    """Process due jobs in bounded batches until application shutdown."""
    interval = max(5, settings.internal_scheduler_interval_seconds)
    while not stop_event.is_set():
        try:
            result = await asyncio.to_thread(
                run_due_collection_jobs,
                max_jobs=settings.collection_batch_size,
                worker_id="render-web-internal-scheduler",
            )
            if result.failed:
                logger.warning("collection scheduler completed with failures: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("collection scheduler tick failed")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            continue


def start_scheduler(settings: Settings) -> tuple[asyncio.Task[Any], asyncio.Event]:
    stop_event = asyncio.Event()
    task = asyncio.create_task(run_scheduler(settings, stop_event))
    return task, stop_event


async def stop_scheduler(task: asyncio.Task[Any], stop_event: asyncio.Event) -> None:
    stop_event.set()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

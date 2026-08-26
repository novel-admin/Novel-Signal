"""Backward-compatible import surface for collection execution.

The production scheduler is now :mod:`novel_signal.modules.collection.runner`.
This module intentionally contains no Celery task or broker configuration.
"""

from __future__ import annotations

from novel_signal.modules.collection.runner import (
    register_builtin_executors,
    run_collection_job,
    run_due_collection_jobs,
)

# Keep this compatibility import surface safe after callers reset the registry.
register_builtin_executors()

__all__ = ["run_collection_job", "run_due_collection_jobs"]

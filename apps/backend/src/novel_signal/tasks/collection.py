"""Backward-compatible import surface for collection execution.

The production scheduler is now :mod:`novel_signal.modules.collection.runner`.
This module intentionally contains no Celery task or broker configuration.
"""

from __future__ import annotations

from novel_signal.modules.collection.runner import run_collection_job, run_due_collection_jobs

__all__ = ["run_collection_job", "run_due_collection_jobs"]

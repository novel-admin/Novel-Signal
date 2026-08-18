from celery import Celery

from novel_signal.config import get_settings

settings = get_settings()
celery_app = Celery(
    "novel_signal",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["novel_signal.tasks.collection"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_routes={"novel_signal.collection.*": {"queue": "collection"}},
    worker_concurrency=settings.amazon_in_concurrency,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    result_expires=3600,
    beat_schedule={
        "plan-due-collection-jobs": {
            "task": "novel_signal.collection.plan_due",
            "schedule": 60.0,
        }
    },
)

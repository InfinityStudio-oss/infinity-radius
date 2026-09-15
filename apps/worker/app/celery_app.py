"""Celery application entrypoint.

Run with `celery -A app.celery_app worker` / `celery -A app.celery_app beat`.
"""

from celery import Celery

from app.config import get_worker_settings

settings = get_worker_settings()

celery_app = Celery(
    "infinity_radius",
    broker=str(settings.redis_url),
    backend=str(settings.redis_url),
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.default_timezone,
    enable_utc=True,
    task_track_started=True,
)

# Celery Beat schedule. No periodic jobs exist yet — entries are added here
# as billing/RADIUS-sync/reconciliation jobs are implemented.
celery_app.conf.beat_schedule = {}

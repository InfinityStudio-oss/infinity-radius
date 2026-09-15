"""Celery application shared by the API (task producer) and the worker/beat
processes (apps/worker), which import this module to obtain the same
broker/backend configuration and task registry.
"""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "infinity_radius",
    broker=str(settings.redis_url),
    backend=str(settings.redis_url),
    include=[],  # task modules are registered as business logic is added
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.default_timezone,
    enable_utc=True,
    task_track_started=True,
)

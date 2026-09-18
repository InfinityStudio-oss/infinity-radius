"""Celery application shared by the API (task producer) and the worker/beat
processes (apps/worker), which import this module to obtain the same
broker/backend configuration and task registry.
"""

from celery import Celery

from app.core.config import get_settings
from app.integrations.selcom_business.config import validate_selcom_startup_config

settings = get_settings()

# Same guard as app/main.py — a no-op when Selcom isn't configured at all
# (Beat's case, by design: it never calls Selcom, only schedules), but
# catches a real sandbox/production mismatch immediately on Worker boot,
# which does call Selcom (reconciliation queries).
validate_selcom_startup_config()

celery_app = Celery(
    "infinity_radius",
    broker=str(settings.redis_url),
    backend=str(settings.redis_url),
    include=["app.tasks.reconciliation"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.default_timezone,
    enable_utc=True,
    task_track_started=True,
)

# Run with `celery -A app.core.celery_app worker` / `... beat` from apps/api
# — this app instance (not apps/worker's) owns the task, since it needs the
# full API app's DB/service layer. Every 2 minutes: comfortably inside
# NetworkAgentSettings-style bounds without hammering Selcom, while still
# resolving a PROCESSING/AMBIGUOUS withdrawal well within a support SLA.
celery_app.conf.beat_schedule = {
    "reconcile-pending-withdrawals": {
        "task": "infinity_radius.reconcile_pending_withdrawals",
        "schedule": 120.0,
    },
}

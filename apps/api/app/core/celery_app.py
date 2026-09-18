"""Celery application shared by the API (task producer) and the worker/beat
processes, which import this module to obtain the same broker/backend
configuration and task registry.

Neither Worker nor Beat calls Selcom directly (Option B network
centralization — see app/integrations/internal_web/client.py and
app/api/v1/internal_disbursements.py): Beat only schedules, and Worker
only decides which withdrawals need reconciliation and asks web's
internal HMAC-authenticated endpoint to actually query Selcom. So this
module deliberately never imports or calls
app.integrations.selcom_business.config.validate_selcom_startup_config —
Worker/Beat boot with zero Selcom credentials/awareness; only app/main.py
(the web service) still validates them at startup.
"""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

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

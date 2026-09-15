"""Task registry. Empty until the first background job (billing, RADIUS sync,
voucher expiry, payout reconciliation, ...) is implemented.
"""

from app.celery_app import celery_app


@celery_app.task(name="infinity_radius.ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    """Smoke-test task confirming the worker can execute jobs from the broker."""
    return "pong"

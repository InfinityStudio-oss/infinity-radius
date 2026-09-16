"""Celery task modules — registered on app.core.celery_app via its
`include` list. Each module here needs the full API app's DB/service
layer, which is why these tasks live in apps/api rather than apps/worker
(a separate, dependency-free package — see apps/worker/app/tasks.py).
Run with `celery -A app.core.celery_app worker` / `... beat` from apps/api.
"""

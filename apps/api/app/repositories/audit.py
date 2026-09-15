from app.models.audit import AuditLog
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    model = AuditLog
    search_fields = ("action", "target_type")
    filterable_fields = ("action", "target_type", "actor_id")
    sortable_fields = ("created_at",)

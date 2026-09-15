from app.models.network import UserSession
from app.repositories.base import BaseRepository


class UserSessionRepository(BaseRepository[UserSession]):
    model = UserSession
    search_fields = ("session_identifier", "ip_address")
    filterable_fields = ("status", "customer_id", "router_id", "subscription_id")
    sortable_fields = ("created_at", "started_at", "ended_at", "status")

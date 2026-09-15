from app.models.tenancy import Profile, Tenant
from app.repositories.base import BaseRepository


class TenantRepository(BaseRepository[Tenant]):
    model = Tenant
    search_fields = ("name", "slug")
    filterable_fields = ("status", "country")
    sortable_fields = ("created_at", "name", "status")
    default_sort = "name"


class ProfileRepository(BaseRepository[Profile]):
    model = Profile
    search_fields = ("full_name", "email", "phone")
    filterable_fields = ("status",)
    sortable_fields = ("created_at", "full_name", "status")
    default_sort = "full_name"

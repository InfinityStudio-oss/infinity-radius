"""Resend configuration interface — deliberately minimal, same shape as
app/integrations/selcom/config.py."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ResendConfig:
    api_key: str | None
    from_email: str | None
    from_name: str
    super_admin_review_email: str | None
    app_url: str

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.from_email)

    @property
    def from_header(self) -> str:
        return f"{self.from_name} <{self.from_email}>"

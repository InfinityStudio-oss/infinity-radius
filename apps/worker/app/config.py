"""Worker settings.

Deployed as an independent Railway service from apps/api, so this does not
import api's `app` package (avoids a top-level-name collision if both were
ever installed into one environment) — it revalidates the small slice of
configuration a Celery process needs. Business task modules added in a
later phase should live in a proper shared internal package rather than
duplicating logic further.
"""

from functools import lru_cache
from typing import Literal

from pydantic import RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "staging", "production"] = "development"
    redis_url: RedisDsn
    default_timezone: str = "Africa/Dar_es_Salaam"


@lru_cache
def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()

"""Configuración segura de la API interna."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import unquote, urlsplit

from dotenv import load_dotenv


class SettingsError(ValueError):
    """Configuración ausente o apuntando a una base protegida."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    expected_database: str = "aquanqa_migracion"
    api_prefix: str = "/v1"
    environment: str = "local"
    public_api_url: str | None = None
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        expected = os.getenv("AQUANQA_API_DATABASE", "aquanqa_migracion")
        database_url = os.getenv("AQUANQA_API_DATABASE_URL") or os.getenv("DATABASE_URL")
        if not database_url:
            host = os.getenv("PGHOST", "localhost")
            port = os.getenv("PGPORT", "5432")
            user = os.getenv("APP_DB_USER") or os.getenv("PGUSER", "postgres")
            password = os.getenv("APP_DB_PASSWORD") or os.getenv("PGPASSWORD", "")
            database_url = f"postgresql://{user}:{password}@{host}:{port}/{expected}"

        database_name = _database_name(database_url)
        if database_name != expected:
            raise SettingsError(
                f"La API de campo solo puede apuntar a {expected}; "
                f"la configuración apunta a {database_name or '<desconocida>'}"
            )
        return cls(
            database_url=database_url,
            expected_database=expected,
            api_prefix=os.getenv("AQUANQA_API_PREFIX", "/v1").rstrip("/"),
            environment=os.getenv("AQUANQA_API_ENVIRONMENT", "local"),
            public_api_url=os.getenv("AQUANQA_API_PUBLIC_URL") or None,
            log_level=os.getenv("AQUANQA_API_LOG_LEVEL", "INFO").upper(),
        )


def _database_name(database_url: str) -> str:
    parsed = urlsplit(database_url)
    return unquote(parsed.path.split("?", 1)[0].strip("/"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


__all__ = ["Settings", "SettingsError", "get_settings"]

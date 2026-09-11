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
    database_pool_min_size: int = 3
    database_pool_max_size: int = 10
    database_pool_timeout_seconds: float = 5.0
    jwt_secret: str = "local-development-secret-change-me"
    jwt_access_minutes: int = 15
    jwt_refresh_days: int = 7

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        expected = os.getenv("AQUANQA_API_DATABASE", "aquanqa_migracion")
        environment = os.getenv("AQUANQA_API_ENVIRONMENT", "local").lower()
        jwt_secret = os.getenv("AQUANQA_JWT_SECRET")
        if environment not in {"local", "test"} and not jwt_secret:
            raise SettingsError(
                "AQUANQA_JWT_SECRET es obligatorio fuera de los entornos local y test"
            )
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
        pool_max_size = int(os.getenv("AQUANQA_API_DATABASE_POOL_MAX_SIZE", "10"))
        pool_min_size = int(
            os.getenv("AQUANQA_API_DATABASE_POOL_MIN_SIZE", str(min(3, pool_max_size)))
        )
        return cls(
            database_url=database_url,
            expected_database=expected,
            api_prefix=os.getenv("AQUANQA_API_PREFIX", "/v1").rstrip("/"),
            environment=environment,
            public_api_url=os.getenv("AQUANQA_API_PUBLIC_URL") or None,
            log_level=os.getenv("AQUANQA_API_LOG_LEVEL", "INFO").upper(),
            database_pool_min_size=pool_min_size,
            database_pool_max_size=pool_max_size,
            database_pool_timeout_seconds=float(
                os.getenv("AQUANQA_API_DATABASE_POOL_TIMEOUT_SECONDS", "5")
            ),
            jwt_secret=jwt_secret or "local-development-secret-change-me",
            jwt_access_minutes=int(os.getenv("AQUANQA_JWT_ACCESS_MINUTES", "15")),
            jwt_refresh_days=int(os.getenv("AQUANQA_JWT_REFRESH_DAYS", "7")),
        )


def _database_name(database_url: str) -> str:
    parsed = urlsplit(database_url)
    return unquote(parsed.path.split("?", 1)[0].strip("/"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


__all__ = ["Settings", "SettingsError", "get_settings"]

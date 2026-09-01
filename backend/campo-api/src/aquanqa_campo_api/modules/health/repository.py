"""Puerto de comprobación de disponibilidad de PostgreSQL."""

from typing import Protocol


class HealthRepositoryError(RuntimeError):
    """La dependencia comprobada no está disponible."""


class HealthRepository(Protocol):
    def ping(self) -> None: ...


__all__ = ["HealthRepository", "HealthRepositoryError"]

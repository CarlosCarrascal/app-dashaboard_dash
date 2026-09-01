"""Caso de uso de disponibilidad."""

from .repository import HealthRepository


class HealthService:
    def __init__(self, repository: HealthRepository):
        self._repository = repository

    def ready(self) -> dict[str, str]:
        self._repository.ping()
        return {"status": "ok", "database": "ready"}


__all__ = ["HealthService"]

"""Casos de uso de identidad temporal."""

from .repository import IdentityRepository
from .schemas import EvaluadorCatalogo, EvaluadorSesion


class IdentityService:
    def __init__(self, repository: IdentityRepository):
        self._repository = repository

    def resolve_by_dni(self, dni: str) -> EvaluadorSesion | None:
        row = self._repository.find_evaluador_by_dni(dni)
        return None if row is None else EvaluadorSesion.model_validate(row)

    def list_evaluadores(self) -> list[EvaluadorCatalogo]:
        return [
            EvaluadorCatalogo.model_validate(row) for row in self._repository.list_evaluadores()
        ]


__all__ = ["IdentityService"]

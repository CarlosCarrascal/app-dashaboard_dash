"""Casos de uso de catálogos."""

from .repository import CatalogRepository
from .schemas import FundoCatalogo, LoteCatalogo, ModuloCatalogo


class CatalogService:
    def __init__(self, repository: CatalogRepository):
        self._repository = repository

    def list_fundos(self) -> list[FundoCatalogo]:
        return [FundoCatalogo.model_validate(row) for row in self._repository.list_fundos()]

    def list_modulos(self, fundo_id: int | None = None) -> list[ModuloCatalogo]:
        return [
            ModuloCatalogo.model_validate(row)
            for row in self._repository.list_modulos(fundo_id=fundo_id)
        ]

    def list_lotes(self, modulo_id: int | None = None) -> list[LoteCatalogo]:
        return [
            LoteCatalogo.model_validate(row)
            for row in self._repository.list_lotes(modulo_id=modulo_id)
        ]


__all__ = ["CatalogService"]

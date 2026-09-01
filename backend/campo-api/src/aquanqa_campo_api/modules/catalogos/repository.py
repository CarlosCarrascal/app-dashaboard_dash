"""Puerto de lectura de catálogos de ubicación."""

from typing import Any, Protocol


class CatalogRepositoryError(RuntimeError):
    """Error técnico al consultar los catálogos."""


class CatalogRepository(Protocol):
    def list_fundos(self) -> list[dict[str, Any]]: ...

    def list_modulos(self, fundo_id: int | None = None) -> list[dict[str, Any]]: ...

    def list_lotes(self, modulo_id: int | None = None) -> list[dict[str, Any]]: ...


__all__ = ["CatalogRepository", "CatalogRepositoryError"]

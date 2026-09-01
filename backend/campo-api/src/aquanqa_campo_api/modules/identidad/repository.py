"""Puerto de lectura de evaluadores."""

from typing import Any, Protocol


class IdentityRepositoryError(RuntimeError):
    """Error técnico al consultar evaluadores."""


class IdentityRepository(Protocol):
    def list_evaluadores(self) -> list[dict[str, Any]]: ...

    def find_evaluador_by_dni(self, dni: str) -> dict[str, Any] | None: ...


__all__ = ["IdentityRepository", "IdentityRepositoryError"]

"""Puerto de persistencia de identidades administrativas."""

from __future__ import annotations

from typing import Any, Protocol


class AuthRepositoryError(RuntimeError):
    """Error técnico al consultar o actualizar una identidad."""


class AuthRepository(Protocol):
    def find_by_email(self, email: str) -> dict[str, Any] | None: ...

    def find_by_id(self, usuario_id: int) -> dict[str, Any] | None: ...

    def touch_login(self, usuario_id: int) -> None: ...


__all__ = ["AuthRepository", "AuthRepositoryError"]

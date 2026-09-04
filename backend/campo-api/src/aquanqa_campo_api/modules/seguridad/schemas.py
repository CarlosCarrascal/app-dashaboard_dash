"""Contratos HTTP de autenticación y autorización."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccessScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    empresa_id: int | None = Field(default=None, gt=0)
    fundo_id: int | None = Field(default=None, gt=0)
    modulo_id: int | None = Field(default=None, gt=0)
    lote_id: int | None = Field(default=None, gt=0)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().casefold()
        if "@" not in value:
            raise ValueError("email debe tener formato válido")
        return value


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=20)


class AuthUser(BaseModel):
    usuario_id: int
    email: str
    nombre: str
    rol: str
    permisos: list[str] = Field(default_factory=list)
    alcances: list[AccessScope] = Field(default_factory=list)

    def puede(self, permiso: str) -> bool:
        return "*" in self.permisos or permiso in self.permisos


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthUser


__all__ = ["AccessScope", "AuthUser", "LoginRequest", "RefreshRequest", "TokenPair"]

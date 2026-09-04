"""Casos de uso de login, refresh y autorización por permiso."""

from __future__ import annotations

import time
from secrets import token_urlsafe
from typing import Any

from ...core.security import TokenError, decode_token, encode_token, verify_password
from ...core.settings import Settings
from .repository import AuthRepository
from .schemas import AccessScope, AuthUser, LoginRequest, TokenPair


class InvalidCredentialsError(ValueError):
    """Credenciales no válidas o usuario inactivo."""


class AuthService:
    def __init__(self, repository: AuthRepository, settings: Settings):
        self._repository = repository
        self._settings = settings

    def login(self, payload: LoginRequest) -> TokenPair:
        row = self._repository.find_by_email(payload.email)
        if row is None or not row.get("activo") or not verify_password(
            payload.password, row.get("hash_password")
        ):
            raise InvalidCredentialsError("Email o contraseña incorrectos")
        self._repository.touch_login(int(row["usuario_id"]))
        user = _user(row)
        return self._tokens(user)

    def refresh(self, refresh_token: str) -> TokenPair:
        claims = decode_token(
            refresh_token, self._settings.jwt_secret, expected_type="refresh"
        )
        row = self._repository.find_by_id(int(claims["sub"]))
        if row is None or not row.get("activo"):
            raise InvalidCredentialsError("La sesión ya no está activa")
        return self._tokens(_user(row))

    def current_user(self, access_token: str) -> AuthUser:
        claims = decode_token(access_token, self._settings.jwt_secret, expected_type="access")
        row = self._repository.find_by_id(int(claims["sub"]))
        if row is None or not row.get("activo"):
            raise InvalidCredentialsError("La sesión ya no está activa")
        return _user(row)

    def _tokens(self, user: AuthUser) -> TokenPair:
        now = int(time.time())
        access_exp = now + self._settings.jwt_access_minutes * 60
        refresh_exp = now + self._settings.jwt_refresh_days * 86400
        common = {
            "sub": str(user.usuario_id),
            "jti": token_urlsafe(12),
            "iat": now,
        }
        access = encode_token(
            {
                **common,
                "typ": "access",
                "role": user.rol,
                "permissions": user.permisos,
                "exp": access_exp,
            },
            self._settings.jwt_secret,
        )
        refresh = encode_token(
            {**common, "typ": "refresh", "exp": refresh_exp}, self._settings.jwt_secret
        )
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=self._settings.jwt_access_minutes * 60,
            user=user,
        )


def _user(row: dict[str, Any]) -> AuthUser:
    permissions = row.get("permisos") or []
    if isinstance(permissions, str):
        permissions = [permissions]
    scopes = row.get("alcances") or []
    if isinstance(scopes, dict):
        scopes = [scopes]
    return AuthUser(
        usuario_id=int(row["usuario_id"]),
        email=row["email"],
        nombre=row["nombre"],
        rol=row["rol"],
        permisos=sorted(str(permission) for permission in permissions),
        alcances=[AccessScope.model_validate(scope) for scope in scopes],
    )


__all__ = ["AuthService", "InvalidCredentialsError", "TokenError"]

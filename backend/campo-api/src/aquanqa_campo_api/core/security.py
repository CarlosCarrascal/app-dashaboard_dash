"""Tokens firmados y hashes de contraseña sin depender de un ORM."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

PASSWORD_ITERATIONS = 310_000


class TokenError(ValueError):
    """Token ausente, manipulado, vencido o de tipo incorrecto."""


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("La contraseña no puede estar vacía")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return "$".join(
        (
            "pbkdf2_sha256",
            str(PASSWORD_ITERATIONS),
            _b64encode(salt),
            _b64encode(digest),
        )
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not password or not encoded:
        return False
    try:
        algorithm, iterations, salt_text, expected_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = _b64decode(salt_text)
        expected = _b64decode(expected_text)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
    except (TypeError, ValueError, OverflowError):
        return False
    return hmac.compare_digest(actual, expected)


def encode_token(claims: dict[str, Any], secret: str) -> str:
    if not secret:
        raise ValueError("Falta AQUANQA_JWT_SECRET")
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _json_segment(header)
    encoded_claims = _json_segment(claims)
    unsigned = f"{encoded_header}.{encoded_claims}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), unsigned, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_claims}.{_b64encode(signature)}"


def decode_token(token: str, secret: str, expected_type: str) -> dict[str, Any]:
    if not token or not secret:
        raise TokenError("Credenciales inválidas")
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("Token mal formado")
    try:
        unsigned = f"{parts[0]}.{parts[1]}".encode("ascii")
        expected = hmac.new(secret.encode("utf-8"), unsigned, hashlib.sha256).digest()
        received = _b64decode(parts[2])
        header = json.loads(_b64decode(parts[0]))
        claims = json.loads(_b64decode(parts[1]))
    except (UnicodeEncodeError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        raise TokenError("Token mal formado") from None
    if not hmac.compare_digest(received, expected) or header.get("alg") != "HS256":
        raise TokenError("Firma inválida")
    if claims.get("typ") != expected_type:
        raise TokenError("Tipo de token inválido")
    try:
        expires_at = int(claims["exp"])
        subject = int(claims["sub"])
    except (KeyError, TypeError, ValueError):
        raise TokenError("Claims inválidos") from None
    if expires_at <= int(time.time()):
        raise TokenError("Token vencido")
    if subject <= 0:
        raise TokenError("Sujeto inválido")
    return claims


def _json_segment(value: dict[str, Any]) -> str:
    return _b64encode(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


__all__ = [
    "PASSWORD_ITERATIONS",
    "TokenError",
    "decode_token",
    "encode_token",
    "hash_password",
    "verify_password",
]

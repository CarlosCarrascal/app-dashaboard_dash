"""Funciones de huella digital sin dependencias del dominio de proyección."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path


def sha256_archivo(ruta: str | Path) -> str:
    """Calcula la huella SHA-256 leyendo el archivo por bloques."""

    digest = sha256()
    with Path(ruta).open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


__all__ = ["sha256_archivo"]

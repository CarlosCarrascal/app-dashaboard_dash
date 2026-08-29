"""Huella de manifiestos y contenedores de salida del caso operativo."""

from __future__ import annotations

import hashlib
import json

import pandas as pd

from ..contratos import DatosProyeccion, FuenteInfo


def _firma_manifest(manifest: list[dict[str, object]]) -> str:
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def datos_proyeccion_operativo(fuente: FuenteInfo) -> DatosProyeccion:
    """Crea el contenedor mínimo requerido por el repositorio y exportador."""
    return DatosProyeccion(
        fuente=fuente,
        forecast=pd.DataFrame(),
        cosecha=pd.DataFrame(),
    )


__all__ = ["_firma_manifest", "datos_proyeccion_operativo"]

"""Fachada histórica para la validación de libros operativos ProySemanal."""

from __future__ import annotations

from .compartido.hashes import sha256_archivo
from .operativo.contratos import (
    CAMPOS_NUMERICOS,
    CLAVES_CORRIDA,
    MODELO_OPERATIVO_ACTUAL,
    ResultadoValidacionOperativa,
)
from .operativo.lectura import leer_libro_operativo
from .operativo.normalizacion import (  # noqa: F401 - aliases históricos
    _campana_unica,
    _normalizar_claves,
)
from .operativo.validacion import validar_libro_operativo, validar_libros_semana

__all__ = [
    "CAMPOS_NUMERICOS",
    "CLAVES_CORRIDA",
    "MODELO_OPERATIVO_ACTUAL",
    "ResultadoValidacionOperativa",
    "leer_libro_operativo",
    "sha256_archivo",
    "validar_libro_operativo",
    "validar_libros_semana",
]

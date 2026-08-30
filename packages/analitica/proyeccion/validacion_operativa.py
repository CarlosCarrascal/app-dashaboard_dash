"""Fachada histórica para la validación de libros operativos ProySemanal."""

from __future__ import annotations

from .compartido import sha256_archivo
from .operativo.excel import (  # noqa: F401 - aliases históricos
    CAMPOS_NUMERICOS,
    CLAVES_CORRIDA,
    MODELO_OPERATIVO_ACTUAL,
    ResultadoValidacionOperativa,
    _campana_unica,
    _normalizar_claves,
    leer_libro_operativo,
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

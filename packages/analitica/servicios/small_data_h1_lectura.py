"""Lectura y normalización de fuentes para small data H1."""

from __future__ import annotations

import pandas as pd

from . import small_data_h1_configuracion as _configuracion
from .small_data import cargar_universo_lote as _cargar_universo_lote

CAMPANIA_DEFAULT = _configuracion.CAMPANIA_DEFAULT
RUN_ID_DEFAULT = _configuracion.RUN_ID_DEFAULT
ULTIMO_CIERRE_DEFAULT = _configuracion.ULTIMO_CIERRE_DEFAULT


def normalizar_fundo(valor: object) -> str:
    clave = str(valor or "").strip().casefold()
    if clave in {"aqu anqa 1", "arena", "arena azul"}:
        return "Arena"
    if clave in {"aqu anqa 2", "quri", "quri allpa"}:
        return "Quri"
    if clave in {"aqu anqa 3", "aqu anqa 5", "kawsay", "kawsay allpa"}:
        return "Kawsay"
    if clave in {"aqu anqa 4", "ayllu", "ayllu allpa"}:
        return "Ayllu"
    return str(valor)


def cargar_universo_lote(
    *,
    run_id: int = RUN_ID_DEFAULT,
    campania: str = CAMPANIA_DEFAULT,
    ultimo_cierre: pd.Timestamp = ULTIMO_CIERRE_DEFAULT,
) -> pd.DataFrame:
    """Fachada compatible; la implementación vive en un servicio reutilizable."""

    return _cargar_universo_lote(
        run_id=run_id,
        campania=campania,
        ultimo_cierre=ultimo_cierre,
    )


__all__ = [
    "CAMPANIA_DEFAULT",
    "RUN_ID_DEFAULT",
    "ULTIMO_CIERRE_DEFAULT",
    "_cargar_universo_lote",
    "cargar_universo_lote",
    "normalizar_fundo",
]

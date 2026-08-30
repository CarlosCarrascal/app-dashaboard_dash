"""Semántica temporal de las versiones R09."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

_VERSION = re.compile(r"^S(?P<semana>\d{1,2})(?:_v(?P<sufijo>.+))?$", re.IGNORECASE)


@dataclass(frozen=True)
class VersionForecast:
    codigo: str
    semana_emision: int | None
    iteracion: int | None
    escenario: str | None

    @property
    def oficial(self) -> bool:
        return self.semana_emision is not None and self.escenario is None


def parsear_version(codigo: object) -> VersionForecast:
    texto = "" if codigo is None else str(codigo).strip()
    match = _VERSION.match(texto)
    if not match:
        return VersionForecast(texto, None, None, "no_parseable")
    sufijo = match.group("sufijo")
    if sufijo is None:
        return VersionForecast(texto, int(match.group("semana")), 1, None)
    if sufijo.isdigit():
        return VersionForecast(texto, int(match.group("semana")), int(sufijo), None)
    return VersionForecast(texto, int(match.group("semana")), None, sufijo.upper())


def fecha_emision_desde_objetivo(fecha_objetivo: object, semana_emision: int) -> pd.Timestamp:
    """Lunes ISO de emisión usando el año ISO de la fecha objetivo.

    Si el código apunta a una semana posterior al objetivo, se prueba el año ISO anterior.
    Eso cubre campañas que cruzan diciembre/enero sin deducir el año desde `C202x`.
    """
    objetivo = pd.Timestamp(fecha_objetivo).normalize()
    iso_year = int(objetivo.isocalendar().year)
    candidata = pd.Timestamp.fromisocalendar(iso_year, semana_emision, 1)
    if candidata > objetivo:
        anterior = pd.Timestamp.fromisocalendar(iso_year - 1, semana_emision, 1)
        if anterior <= objetivo:
            candidata = anterior
    return candidata


def banda_horizonte(horizonte: int) -> str:
    if horizonte <= 2:
        return "operativo"
    if horizonte <= 6:
        return "planificacion"
    return "escenario"

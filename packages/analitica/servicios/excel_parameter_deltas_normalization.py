"""Normalización y constantes del screening de parámetros Excel."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

SEMANAS = tuple(range(24, 36))
FUNDOS = ("Arena", "Ayllu", "Kawsay", "Quri")
ALIASES_FUNDO = {
    "Arena": ("arena",),
    "Ayllu": ("ayllu",),
    "Kawsay": ("kawsay",),
    "Quri": ("quri", "qury"),
}
TOKENS_VARIANTE = ("edi", "oli", "v2", "v3", "vdr", "copia", "copy", "eangulo")
PARAMETROS = (
    "X1",
    "O1",
    "N1",
    "X2",
    "O2",
    "N2",
    "X3",
    "O3",
    "N3",
    "A1",
    "B1",
    "A2",
    "B2",
    "A3",
    "B3",
)


def _normalizar_texto(valor: object) -> str:
    return " ".join(str(valor or "").strip().casefold().replace("_", " ").split())


def _es_variante(nombre: str) -> bool:
    stem = _normalizar_texto(Path(nombre).stem)
    return any(
        re.search(rf"(?:^|[ -]){re.escape(token)}(?:$|[ -])", stem) or stem.endswith(token)
        for token in TOKENS_VARIANTE
    )


def _columna(tabla: pd.DataFrame, nombre: str) -> str | None:
    buscado = nombre.casefold().replace(" ", "")
    for columna in tabla.columns:
        if str(columna).strip().casefold().replace(" ", "") == buscado:
            return str(columna)
    return None


def _clave_lote(tabla: pd.DataFrame) -> pd.Series:
    modulo = _columna(tabla, "Modulo")
    lote = _columna(tabla, "Lote")
    if modulo is None or lote is None:
        raise ValueError("La hoja no contiene Modulo/Lote")
    return tabla[modulo].map(_normalizar_texto) + "|" + tabla[lote].map(_normalizar_texto)


__all__ = [
    "ALIASES_FUNDO",
    "FUNDOS",
    "PARAMETROS",
    "SEMANAS",
    "TOKENS_VARIANTE",
    "_clave_lote",
    "_columna",
    "_es_variante",
    "_normalizar_texto",
]

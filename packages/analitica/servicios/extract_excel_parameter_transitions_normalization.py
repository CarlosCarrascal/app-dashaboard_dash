"""Normalización de nombres y valores para transiciones Excel."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Sequence

import pandas as pd

from analitica.proyeccion.hibrido_parametros_asof import (
    PARAMETROS_NOMBRADOS,
    normalizar_parametros_excel,
)
from analitica.proyeccion.parametros_excel import seleccionar_libros_parametros

KEY_COLUMNS = ["modulo", "lote"]


def _canonical_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _clean_identifier(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "nat"} else text


def _unique_headers(values: Sequence[object]) -> list[str]:
    headers: list[str] = []
    counts: dict[str, int] = {}
    for index, value in enumerate(values):
        base = str(value).strip() or f"__unnamed_{index}"
        count = counts.get(base, 0)
        counts[base] = count + 1
        headers.append(base if count == 0 else f"{base}__{count + 1}")
    return headers


def _column_lookup(frame: pd.DataFrame) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for column in frame.columns:
        canonical = _canonical_text(column)
        if canonical and canonical not in lookup:
            lookup[canonical] = str(column)
    return lookup


def _required_column(frame: pd.DataFrame, canonical: str) -> str:
    column = _column_lookup(frame).get(canonical)
    if column is None:
        raise ValueError(f"Falta la columna requerida {canonical!r}")
    return column


def _optional_series(frame: pd.DataFrame, canonical: str, *, dtype: str = "object") -> pd.Series:
    column = _column_lookup(frame).get(canonical)
    if column is None:
        return pd.Series(pd.NA, index=frame.index, dtype=dtype)
    return frame[column]


def _assert_unique_keys(frame: pd.DataFrame, *, source: str, sheet: str) -> None:
    duplicated = frame.duplicated(KEY_COLUMNS, keep=False)
    if duplicated.any():
        examples = frame.loc[duplicated, KEY_COLUMNS].head(5).to_dict("records")
        raise ValueError(f"Claves duplicadas en {source}/{sheet}: {examples}")


__all__ = [
    "KEY_COLUMNS",
    "PARAMETROS_NOMBRADOS",
    "_assert_unique_keys",
    "_canonical_text",
    "_clean_identifier",
    "_column_lookup",
    "_optional_series",
    "_required_column",
    "_unique_headers",
    "normalizar_parametros_excel",
    "seleccionar_libros_parametros",
]

"""Lectura y preparación de snapshots de libros Excel."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .extract_excel_parameter_transitions_normalization import (
    KEY_COLUMNS,
    PARAMETROS_NOMBRADOS,
    _assert_unique_keys,
    _canonical_text,
    _clean_identifier,
    _column_lookup,
    _optional_series,
    _required_column,
    _unique_headers,
    normalizar_parametros_excel,
)


@dataclass(frozen=True)
class WorkbookSnapshot:
    """Estado mínimo de un libro canónico, sin ninguna salida de forecast."""

    semana: int
    fundo: str
    path: Path
    sha256: str
    frame: pd.DataFrame
    fepas_indices: tuple[int, ...]


def _find_header_index(rows: Sequence[Sequence[object]], required: set[str]) -> int:
    for index, row in enumerate(rows[:8]):
        available = {
            _canonical_text(value)
            for value in row
        }
        if required.issubset(available):
            return index
    raise ValueError(f"No se encontró cabecera con columnas requeridas: {sorted(required)}")


def _table_from_rows(rows: Sequence[Sequence[object]], required: set[str]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    header_index = _find_header_index(rows, required)
    headers = _unique_headers(rows[header_index])
    body = []
    width = len(headers)
    for row in rows[header_index + 1 :]:
        values = list(row[:width]) + [None] * max(0, width - len(row))
        body.append(values[:width])
    return pd.DataFrame(body, columns=headers)


def _prepare_parameters(rows: Sequence[Sequence[object]], source: str) -> pd.DataFrame:
    raw = _table_from_rows(rows, {"modulo", "lote", "x1", "o1", "n1"})
    normalized = normalizar_parametros_excel(raw)
    module_column = _required_column(normalized, "modulo")
    lot_column = _required_column(normalized, "lote")
    output = pd.DataFrame(
        {
            "modulo": normalized[module_column].map(_clean_identifier),
            "lote": normalized[lot_column].map(_clean_identifier),
            "turno_parametros": _optional_series(normalized, "turno").map(_clean_identifier),
        }
    )
    for parameter in PARAMETROS_NOMBRADOS:
        output[parameter] = pd.to_numeric(normalized.get(parameter), errors="coerce")
    output = output[output.modulo.ne("") & output.lote.ne("")].copy()
    output["parametros_presente"] = True
    _assert_unique_keys(output, source=source, sheet="Parametros")
    return output


def _prepare_panel(
    rows: Sequence[Sequence[object]], source: str
) -> tuple[pd.DataFrame, tuple[int, ...]]:
    raw = _table_from_rows(rows, {"modulo", "lote", "finicio"})
    lookup = _column_lookup(raw)
    module_column = _required_column(raw, "modulo")
    lot_column = _required_column(raw, "lote")
    output = pd.DataFrame(
        {
            "modulo": raw[module_column].map(_clean_identifier),
            "lote": raw[lot_column].map(_clean_identifier),
            "turno_panel": _optional_series(raw, "turno").map(_clean_identifier),
            "finicio": pd.to_datetime(
                _optional_series(raw, "finicio"), errors="coerce"
            ).dt.normalize(),
            "caida": pd.to_numeric(_optional_series(raw, "caida"), errors="coerce"),
        }
    )
    fepas: dict[int, str] = {}
    for canonical, original in lookup.items():
        match = re.fullmatch(r"fepas(\d+)", canonical)
        if match:
            fepas[int(match.group(1))] = original
    for index, original in sorted(fepas.items()):
        output[f"fepas{index}"] = pd.to_datetime(raw[original], errors="coerce").dt.normalize()
    output = output[output.modulo.ne("") & output.lote.ne("")].copy()
    output["panel_presente"] = True
    _assert_unique_keys(output, source=source, sheet="Panel")
    return output, tuple(sorted(fepas))


def _read_snapshot(manifest_row: Mapping[str, object]) -> WorkbookSnapshot:
    try:
        from python_calamine import CalamineWorkbook
    except ImportError as exc:  # pragma: no cover - dependencia opcional de ejecución
        raise RuntimeError("python-calamine es necesario para leer los libros xlsm") from exc

    path = Path(str(manifest_row["ruta_fuente"])).resolve()
    workbook = CalamineWorkbook.from_path(str(path))
    parameter_rows = workbook.get_sheet_by_name("Parametros").to_python()
    panel_rows = workbook.get_sheet_by_name("Panel").to_python()
    parameters = _prepare_parameters(parameter_rows, path.name)
    panel, fepas_indices = _prepare_panel(panel_rows, path.name)
    merged = parameters.merge(panel, on=KEY_COLUMNS, how="outer", validate="one_to_one")
    merged["parametros_presente"] = merged["parametros_presente"].fillna(False).astype(bool)
    merged["panel_presente"] = merged["panel_presente"].fillna(False).astype(bool)
    merged["turno"] = merged["turno_panel"].where(
        merged["turno_panel"].astype("string").fillna("").ne(""),
        merged["turno_parametros"],
    )
    merged.drop(columns=["turno_panel", "turno_parametros"], inplace=True)
    merged.sort_values(KEY_COLUMNS, inplace=True, kind="stable")
    merged.reset_index(drop=True, inplace=True)
    return WorkbookSnapshot(
        semana=int(manifest_row["semana_emision"]),
        fundo=str(manifest_row["fundo_operativo"]),
        path=path,
        sha256=str(manifest_row["sha256_fuente"]),
        frame=merged,
        fepas_indices=fepas_indices,
    )
__all__ = [
    "WorkbookSnapshot",
    "_find_header_index",
    "_prepare_panel",
    "_prepare_parameters",
    "_read_snapshot",
    "_table_from_rows",
]

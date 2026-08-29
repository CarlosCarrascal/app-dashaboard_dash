"""Cálculo de transiciones y reporte de cobertura de libros Excel."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from .extract_excel_parameter_transitions_io import WorkbookSnapshot, _read_snapshot
from .extract_excel_parameter_transitions_normalization import (
    KEY_COLUMNS,
    PARAMETROS_NOMBRADOS,
    seleccionar_libros_parametros,
)


def _difference_days(current: pd.Series, previous: pd.Series) -> pd.Series:
    current_dates = pd.to_datetime(current, errors="coerce")
    previous_dates = pd.to_datetime(previous, errors="coerce")
    return (current_dates - previous_dates).dt.total_seconds().div(86_400.0)


def _numeric_changed(previous: pd.Series, current: pd.Series) -> pd.Series:
    previous_numeric = pd.to_numeric(previous, errors="coerce")
    current_numeric = pd.to_numeric(current, errors="coerce")
    one_missing = previous_numeric.isna() ^ current_numeric.isna()
    both = previous_numeric.notna() & current_numeric.notna()
    changed = pd.Series(False, index=previous.index)
    changed.loc[one_missing] = True
    changed.loc[both] = ~np.isclose(
        previous_numeric.loc[both], current_numeric.loc[both], rtol=1e-9, atol=1e-12
    )
    return changed


def _date_changed(previous: pd.Series, current: pd.Series) -> pd.Series:
    previous_dates = pd.to_datetime(previous, errors="coerce")
    current_dates = pd.to_datetime(current, errors="coerce")
    one_missing = previous_dates.isna() ^ current_dates.isna()
    both = previous_dates.notna() & current_dates.notna()
    changed = pd.Series(False, index=previous.index)
    changed.loc[one_missing] = True
    changed.loc[both] = previous_dates.loc[both].ne(current_dates.loc[both])
    return changed


def _safe_log_ratio(current: pd.Series, previous: pd.Series) -> pd.Series:
    current_numeric = pd.to_numeric(current, errors="coerce")
    previous_numeric = pd.to_numeric(previous, errors="coerce")
    valid = current_numeric.gt(0) & previous_numeric.gt(0)
    output = pd.Series(np.nan, index=current.index, dtype=float)
    output.loc[valid] = np.log(current_numeric.loc[valid] / previous_numeric.loc[valid])
    return output


def _asof_status(
    previous_week: int,
    current_week: int,
    emission_dates: Mapping[int, pd.Timestamp],
) -> tuple[pd.Timestamp | None, pd.Timestamp | None, bool, str]:
    previous_date = emission_dates.get(previous_week)
    current_date = emission_dates.get(current_week)
    if current_week != previous_week + 1:
        return previous_date, current_date, False, "emisiones_no_consecutivas"
    if previous_date is None or current_date is None:
        return previous_date, current_date, False, "sin_fechas_emision_verificadas"
    if pd.isna(previous_date) or pd.isna(current_date):
        return previous_date, current_date, False, "fecha_emision_invalida"
    if pd.Timestamp(previous_date) >= pd.Timestamp(current_date):
        return previous_date, current_date, False, "fechas_emision_no_crecientes"
    return previous_date, current_date, True, "estricto"


def _transition_frame(
    previous: WorkbookSnapshot,
    current: WorkbookSnapshot,
    *,
    campaign: str,
    emission_dates: Mapping[int, pd.Timestamp],
) -> tuple[pd.DataFrame, dict[str, object]]:
    if previous.fundo != current.fundo:
        raise ValueError("No se pueden comparar libros de fundos distintos")
    if current.semana != previous.semana + 1:
        raise ValueError("El extractor no une emisiones con semanas intermedias faltantes")

    all_fepas = sorted(set(previous.fepas_indices) | set(current.fepas_indices))
    value_columns = ["turno", *PARAMETROS_NOMBRADOS, "caida", "finicio"] + [
        f"fepas{index}" for index in all_fepas
    ]
    for frame in (previous.frame, current.frame):
        for column in value_columns:
            if column not in frame:
                frame[column] = pd.NA

    previous_columns = KEY_COLUMNS + ["parametros_presente", "panel_presente", *value_columns]
    current_columns = KEY_COLUMNS + ["parametros_presente", "panel_presente", *value_columns]
    previous_frame = previous.frame[previous_columns].rename(
        columns={
            column: f"{column}_anterior" for column in previous_columns if column not in KEY_COLUMNS
        }
    )
    current_frame = current.frame[current_columns].rename(
        columns={
            column: f"{column}_actual" for column in current_columns if column not in KEY_COLUMNS
        }
    )
    output = previous_frame.merge(
        current_frame,
        on=KEY_COLUMNS,
        how="outer",
        validate="one_to_one",
        indicator=True,
    )
    output["estado_lote"] = (
        output["_merge"]
        .map(
            {
                "both": "comparable",
                "left_only": "retirado_en_actual",
                "right_only": "nuevo_en_actual",
            }
        )
        .astype("string")
    )
    output.drop(columns="_merge", inplace=True)

    for side in ("anterior", "actual"):
        for column in ("parametros_presente", "panel_presente"):
            output[f"{column}_{side}"] = output[f"{column}_{side}"].fillna(False).astype(bool)

    changed_parameter_columns: list[str] = []
    for parameter in PARAMETROS_NOMBRADOS:
        previous_column = f"{parameter}_anterior"
        current_column = f"{parameter}_actual"
        output[f"delta_{parameter}"] = pd.to_numeric(
            output[current_column], errors="coerce"
        ) - pd.to_numeric(output[previous_column], errors="coerce")
        changed_column = f"cambio_{parameter}"
        output[changed_column] = _numeric_changed(output[previous_column], output[current_column])
        changed_parameter_columns.append(changed_column)
        if parameter.startswith(("O", "N", "A")):
            output[f"delta_log_{parameter}"] = _safe_log_ratio(
                output[current_column], output[previous_column]
            )
    output["n_parametros_cambiados"] = output[changed_parameter_columns].sum(axis=1).astype(int)

    output["delta_caida"] = pd.to_numeric(output["caida_actual"], errors="coerce") - pd.to_numeric(
        output["caida_anterior"], errors="coerce"
    )
    output["cambio_caida"] = _numeric_changed(output["caida_anterior"], output["caida_actual"])
    output["delta_finicio_dias"] = _difference_days(
        output["finicio_actual"], output["finicio_anterior"]
    )
    output["cambio_finicio"] = _date_changed(output["finicio_anterior"], output["finicio_actual"])

    fepas_delta_columns: list[str] = []
    fepas_changed_columns: list[str] = []
    for index in all_fepas:
        previous_column = f"fepas{index}_anterior"
        current_column = f"fepas{index}_actual"
        delta_column = f"delta_fepas{index}_dias"
        changed_column = f"cambio_fepas{index}"
        output[delta_column] = _difference_days(output[current_column], output[previous_column])
        output[changed_column] = _date_changed(output[previous_column], output[current_column])
        fepas_delta_columns.append(delta_column)
        fepas_changed_columns.append(changed_column)
    if fepas_delta_columns:
        output["n_fepas_cambiadas"] = output[fepas_changed_columns].sum(axis=1).astype(int)
        output["mediana_delta_fepas_dias"] = output[fepas_delta_columns].median(axis=1, skipna=True)
        output["max_abs_delta_fepas_dias"] = (
            output[fepas_delta_columns].abs().max(axis=1, skipna=True)
        )
    else:
        output["n_fepas_cambiadas"] = 0
        output["mediana_delta_fepas_dias"] = np.nan
        output["max_abs_delta_fepas_dias"] = np.nan
    previous_fepas = [f"fepas{index}_anterior" for index in all_fepas]
    current_fepas = [f"fepas{index}_actual" for index in all_fepas]
    output["n_pasadas_anterior"] = output[previous_fepas].notna().sum(axis=1).astype(int)
    output["n_pasadas_actual"] = output[current_fepas].notna().sum(axis=1).astype(int)
    output["cambio_n_pasadas"] = output["n_pasadas_actual"] - output["n_pasadas_anterior"]

    previous_date, current_date, strict_asof, asof_reason = _asof_status(
        previous.semana, current.semana, emission_dates
    )
    output.insert(0, "campania", campaign)
    output.insert(1, "fundo", current.fundo)
    output.insert(2, "emision_anterior", f"S{previous.semana:02d}")
    output.insert(3, "emision_actual", f"S{current.semana:02d}")
    output.insert(4, "semana_emision_anterior", previous.semana)
    output.insert(5, "semana_emision_actual", current.semana)
    output.insert(6, "fecha_emision_anterior", previous_date)
    output.insert(7, "fecha_emision_actual", current_date)
    output.insert(8, "sha256_anterior", previous.sha256)
    output.insert(9, "sha256_actual", current.sha256)
    output.insert(10, "archivo_anterior", previous.path.name)
    output.insert(11, "archivo_actual", current.path.name)
    output.insert(12, "ruta_anterior", str(previous.path))
    output.insert(13, "ruta_actual", str(current.path))
    output.insert(14, "transicion_canonicamente_consecutiva", True)
    output.insert(15, "transicion_asof_estricta", strict_asof)
    output.insert(16, "motivo_asof", asof_reason)
    output["fila_asof_utilizable"] = (
        output["transicion_asof_estricta"]
        & output["estado_lote"].eq("comparable")
        & output["parametros_presente_anterior"]
        & output["parametros_presente_actual"]
        & output["panel_presente_anterior"]
        & output["panel_presente_actual"]
    )
    output["transition_id"] = (
        output["campania"].astype(str)
        + "|"
        + output["fundo"].astype(str)
        + "|"
        + output["emision_anterior"].astype(str)
        + "-"
        + output["emision_actual"].astype(str)
        + "|"
        + output["modulo"].astype(str)
        + "|"
        + output["lote"].astype(str)
    )
    output.sort_values(
        ["semana_emision_actual", "fundo", "modulo", "lote"],
        inplace=True,
        kind="stable",
    )
    output.reset_index(drop=True, inplace=True)

    common = output.estado_lote.eq("comparable")
    pair_report = {
        "fundo": current.fundo,
        "emision_anterior": f"S{previous.semana:02d}",
        "emision_actual": f"S{current.semana:02d}",
        "archivo_anterior": previous.path.name,
        "archivo_actual": current.path.name,
        "sha256_anterior": previous.sha256,
        "sha256_actual": current.sha256,
        "fecha_emision_anterior": previous_date,
        "fecha_emision_actual": current_date,
        "transicion_asof_estricta": strict_asof,
        "motivo_asof": asof_reason,
        "filas_union": int(len(output)),
        "lotes_comparables": int(common.sum()),
        "lotes_nuevos": int(output.estado_lote.eq("nuevo_en_actual").sum()),
        "lotes_retirados": int(output.estado_lote.eq("retirado_en_actual").sum()),
        "cobertura_lotes_comparables": float(common.mean()) if len(output) else 0.0,
        "cobertura_parametros_ambos": float(
            (output.parametros_presente_anterior & output.parametros_presente_actual).mean()
        )
        if len(output)
        else 0.0,
        "cobertura_panel_ambos": float(
            (output.panel_presente_anterior & output.panel_presente_actual).mean()
        )
        if len(output)
        else 0.0,
        "indices_fepas": all_fepas,
    }
    return output, pair_report


def _extract_transitions(
    source_root: Path,
    *,
    weeks: Sequence[int],
    campaign: str,
    emission_dates: Mapping[int, pd.Timestamp] | None = None,
    selector=seleccionar_libros_parametros,
    reader=_read_snapshot,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Construye el dataset candidate-only en memoria."""

    manifest, missing = selector(source_root, semanas=list(weeks))
    if manifest.empty:
        raise ValueError("El selector canónico no encontró libros para las semanas solicitadas")
    if not manifest["variante"].eq("base").all():
        raise ValueError("El extractor candidate-only no acepta variantes promovidas")

    records = manifest.sort_values(["fundo_operativo", "semana_emision"]).to_dict("records")
    by_key = {(str(row["fundo_operativo"]), int(row["semana_emision"])): row for row in records}
    cache: dict[str, WorkbookSnapshot] = {}
    frames: list[pd.DataFrame] = []
    pair_reports: list[dict[str, object]] = []
    emission_dates = emission_dates or {}

    for fund in sorted(manifest.fundo_operativo.unique()):
        selected_weeks = sorted(
            int(value)
            for value in manifest.loc[manifest.fundo_operativo.eq(fund), "semana_emision"].unique()
        )
        for current_week in selected_weeks:
            previous_week = current_week - 1
            previous_row = by_key.get((fund, previous_week))
            current_row = by_key.get((fund, current_week))
            if previous_row is None or current_row is None:
                continue
            for row in (previous_row, current_row):
                path_key = str(Path(str(row["ruta_fuente"])).resolve())
                if path_key not in cache:
                    cache[path_key] = reader(row)
            transition, pair_report = _transition_frame(
                cache[str(Path(str(previous_row["ruta_fuente"])).resolve())],
                cache[str(Path(str(current_row["ruta_fuente"])).resolve())],
                campaign=campaign,
                emission_dates=emission_dates,
            )
            frames.append(transition)
            pair_reports.append(pair_report)

    if not frames:
        raise ValueError("No existen pares canónicos consecutivos en las semanas solicitadas")
    transitions = pd.concat(frames, ignore_index=True, sort=False)
    transitions.sort_values(
        ["semana_emision_actual", "fundo", "modulo", "lote"],
        inplace=True,
        kind="stable",
    )
    transitions.reset_index(drop=True, inplace=True)

    comparable = transitions.estado_lote.eq("comparable")
    parameter_both = (
        transitions.parametros_presente_anterior & transitions.parametros_presente_actual
    )
    panel_both = transitions.panel_presente_anterior & transitions.panel_presente_actual
    report = {
        "schema_version": "excel-parameter-transitions-v1",
        "candidate_only": True,
        "postgresql_persisted": False,
        "reads_forecast_outputs": False,
        "source_root": str(Path(source_root).resolve()),
        "campaign": campaign,
        "weeks_requested": list(map(int, weeks)),
        "selection": {
            "selected_workbooks": int(len(manifest)),
            "missing_week_fund_combinations": int(len(missing)),
            "workbooks_read": int(len(cache)),
            "funds": sorted(map(str, manifest.fundo_operativo.unique())),
            "weeks_selected": sorted(map(int, manifest.semana_emision.unique())),
            "canonical_pairs": int(len(pair_reports)),
        },
        "coverage": {
            "transition_rows": int(len(transitions)),
            "comparable_lot_rows": int(comparable.sum()),
            "new_lot_rows": int(transitions.estado_lote.eq("nuevo_en_actual").sum()),
            "removed_lot_rows": int(transitions.estado_lote.eq("retirado_en_actual").sum()),
            "comparable_lot_coverage": float(comparable.mean()),
            "parameters_in_both_coverage": float(parameter_both.mean()),
            "panel_in_both_coverage": float(panel_both.mean()),
            "strict_asof_transition_rows": int(transitions.transicion_asof_estricta.sum()),
            "strict_asof_usable_rows": int(transitions.fila_asof_utilizable.sum()),
        },
        "asof_contract": {
            "canonical_sequence_is_not_date_certification": True,
            "verified_emission_dates_supplied": sorted(map(int, emission_dates)),
            "strict_rule": "Sactual=Sprevia+1 and fecha_previa<fecha_actual",
        },
        "manifest": manifest.to_dict("records"),
        "missing": missing.to_dict("records"),
        "pairs": pair_reports,
        "columns": list(map(str, transitions.columns)),
    }
    return transitions, report


__all__ = [
    "_asof_status",
    "_date_changed",
    "_difference_days",
    "_extract_transitions",
    "_numeric_changed",
    "_safe_log_ratio",
    "_transition_frame",
]

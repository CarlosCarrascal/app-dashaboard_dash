"""Normalización y evaluación del candidato de turno temporal."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..compartido import normalizar_forecast_candidate
from .turno_temporal_contratos import (
    CLAVE_UNIVERSO,
)


def auditar_universo_candidate(universo: pd.DataFrame, candidato: pd.DataFrame) -> dict[str, Any]:
    """Compara claves y reales sin convertir ausencias en ceros silenciosos."""

    base = normalizar_forecast_candidate(universo)
    pred = normalizar_forecast_candidate(candidato)
    clave = list(CLAVE_UNIVERSO)
    claves_base = base[clave].drop_duplicates()
    claves_pred = pred[clave].drop_duplicates()
    cruce = claves_base.merge(claves_pred, on=clave, how="outer", indicator=True)
    faltantes = int(cruce._merge.eq("left_only").sum())
    extras = int(cruce._merge.eq("right_only").sum())
    resultado: dict[str, Any] = {
        "n_universo": int(len(claves_base)),
        "n_candidato": int(len(claves_pred)),
        "faltantes": faltantes,
        "extras": extras,
        "cobertura_filas": float((len(claves_base) - faltantes) / len(claves_base))
        if len(claves_base)
        else np.nan,
        "universo_identico": faltantes == 0 and extras == 0,
    }
    if "real_kg" in base and "real_kg" in pred:
        reales = base[clave + ["real_kg"]].merge(
            pred[clave + ["real_kg"]], on=clave, how="inner", suffixes=("_base", "_cand")
        )
        distintos = ~np.isclose(
            pd.to_numeric(reales.real_kg_base, errors="coerce"),
            pd.to_numeric(reales.real_kg_cand, errors="coerce"),
            equal_nan=True,
        )
        resultado["reales_distintos"] = int(distintos.sum())
        resultado["denominador_identico"] = not bool(distintos.any())
    return resultado


def metricas_adversariales(
    universo: pd.DataFrame,
    candidato: pd.DataFrame,
) -> dict[str, Any]:
    """Muestra cancelación agregada, precisión por lote y cobertura por fila."""

    if "real_kg" not in universo:
        raise ValueError("El universo debe contener real_kg para evaluar")
    base = normalizar_forecast_candidate(universo)
    pred = normalizar_forecast_candidate(candidato)
    clave = list(CLAVE_UNIVERSO)
    columnas = clave + ["p50_kg"]
    alineado = base[clave + ["real_kg"]].merge(
        pred[columnas].rename(columns={"p50_kg": "pred_kg"}),
        on=clave,
        how="left",
        validate="one_to_one",
    )
    emitio = alineado.pred_kg.notna()
    alineado["pred_operacional_kg"] = alineado.pred_kg.fillna(0.0)
    real_total = float(alineado.real_kg.abs().sum())
    error_lote = (alineado.pred_operacional_kg - alineado.real_kg).abs()
    semanal = alineado.groupby(
        [
            "evaluation_contract_id",
            "campania",
            "fecha_emision",
            "fecha_objetivo",
            "horizonte_semanas",
        ],
        as_index=False,
    ).agg(real_kg=("real_kg", "sum"), pred_kg=("pred_operacional_kg", "sum"))
    denom_semana = float(semanal.real_kg.abs().sum())
    wape_empresa = (
        float((semanal.pred_kg - semanal.real_kg).abs().sum() / denom_semana)
        if denom_semana
        else np.nan
    )
    wape_lote = float(error_lote.sum() / real_total) if real_total else np.nan
    cobertura_volumen = (
        float(alineado.loc[emitio, "real_kg"].abs().sum() / real_total) if real_total else np.nan
    )
    resultado: dict[str, Any] = {
        "wape_empresa_semana": wape_empresa,
        "wape_lote_semana": wape_lote,
        "brecha_cancelacion": float(wape_lote - wape_empresa),
        "cobertura_filas": float(emitio.mean()) if len(emitio) else np.nan,
        "cobertura_volumen": cobertura_volumen,
        "n_lote_emision_semana": int(len(alineado)),
        "n_semanas_empresa": int(len(semanal)),
    }
    if "fundo" in base:
        por_fundo = base[clave + ["fundo", "real_kg"]].merge(
            pred[columnas].rename(columns={"p50_kg": "pred_kg"}), on=clave, how="left"
        )
        por_fundo["pred_kg"] = por_fundo.pred_kg.fillna(0.0)
        resumen_fundo: dict[str, float] = {}
        for fundo, grupo in por_fundo.groupby("fundo", dropna=False):
            denom = float(grupo.real_kg.abs().sum())
            resumen_fundo[str(fundo)] = (
                float((grupo.pred_kg - grupo.real_kg).abs().sum() / denom) if denom else np.nan
            )
        resultado["wape_por_fundo"] = resumen_fundo
    return resultado


__all__ = [
    "auditar_universo_candidate",
    "metricas_adversariales",
    "normalizar_forecast_candidate",
]

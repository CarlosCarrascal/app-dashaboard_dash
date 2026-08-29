"""Evaluación y selección de configuraciones de small data H1."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .small_data_h1_configuracion import (
    FUNDOS,
    SEMANA_MAX_SELECCION,
    Configuracion,
    configuraciones,
)
from .small_data_h1_prediccion import predecir_rolling


def _metricas(tabla: pd.DataFrame, columna: str, grano: tuple[str, ...]) -> dict[str, float | int]:
    agregado = tabla.groupby(list(grano), as_index=False, dropna=False).agg(
        pred_kg=(columna, "sum"), real_kg=("real_kg", "sum")
    )
    error = agregado.pred_kg - agregado.real_kg
    denominador = float(agregado.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / denominador) if denominador else np.nan,
        "sesgo": float(error.sum() / denominador) if denominador else np.nan,
        "mae_kg": float(error.abs().mean()) if len(agregado) else np.nan,
        "n": int(len(agregado)),
        "real_kg": float(agregado.real_kg.sum()),
        "pred_kg": float(agregado.pred_kg.sum()),
    }


def _wins(
    tabla: pd.DataFrame,
    candidato: str,
    base: str,
    grano: tuple[str, ...],
) -> dict[str, float | int]:
    agregado = tabla.groupby(list(grano), as_index=False, dropna=False).agg(
        real_kg=("real_kg", "sum"),
        candidato_kg=(candidato, "sum"),
        base_kg=(base, "sum"),
    )
    error_candidato = (agregado.candidato_kg - agregado.real_kg).abs()
    error_base = (agregado.base_kg - agregado.real_kg).abs()
    return {
        "wins": int(error_candidato.lt(error_base).sum()),
        "empates": int(error_candidato.eq(error_base).sum()),
        "n": int(len(agregado)),
        "proporcion": float(error_candidato.lt(error_base).mean()) if len(agregado) else np.nan,
    }


def _resumen_periodo(
    panel: pd.DataFrame,
    lotes: pd.DataFrame,
    mascara_panel: pd.Series,
    mascara_lotes: pd.Series,
) -> dict[str, object]:
    bloque = panel.loc[mascara_panel].copy()
    lote_bloque = lotes.loc[mascara_lotes].copy()
    condicionado = lote_bloque.loc[lote_bloque.r09_emitio & lote_bloque.r09_kg.notna()].copy()
    real_total = float(lote_bloque.real_kg.abs().sum())
    real_condicionado = float(condicionado.real_kg.abs().sum())
    cobertura = {
        "candidato_lotes": 1.0 if len(lote_bloque) else np.nan,
        "candidato_volumen": 1.0 if real_total else np.nan,
        "r09_lotes": float(len(condicionado) / len(lote_bloque)) if len(lote_bloque) else np.nan,
        "r09_volumen": real_condicionado / real_total if real_total else np.nan,
    }
    por_fundo: dict[str, object] = {}
    for fundo in FUNDOS:
        fondo = bloque.loc[bloque.fundo_operativo.eq(fundo)]
        fondo_cond = condicionado.loc[condicionado.fundo_operativo.eq(fundo)]
        por_fundo[fundo] = {
            "completo": {
                "candidato": _metricas(fondo, "candidate_kg", ("fecha_objetivo",)),
                "macro": _metricas(fondo, "macro_kg", ("fecha_objetivo",)),
            },
            "r09_condicionado_mismo_universo": {
                "candidato": _metricas(fondo_cond, "candidate_kg", ("fecha_objetivo",)),
                "macro": _metricas(fondo_cond, "macro_kg", ("fecha_objetivo",)),
                "r09": _metricas(fondo_cond, "r09_kg", ("fecha_objetivo",)),
            },
        }
    return {
        "semanas": sorted(map(int, bloque.semana_objetivo.unique())),
        "empresa_completo": {
            "candidato": _metricas(bloque, "candidate_kg", ("fecha_objetivo",)),
            "macro": _metricas(bloque, "macro_kg", ("fecha_objetivo",)),
            "wins_candidato_vs_macro": _wins(
                bloque, "candidate_kg", "macro_kg", ("fecha_objetivo",)
            ),
        },
        "fundo_completo": {
            "candidato": _metricas(bloque, "candidate_kg", ("fecha_objetivo", "fundo_operativo")),
            "macro": _metricas(bloque, "macro_kg", ("fecha_objetivo", "fundo_operativo")),
            "wins_candidato_vs_macro": _wins(
                bloque,
                "candidate_kg",
                "macro_kg",
                ("fecha_objetivo", "fundo_operativo"),
            ),
        },
        "r09_condicionado_mismo_universo": {
            "empresa": {
                "candidato": _metricas(condicionado, "candidate_kg", ("fecha_objetivo",)),
                "macro": _metricas(condicionado, "macro_kg", ("fecha_objetivo",)),
                "r09": _metricas(condicionado, "r09_kg", ("fecha_objetivo",)),
                "wins_candidato_vs_r09": _wins(
                    condicionado, "candidate_kg", "r09_kg", ("fecha_objetivo",)
                ),
            },
            "fundo": {
                "candidato": _metricas(
                    condicionado,
                    "candidate_kg",
                    ("fecha_objetivo", "fundo_operativo"),
                ),
                "macro": _metricas(condicionado, "macro_kg", ("fecha_objetivo", "fundo_operativo")),
                "r09": _metricas(condicionado, "r09_kg", ("fecha_objetivo", "fundo_operativo")),
                "wins_candidato_vs_r09": _wins(
                    condicionado,
                    "candidate_kg",
                    "r09_kg",
                    ("fecha_objetivo", "fundo_operativo"),
                ),
            },
        },
        "cobertura": cobertura,
        "por_fundo": por_fundo,
    }


def seleccionar_configuracion(panel: pd.DataFrame) -> tuple[Configuracion, pd.DataFrame]:
    """Selecciona exclusivamente con resultados objetivo hasta S30."""

    filas: list[dict[str, object]] = []
    for config in configuraciones():
        pred = predecir_rolling(panel, config)
        desarrollo = pred.loc[pred.semana_objetivo.le(SEMANA_MAX_SELECCION)]
        empresa = _metricas(desarrollo, "candidate_kg", ("fecha_objetivo",))
        fundo = _metricas(desarrollo, "candidate_kg", ("fecha_objetivo", "fundo_operativo"))
        filas.append(
            {
                "configuracion_id": config.id,
                "configuracion": config,
                "wape_empresa": empresa["wape"],
                "wape_fundo": fundo["wape"],
                "sesgo_empresa": empresa["sesgo"],
                "n_semanas_ajustadas": int(
                    desarrollo.loc[desarrollo.modelo_ajustado, "semana_objetivo"].nunique()
                ),
            }
        )
    ranking = pd.DataFrame(filas).sort_values(
        ["wape_empresa", "wape_fundo", "sesgo_empresa"],
        key=lambda serie: serie.abs() if serie.name == "sesgo_empresa" else serie,
        kind="stable",
    )
    ganador = ranking.iloc[0].configuracion
    return ganador, ranking


__all__ = [
    "_metricas",
    "_resumen_periodo",
    "_wins",
    "seleccionar_configuracion",
]

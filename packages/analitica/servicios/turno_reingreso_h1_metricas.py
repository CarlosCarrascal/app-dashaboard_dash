"""Métricas y auditoría de aplicabilidad para run76 H1."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

from .turno_reingreso_h1_fuentes import CLAVE_LOTE


def auditar_aplicabilidad_h1(tabla: pd.DataFrame) -> dict[str, Any]:
    """Determina si la curva posee dos o más horizontes que redistribuir."""

    grupos = [
        "evaluation_contract_id",
        "campania",
        "fecha_emision",
        "lote_id",
    ]
    resumen = tabla.groupby(grupos, dropna=False).agg(
        n_horizontes=("horizonte_semanas", "nunique"),
        horizonte_min=("horizonte_semanas", "min"),
        horizonte_max=("horizonte_semanas", "max"),
    )
    grupos_redistribuibles = resumen.n_horizontes.ge(2)
    return {
        "grupos_emision_lote": int(len(resumen)),
        "horizontes_disponibles": sorted(int(v) for v in tabla.horizonte_semanas.unique()),
        "max_horizontes_por_emision_lote": int(resumen.n_horizontes.max()),
        "grupos_redistribuibles": int(grupos_redistribuibles.sum()),
        "cobertura_grupos_redistribuibles": float(grupos_redistribuibles.mean()),
        "aplicable": bool(grupos_redistribuibles.all() and len(resumen) > 0),
        "razon_bloqueo": (
            None
            if bool(grupos_redistribuibles.all() and len(resumen) > 0)
            else (
                "run76 solo conserva h1 por emisión-lote. La función pura conserva "
                "el total y necesita al menos dos horizontes contiguos para redistribuir; "
                "con un único punto toda configuración es matemáticamente un no-op."
            )
        ),
    }


def _metricas_agregadas(
    tabla: pd.DataFrame,
    columna: str,
    *,
    grano: Iterable[str],
) -> dict[str, float | int]:
    agregado = tabla.groupby(list(grano), as_index=False).agg(
        pred_kg=(columna, "sum"), real_kg=("real_kg", "sum")
    )
    error = agregado.pred_kg - agregado.real_kg
    denominador = float(agregado.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / denominador) if denominador else np.nan,
        "sesgo": float(error.sum() / denominador) if denominador else np.nan,
        "mae_kg": float(error.abs().mean()) if len(error) else np.nan,
        "n": int(len(agregado)),
        "real_kg": denominador,
        "pred_kg": float(agregado.pred_kg.sum()),
    }


def _cobertura(tabla: pd.DataFrame, disponible: pd.Series) -> dict[str, float | int]:
    mascara = disponible.fillna(False).astype(bool)
    denominador = float(tabla.real_kg.abs().sum())
    return {
        "filas_lote_disponibles": int(mascara.sum()),
        "filas_lote_totales": int(len(tabla)),
        "cobertura_filas_lote": float(mascara.mean()) if len(tabla) else 0.0,
        "cobertura_volumen": (
            float(tabla.loc[mascara, "real_kg"].abs().sum() / denominador) if denominador else 0.0
        ),
    }


def _evaluar_split(tabla: pd.DataFrame) -> dict[str, Any]:
    empresa = ("campania", "fecha_objetivo")
    fundo = ("campania", "fecha_objetivo", "fundo")
    r09_cond = tabla[tabla.r09_emitio].copy()
    resultado: dict[str, Any] = {
        "semanas": sorted(int(v) for v in tabla.semana_objetivo.unique()),
        "macro": {
            "empresa_semana": _metricas_agregadas(tabla, "macro_kg", grano=empresa),
            "fundo_semana": _metricas_agregadas(tabla, "macro_kg", grano=fundo),
            "cobertura": _cobertura(tabla, pd.Series(True, index=tabla.index)),
        },
        "r09_condicionado": {
            "empresa_semana": _metricas_agregadas(r09_cond, "r09_kg", grano=empresa),
            "fundo_semana": _metricas_agregadas(r09_cond, "r09_kg", grano=fundo),
            "cobertura": _cobertura(tabla, tabla.r09_emitio),
            "nota": (
                "R09 condicionado se evalúa solo donde emitió; su denominador es menor "
                "y no es una comparación pareada directa con Macro de cobertura completa."
            ),
        },
    }
    por_fundo: dict[str, Any] = {}
    for nombre, bloque in tabla.groupby("fundo", sort=True):
        r09_fundo = bloque[bloque.r09_emitio]
        macro_m = _metricas_agregadas(bloque, "macro_kg", grano=("campania", "fecha_objetivo"))
        r09_m = _metricas_agregadas(r09_fundo, "r09_kg", grano=("campania", "fecha_objetivo"))
        por_fundo[str(nombre)] = {
            "macro": macro_m,
            "r09_condicionado": r09_m,
            "cobertura_r09": _cobertura(bloque, bloque.r09_emitio),
            "candidate_noop_vs_macro_pp": 0.0,
            "candidate_noop_vs_r09_condicionado_pp": float(
                100.0 * (macro_m["wape"] - r09_m["wape"])
            ),
            "comparacion_candidate_vs_r09_pareada": False,
        }
    resultado["por_fundo"] = por_fundo
    return resultado


def _keyset_sha256(tabla: pd.DataFrame) -> str:
    llaves = tabla[CLAVE_LOTE].copy().sort_values(CLAVE_LOTE)
    serializado = llaves.astype(str).agg("|".join, axis=1).str.cat(sep="\n")
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()

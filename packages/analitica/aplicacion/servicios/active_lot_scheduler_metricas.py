"""Métricas, comparación y selección de configuración del scheduler."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

from .active_lot_scheduler_contratos import (
    SEMANA_DESARROLLO_FINAL,
    ConfiguracionScheduler,
    configuraciones,
)
from .active_lot_scheduler_prediccion import predecir_scheduler


def _metricas(tabla: pd.DataFrame, columna: str, grano: Iterable[str]) -> dict[str, float | int]:
    agregado = tabla.groupby(list(grano), as_index=False, dropna=False).agg(
        pred_kg=(columna, "sum"), real_kg=("real_kg", "sum")
    )
    error = agregado.pred_kg - agregado.real_kg
    den = float(agregado.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / den) if den else math.nan,
        "bias": float(error.sum() / den) if den else math.nan,
        "mae_kg": float(error.abs().mean()) if len(error) else math.nan,
        "n": int(len(agregado)),
        "real_kg": float(agregado.real_kg.sum()),
        "pred_kg": float(agregado.pred_kg.sum()),
    }


def _cobertura_y_ceros(tabla: pd.DataFrame, columna: str) -> dict[str, float | int]:
    positivos = tabla.real_kg.gt(0)
    den = float(tabla.loc[positivos, "real_kg"].sum())
    bandera = "emitio_candidate" if columna == "candidate_kg" else "emitio_macro"
    emitio = tabla[bandera].fillna(False).astype(bool)
    ceros = positivos & tabla[columna].fillna(0).le(1e-9)
    return {
        "cobertura_lotes_con_real": float(emitio[positivos].mean())
        if positivos.any()
        else math.nan,
        "cobertura_volumen": float(tabla.loc[positivos & emitio, "real_kg"].sum() / den)
        if den
        else math.nan,
        "falsos_ceros_lote_semana": int(ceros.sum()),
        "falsos_ceros_volumen_kg": float(tabla.loc[ceros, "real_kg"].sum()),
        "falsos_ceros_volumen_pct": float(tabla.loc[ceros, "real_kg"].sum() / den)
        if den
        else math.nan,
    }


def bootstrap_pareado(
    tabla: pd.DataFrame,
    candidato: str,
    referencia: str,
    *,
    repeticiones: int = 4_000,
) -> dict[str, Any] | None:
    semanal = tabla.groupby(["campania", "fecha_objetivo"], as_index=False).agg(
        real_kg=("real_kg", "sum"),
        candidato_kg=(candidato, "sum"),
        referencia_kg=(referencia, "sum"),
    )
    if semanal.empty:
        return None
    ec = (semanal.candidato_kg - semanal.real_kg).abs().to_numpy(float)
    er = (semanal.referencia_kg - semanal.real_kg).abs().to_numpy(float)
    real = semanal.real_kg.abs().to_numpy(float)
    rng = np.random.default_rng(20260825)
    diferencias: list[float] = []
    for _ in range(repeticiones):
        idx = rng.integers(0, len(semanal), len(semanal))
        den = float(real[idx].sum())
        if den:
            diferencias.append(float((ec[idx].sum() - er[idx].sum()) / den))
    intervalo = np.quantile(diferencias, [0.025, 0.975])
    den = float(real.sum())
    return {
        "n_semanas": int(len(semanal)),
        "diferencia_wape_pp": float(100 * (ec.sum() - er.sum()) / den),
        "ic95_diferencia_wape_pp": [float(100 * intervalo[0]), float(100 * intervalo[1])],
        "semanas_ganadas": int((ec < er).sum()),
    }


def resumir(tabla: pd.DataFrame) -> dict[str, Any]:
    empresa = ("campania", "fecha_objetivo")
    fundo = ("campania", "fecha_objetivo", "fundo")
    resultado: dict[str, Any] = {
        "empresa": {
            "candidate": _metricas(tabla, "candidate_kg", empresa),
            "macro": _metricas(tabla, "macro_kg", empresa),
        },
        "fundo": {
            "candidate": _metricas(tabla, "candidate_kg", fundo),
            "macro": _metricas(tabla, "macro_kg", fundo),
            "por_fundo_candidate": {
                str(nombre): _metricas(bloque, "candidate_kg", ("fecha_objetivo",))
                for nombre, bloque in tabla.groupby("fundo", sort=True)
            },
            "por_fundo_macro": {
                str(nombre): _metricas(bloque, "macro_kg", ("fecha_objetivo",))
                for nombre, bloque in tabla.groupby("fundo", sort=True)
            },
        },
        "cobertura_candidate": _cobertura_y_ceros(tabla, "candidate_kg"),
        "cobertura_macro": _cobertura_y_ceros(tabla, "macro_kg"),
        "bootstrap_vs_macro": bootstrap_pareado(tabla, "candidate_kg", "macro_kg"),
    }
    return resultado


def anexar_r09(tabla: pd.DataFrame, r09: pd.DataFrame) -> pd.DataFrame:
    referencia = r09[["campania", "fecha_objetivo", "fundo_operativo", "r09_kg"]].rename(
        columns={"fundo_operativo": "fundo"}
    )
    salida = tabla.merge(
        referencia,
        on=["campania", "fecha_objetivo", "fundo"],
        how="left",
        validate="many_to_one",
    )
    return salida


def resumir_con_r09(tabla: pd.DataFrame) -> dict[str, Any] | None:
    agregado = tabla.groupby(["campania", "fecha_objetivo", "fundo"], as_index=False).agg(
        real_kg=("real_kg", "sum"),
        candidate_kg=("candidate_kg", "sum"),
        macro_kg=("macro_kg", "sum"),
        r09_kg=("r09_kg", "first"),
    )
    semanas = agregado.groupby(["campania", "fecha_objetivo"]).filter(
        lambda b: len(b) == 4 and b.r09_kg.notna().all()
    )
    if semanas.empty:
        return None
    return {
        "empresa": {
            "candidate": _metricas(semanas, "candidate_kg", ("campania", "fecha_objetivo")),
            "macro": _metricas(semanas, "macro_kg", ("campania", "fecha_objetivo")),
            "r09": _metricas(semanas, "r09_kg", ("campania", "fecha_objetivo")),
        },
        "fundo": {
            "candidate": _metricas(
                semanas, "candidate_kg", ("campania", "fecha_objetivo", "fundo")
            ),
            "r09": _metricas(semanas, "r09_kg", ("campania", "fecha_objetivo", "fundo")),
        },
        "bootstrap_vs_r09": bootstrap_pareado(semanas, "candidate_kg", "r09_kg"),
        "n_semanas_comunes": int(semanas.fecha_objetivo.nunique()),
    }


def seleccionar_configuracion(
    contexto_c2026: pd.DataFrame,
    verdad_c2026: pd.DataFrame,
) -> tuple[ConfiguracionScheduler, pd.DataFrame, pd.DataFrame]:
    ranking: list[dict[str, Any]] = []
    predicciones: dict[str, pd.DataFrame] = {}
    for config in configuraciones():
        pred = predecir_scheduler(contexto_c2026, verdad_c2026, config)
        predicciones[config.id] = pred
        dev = pred.loc[pred.semana_iso.le(SEMANA_DESARROLLO_FINAL)].copy()
        empresa = _metricas(dev, "candidate_kg", ("fecha_objetivo",))
        fundo = _metricas(dev, "candidate_kg", ("fecha_objetivo", "fundo"))
        macro = _metricas(dev, "macro_kg", ("fecha_objetivo",))
        ceros = _cobertura_y_ceros(dev, "candidate_kg")
        score = (
            0.60 * float(empresa["wape"])
            + 0.25 * float(fundo["wape"])
            + 0.10 * abs(float(empresa["bias"]))
            + 0.05 * float(ceros["falsos_ceros_volumen_pct"])
        )
        ranking.append(
            {
                "configuracion_id": config.id,
                "score": score,
                "wape_empresa": empresa["wape"],
                "wape_fundo": fundo["wape"],
                "bias_empresa": empresa["bias"],
                "falsos_ceros_volumen_pct": ceros["falsos_ceros_volumen_pct"],
                "macro_wape_empresa": macro["wape"],
            }
        )
    orden = (
        pd.DataFrame(ranking)
        .sort_values(["score", "wape_empresa", "wape_fundo"], kind="stable")
        .reset_index(drop=True)
    )
    ganador_id = str(orden.iloc[0].configuracion_id)
    mapa = {config.id: config for config in configuraciones()}
    return mapa[ganador_id], predicciones[ganador_id], orden

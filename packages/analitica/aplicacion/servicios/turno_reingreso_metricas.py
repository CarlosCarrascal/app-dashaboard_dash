"""Métricas, selección y comparación posterior de R09 para run73."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from analitica.aplicacion.procesos.candidatos import ConfiguracionTurnoTemporal

from .turno_reingreso_fuentes import (
    CLAVE,
    HORIZONTE_MAX,
    HORIZONTE_MIN,
)


def _banda_horizonte(tabla: pd.DataFrame, banda: str) -> pd.DataFrame:
    if banda == "h1":
        return tabla[tabla.horizonte_semanas.eq(1)].copy()
    if banda == "h2_h6":
        return tabla[tabla.horizonte_semanas.between(2, 6)].copy()
    if banda == "h1_h6":
        return tabla.copy()
    raise ValueError(f"Banda desconocida: {banda}")


def _metricas(
    tabla: pd.DataFrame,
    columna: str,
    *,
    grano: Iterable[str],
) -> dict[str, float | int]:
    if tabla.empty:
        return {
            "wape": np.nan,
            "sesgo": np.nan,
            "mae_kg": np.nan,
            "n": 0,
            "real_kg": 0.0,
            "pred_kg": 0.0,
        }
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


def _metricas_bandas(tabla: pd.DataFrame, columna: str) -> dict[str, Any]:
    resultado: dict[str, Any] = {}
    for banda in ("h1", "h2_h6", "h1_h6"):
        bloque = _banda_horizonte(tabla, banda)
        resultado[banda] = {
            "empresa_semana": _metricas(
                bloque,
                columna,
                grano=("fecha_emision", "fecha_objetivo", "horizonte_semanas"),
            ),
            "fundo_semana": _metricas(
                bloque,
                columna,
                grano=(
                    "fecha_emision",
                    "fecha_objetivo",
                    "horizonte_semanas",
                    "fundo",
                ),
            ),
        }
    resultado["por_horizonte"] = {
        f"h{horizonte}": {
            "empresa_semana": _metricas(
                tabla[tabla.horizonte_semanas.eq(horizonte)],
                columna,
                grano=("fecha_emision", "fecha_objetivo", "horizonte_semanas"),
            ),
            "fundo_semana": _metricas(
                tabla[tabla.horizonte_semanas.eq(horizonte)],
                columna,
                grano=(
                    "fecha_emision",
                    "fecha_objetivo",
                    "horizonte_semanas",
                    "fundo",
                ),
            ),
        }
        for horizonte in range(HORIZONTE_MIN, HORIZONTE_MAX + 1)
    }
    resultado["por_fundo"] = {}
    for fundo, bloque in tabla.groupby("fundo", sort=True):
        resultado["por_fundo"][str(fundo)] = {
            banda: _metricas(
                _banda_horizonte(bloque, banda),
                columna,
                grano=("fecha_emision", "fecha_objetivo", "horizonte_semanas"),
            )
            for banda in ("h1", "h2_h6", "h1_h6")
        }
    return resultado


def _semanas_ganadas(
    tabla: pd.DataFrame,
    candidato: str,
    referencia: str,
    *,
    por_fundo: bool = False,
) -> dict[str, Any]:
    grano = ["fecha_emision", "fecha_objetivo", "horizonte_semanas"]
    if por_fundo:
        grano.append("fundo")
    resultado: dict[str, Any] = {}
    for banda in ("h1", "h2_h6", "h1_h6"):
        bloque = _banda_horizonte(tabla, banda)
        agregado = bloque.groupby(grano, as_index=False).agg(
            candidato_kg=(candidato, "sum"),
            referencia_kg=(referencia, "sum"),
            real_kg=("real_kg", "sum"),
        )
        err_c = (agregado.candidato_kg - agregado.real_kg).abs()
        err_r = (agregado.referencia_kg - agregado.real_kg).abs()
        gana = err_c.lt(err_r - 1e-9)
        pierde = err_c.gt(err_r + 1e-9)
        empata = ~(gana | pierde)
        resultado[banda] = {
            "ganadas": int(gana.sum()),
            "perdidas": int(pierde.sum()),
            "empatadas": int(empata.sum()),
            "total": int(len(agregado)),
            "porcentaje_ganadas": float(gana.mean()) if len(gana) else np.nan,
        }
    return resultado


def _alinear_candidato(base: pd.DataFrame, candidato: pd.DataFrame) -> pd.DataFrame:
    columnas = CLAVE + ["p50_kg", "estado_candidate"]
    alineado = base.merge(
        candidato[columnas].rename(columns={"p50_kg": "candidate_kg"}),
        on=CLAVE,
        how="left",
        validate="one_to_one",
    )
    if alineado.candidate_kg.isna().any():
        raise ValueError("El candidato no cubre todas las claves de Macro")
    alineado["macro_kg"] = alineado.p50_kg
    return alineado


def _score_desarrollo(metricas: dict[str, Any]) -> float:
    """Prioriza h1 y evita que cinco horizontes oculten el corto plazo."""

    h1 = metricas["h1"]["empresa_semana"]["wape"]
    h2 = metricas["h2_h6"]["empresa_semana"]["wape"]
    fundo = metricas["h1_h6"]["fundo_semana"]["wape"]
    return float(0.45 * h1 + 0.30 * h2 + 0.25 * fundo)


def seleccionar_configuracion(
    base: pd.DataFrame,
    candidatos: list[tuple[ConfiguracionTurnoTemporal, pd.DataFrame]],
) -> tuple[ConfiguracionTurnoTemporal, pd.DataFrame, list[dict[str, Any]]]:
    """Selecciona solo con S13-S30 y nunca consulta R09."""

    desarrollo_base = base[base.split.eq("desarrollo_s13_s30")].copy()
    filas: list[dict[str, Any]] = []
    mejor: tuple[float, float, float, ConfiguracionTurnoTemporal, pd.DataFrame] | None = None
    for config, candidato in candidatos:
        alineado = _alinear_candidato(base, candidato)
        desarrollo = alineado[alineado.split.eq("desarrollo_s13_s30")].copy()
        metricas = _metricas_bandas(desarrollo, "candidate_kg")
        score = _score_desarrollo(metricas)
        fila = {
            "configuracion": asdict(config),
            "score": score,
            "metricas": metricas,
            "semanas_ganadas_empresa_vs_macro": _semanas_ganadas(
                desarrollo, "candidate_kg", "macro_kg"
            ),
        }
        filas.append(fila)
        clave = (
            score,
            abs(metricas["h1_h6"]["empresa_semana"]["sesgo"]),
            config.peso_calendario,
            config,
            alineado,
        )
        if mejor is None or clave[:3] < mejor[:3]:
            mejor = clave
    if mejor is None or desarrollo_base.empty:
        raise ValueError("No existe desarrollo S13-S30 para seleccionar")
    return mejor[3], mejor[4], filas


def _cobertura_r09(tabla: pd.DataFrame) -> dict[str, float | int]:
    disponible = tabla.r09_kg.notna()
    denominador = float(tabla.real_kg.abs().sum())
    return {
        "filas_disponibles": int(disponible.sum()),
        "filas_totales": int(len(tabla)),
        "cobertura_filas": float(disponible.mean()) if len(tabla) else 0.0,
        "cobertura_volumen": (
            float(tabla.loc[disponible, "real_kg"].abs().sum() / denominador)
            if denominador
            else 0.0
        ),
    }


def _cobertura_r09_bandas(tabla: pd.DataFrame) -> dict[str, Any]:
    return {
        banda: _cobertura_r09(_banda_horizonte(tabla, banda))
        for banda in ("h1", "h2_h6", "h1_h6")
    }


def comparar_r09_despues(
    seleccionado: pd.DataFrame,
    r09: pd.DataFrame,
) -> dict[str, Any]:
    """Compara R09 solo tras seleccionar, sobre el mismo subconjunto emitido."""

    tabla = seleccionado.merge(r09, on=CLAVE, how="left", validate="one_to_one")
    tabla = tabla[tabla.split.ne("fuera_evaluacion")].copy()
    coincidencias = tabla.r09_kg.notna()
    if tabla.loc[coincidencias, "real_r09_kg"].notna().any():
        validos = coincidencias & tabla.real_r09_kg.notna()
        if not np.allclose(tabla.loc[validos, "real_kg"], tabla.loc[validos, "real_r09_kg"]):
            raise ValueError("R09 y Macro no conservan el mismo real en claves pareadas")
    condicionada = tabla[coincidencias].copy()
    resultado: dict[str, Any] = {
        "cobertura": _cobertura_r09_bandas(tabla),
        "nota": (
            "R09 se evalua solo en claves emitidas. Candidate y R09 usan exactamente "
            "esas mismas claves y el mismo denominador real."
        ),
    }
    for split in ("desarrollo_s13_s30", "holdout_s31_s33"):
        universo_split = tabla[tabla.split.eq(split)].copy()
        bloque = condicionada[condicionada.split.eq(split)].copy()
        resultado[split] = {
            "cobertura": _cobertura_r09_bandas(universo_split),
            "candidate_pareado": _metricas_bandas(bloque, "candidate_kg"),
            "r09_condicionado": _metricas_bandas(bloque, "r09_kg"),
            "semanas_ganadas_empresa_candidate_vs_r09": _semanas_ganadas(
                bloque, "candidate_kg", "r09_kg"
            ),
            "semanas_ganadas_fundo_candidate_vs_r09": _semanas_ganadas(
                bloque, "candidate_kg", "r09_kg", por_fundo=True
            ),
        }
    holdout = resultado["holdout_s31_s33"]
    cand = holdout["candidate_pareado"]
    ref = holdout["r09_condicionado"]
    condiciones = {
        "empresa_h1": cand["h1"]["empresa_semana"]["wape"]
        < ref["h1"]["empresa_semana"]["wape"],
        "empresa_h2_h6": cand["h2_h6"]["empresa_semana"]["wape"]
        < ref["h2_h6"]["empresa_semana"]["wape"],
        "fundo_h1_h6": cand["h1_h6"]["fundo_semana"]["wape"]
        < ref["h1_h6"]["fundo_semana"]["wape"],
    }
    resultado["veredicto_holdout"] = {
        "supera_r09_condicionado": bool(all(condiciones.values())),
        "condiciones": condiciones,
        "advertencia_cobertura": (
            holdout["cobertura"]["h1_h6"]["cobertura_volumen"] < 0.90
        ),
    }
    return resultado


def _hash_claves(tabla: pd.DataFrame) -> str:
    llaves = tabla[CLAVE].sort_values(CLAVE, kind="stable").astype(str)
    serializado = llaves.agg("|".join, axis=1).str.cat(sep="\n")
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()

"""Predicción candidate-only del scheduler de lotes activos."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .active_lot_scheduler_contratos import ConfiguracionScheduler
from .active_lot_scheduler_fuentes import _normalizar_fechas


def _actividad(tabla: pd.DataFrame, config: ConfiguracionScheduler) -> pd.Series:
    neutral = 0.50
    lote = np.exp(-0.5 * np.square(tabla.distancia_lote_dias / config.sigma_dias))
    turno = np.exp(-0.5 * np.square(tabla.distancia_turno_dias / config.sigma_dias))
    lote = pd.Series(lote, index=tabla.index).where(tabla.distancia_lote_dias.notna(), neutral)
    turno = pd.Series(turno, index=tabla.index).where(tabla.distancia_turno_dias.notna(), neutral)
    combinada = config.peso_lote * lote + (1.0 - config.peso_lote) * turno
    return config.piso_actividad + (1.0 - config.piso_actividad) * combinada.clip(0.0, 1.0)


def _escala_online(
    historial: list[dict[str, Any]],
    actividad_objetivo: float,
    emision: pd.Timestamp,
    config: ConfiguracionScheduler,
) -> float:
    if config.fuerza_escala <= 0 or not historial:
        return 1.0
    elegibles = [r for r in historial if pd.Timestamp(r["semana_fin"]) < emision]
    if not elegibles:
        return 1.0
    orden = sorted(
        elegibles,
        key=lambda r: (
            abs(float(r["actividad"]) - actividad_objetivo),
            -pd.Timestamp(r["fecha_objetivo"]).value,
        ),
    )[: config.lookback_escala]
    residuos = [float(r["residuo_log"]) for r in orden if np.isfinite(r["residuo_log"])]
    if not residuos:
        return 1.0
    peso = len(residuos) / (len(residuos) + config.shrink_escala)
    correccion = config.fuerza_escala * peso * float(np.median(residuos))
    return float(np.clip(np.exp(correccion), config.escala_minima, config.escala_maxima))


def predecir_scheduler(
    contexto: pd.DataFrame,
    reales_lote_semana: pd.DataFrame,
    config: ConfiguracionScheduler,
) -> pd.DataFrame:
    """Predice secuencialmente; el real solo entra tras cerrar una semana previa."""

    verdad = _normalizar_fechas(reales_lote_semana, ("fecha_objetivo",))
    claves = ["campania", "fecha_objetivo", "lote_id"]
    verdad = verdad.groupby(claves, as_index=False).real_kg.sum()
    # La evaluacion se limita a semanas que tuvieron una emision Macro h1. Se
    # conservan lotes reales ausentes de Macro dentro de esas semanas para
    # penalizar cobertura, pero no se incorporan semanas fuera del contrato.
    semanas_con_emision = contexto[["campania", "fecha_objetivo"]].drop_duplicates()
    verdad = verdad.merge(
        semanas_con_emision,
        on=["campania", "fecha_objetivo"],
        how="inner",
        validate="many_to_one",
    )
    salida: list[pd.DataFrame] = []
    historial_fundo: dict[tuple[str, str], list[dict[str, Any]]] = {}
    grupos = contexto.groupby(["campania", "fecha_emision", "fecha_objetivo", "fundo"], sort=True)
    for (campania, emision, objetivo, fundo), bloque in grupos:
        bloque = bloque.copy()
        bloque["actividad"] = _actividad(bloque, config)
        reciente = pd.to_numeric(bloque.kg_reciente_asof, errors="coerce")
        reemplazo = float(reciente.dropna().median()) if reciente.notna().any() else 1.0
        reciente = reciente.fillna(reemplazo).clip(lower=1e-6)
        masa = bloque.actividad * reciente
        total_macro = float(bloque.macro_kg.sum())
        if total_macro > 0:
            peso_macro = bloque.macro_kg / total_macro
            peso_activo = masa / float(masa.sum()) if float(masa.sum()) > 0 else peso_macro
            actividad_indice = float(np.average(bloque.actividad, weights=reciente))
            escala = _escala_online(
                historial_fundo.get((str(campania), str(fundo)), []),
                actividad_indice,
                pd.Timestamp(emision),
                config,
            )
            pesos = (
                1.0 - config.mezcla_actividad
            ) * peso_macro + config.mezcla_actividad * peso_activo
            bloque["candidate_kg"] = total_macro * escala * pesos
        else:
            actividad_indice = float(bloque.actividad.mean()) if len(bloque) else 0.0
            escala = 1.0
            bloque["candidate_kg"] = 0.0
        bloque["factor_escala"] = escala
        bloque["configuracion_id"] = config.id
        salida.append(bloque)

        real_semana = verdad.loc[verdad.campania.eq(campania) & verdad.fecha_objetivo.eq(objetivo)]
        real_total = float(
            real_semana.loc[real_semana.lote_id.isin(bloque.lote_id), "real_kg"].sum()
        )
        if total_macro > 0:
            historial_fundo.setdefault((str(campania), str(fundo)), []).append(
                {
                    "fecha_objetivo": objetivo,
                    "semana_fin": pd.Timestamp(objetivo) + pd.Timedelta(days=6),
                    "actividad": actividad_indice,
                    "residuo_log": float(np.log1p(real_total) - np.log1p(total_macro)),
                }
            )
    pred = pd.concat(salida, ignore_index=True)
    evaluada = pred.merge(verdad, on=claves, how="outer", validate="one_to_one")
    mapa = pred.sort_values("fecha_objetivo").drop_duplicates(["campania", "lote_id"], keep="last")[
        ["campania", "lote_id", "fundo", "modulo"]
    ]
    evaluada = evaluada.merge(
        mapa,
        on=["campania", "lote_id"],
        how="left",
        suffixes=("", "_mapa"),
        validate="many_to_one",
    )
    evaluada["fundo"] = evaluada.fundo.fillna(evaluada.fundo_mapa)
    evaluada["modulo"] = evaluada.modulo.fillna(evaluada.modulo_mapa)
    evaluada.drop(columns=["fundo_mapa", "modulo_mapa"], errors="ignore", inplace=True)
    evaluada["emitio_macro"] = evaluada.macro_kg.notna()
    evaluada["emitio_candidate"] = evaluada.configuracion_id.notna()
    evaluada["macro_kg"] = evaluada.macro_kg.fillna(0.0)
    evaluada["candidate_kg"] = evaluada.candidate_kg.fillna(0.0)
    evaluada["real_kg"] = evaluada.real_kg.fillna(0.0)
    evaluada["falso_cero_candidate"] = evaluada.real_kg.gt(0) & evaluada.candidate_kg.le(1e-9)
    evaluada["falso_cero_macro"] = evaluada.real_kg.gt(0) & evaluada.macro_kg.le(1e-9)
    return evaluada


def construir_verdad(h01: pd.DataFrame) -> pd.DataFrame:
    base = _normalizar_fechas(h01, ("fecha",))
    base["fecha_objetivo"] = base.fecha - pd.to_timedelta(base.fecha.dt.weekday, unit="D")
    return (
        base.groupby(["campania", "fecha_objetivo", "lote_id"], as_index=False)
        .kg.sum()
        .rename(columns={"kg": "real_kg"})
    )

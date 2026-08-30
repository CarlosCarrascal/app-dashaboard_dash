"""Nowcast separado para la semana en curso del candidato temporal."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .turno_temporal_contratos import _semana_inicio


def construir_nowcast_separado(
    forecast_semana: pd.DataFrame,
    cosecha_diaria: pd.DataFrame,
    *,
    fecha_emision: str | pd.Timestamp,
) -> pd.DataFrame:
    """Estima el cierre de la semana actual sin contaminar el forecast futuro."""

    if forecast_semana.empty:
        return pd.DataFrame()
    f = forecast_semana.copy()
    requeridas = {"campania", "fecha_objetivo", "p50_kg"}
    faltantes = sorted(requeridas.difference(f.columns))
    if faltantes:
        raise ValueError(f"Faltan columnas del prior semanal: {faltantes}")
    emision = pd.Timestamp(fecha_emision).normalize()
    f["fecha_objetivo"] = pd.to_datetime(f.fecha_objetivo, errors="raise").dt.normalize()
    semana = _semana_inicio(emision)
    if f.fecha_objetivo.nunique() != 1 or pd.Timestamp(f.fecha_objetivo.iloc[0]) != semana:
        raise ValueError("El nowcast solo acepta la semana que contiene la emisión")

    requeridas_real = {"campania", "fecha", "kg"}
    faltantes_real = sorted(requeridas_real.difference(cosecha_diaria.columns))
    if faltantes_real:
        raise ValueError(f"Faltan columnas para nowcast: {faltantes_real}")
    h = cosecha_diaria.copy()
    h["fecha"] = pd.to_datetime(h.fecha, errors="raise").dt.normalize()
    h["kg"] = pd.to_numeric(h.kg, errors="coerce").fillna(0.0).clip(lower=0.0)
    if "fecha_disponible" in h:
        h["fecha_disponible"] = pd.to_datetime(h.fecha_disponible, errors="coerce").dt.normalize()
        h = h[h.fecha_disponible.le(emision)]
    h = h[h.campania.astype(str).eq(str(f.campania.iloc[0]))].copy()
    h["semana_inicio"] = _semana_inicio(h.fecha)
    h["dia_semana"] = h.fecha.dt.weekday
    cerradas = h[h.semana_inicio.add(pd.to_timedelta(6, unit="D")).lt(semana)].copy()
    hasta_dia = int(emision.weekday())
    perfiles: list[float] = []
    for _, bloque in cerradas.groupby("semana_inicio"):
        total = float(bloque.kg.sum())
        if total > 0:
            perfiles.append(float(bloque.loc[bloque.dia_semana.le(hasta_dia), "kg"].sum() / total))
    avance_esperado = float(np.median(perfiles)) if perfiles else np.nan
    parcial = float(h.loc[h.semana_inicio.eq(semana) & h.fecha.le(emision), "kg"].sum())
    prior = float(pd.to_numeric(f.p50_kg, errors="coerce").fillna(0.0).sum())
    if np.isfinite(avance_esperado) and avance_esperado > 0:
        ritmo = parcial / avance_esperado
        peso_ritmo = min(max(avance_esperado, 0.15), 0.85)
        nowcast = max(parcial, peso_ritmo * ritmo + (1 - peso_ritmo) * prior)
        estado = "ritmo_intrasemanal"
    else:
        nowcast = max(parcial, prior)
        estado = "sin_perfil_historico"
    return pd.DataFrame(
        [
            {
                "campania": str(f.campania.iloc[0]),
                "fecha_emision": emision,
                "fecha_objetivo": semana,
                "modelo": "CandidateNowcastTurno_v1",
                "version_modelo": "candidate_only_no_persistir_v1",
                "tipo_prediccion": "nowcast",
                "incluye_en_metricas_forecast": False,
                "p50_kg": float(nowcast),
                "kg_parcial_asof": parcial,
                "kg_prior_forecast": prior,
                "avance_esperado": avance_esperado,
                "estado_candidate": estado,
            }
        ]
    )


__all__ = ["construir_nowcast_separado"]

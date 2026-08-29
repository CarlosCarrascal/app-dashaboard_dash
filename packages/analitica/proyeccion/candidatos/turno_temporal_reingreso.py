"""Estimación y aplicación del calendario de reingreso candidate-only."""

from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd

from ..motor_proyeccion_semanal import ajustar_dia_habil
from .turno_temporal_contratos import ConfiguracionTurnoTemporal, _semana_inicio
from .turno_temporal_validacion import normalizar_forecast_candidate


def estimar_desplazamiento_temporal_asof(
    historial: pd.DataFrame,
    *,
    fecha_emision: str | pd.Timestamp,
    config: ConfiguracionTurnoTemporal | None = None,
    grupo: str = "fundo",
) -> dict[str, int]:
    """Elige un shift entero con semanas cerradas antes de la emisión.

    ``pred_base_kg`` se desplaza dentro de cada grupo y se compara con ``real_kg``.
    La penalización favorece cero cuando la mejora es marginal.
    """

    config = config or ConfiguracionTurnoTemporal()
    requeridas = {grupo, "fecha_objetivo", "pred_base_kg", "real_kg"}
    faltantes = sorted(requeridas.difference(historial.columns))
    if faltantes:
        raise ValueError(f"Faltan columnas para ajuste temporal: {faltantes}")
    h = historial.copy()
    h["fecha_objetivo"] = pd.to_datetime(h.fecha_objetivo, errors="raise").dt.normalize()
    h["semana_inicio"] = _semana_inicio(h.fecha_objetivo)
    h["semana_fin"] = h.semana_inicio + pd.to_timedelta(6, unit="D")
    emision = pd.Timestamp(fecha_emision).normalize()
    h = h[h.semana_fin.lt(emision) & h.real_kg.notna() & h.pred_base_kg.notna()].copy()
    if "fecha_disponible" in h:
        disponible = pd.to_datetime(h.fecha_disponible, errors="coerce").dt.normalize()
        h = h[disponible.le(emision)].copy()

    resultados: dict[str, int] = {}
    for nombre, bloque in h.groupby(grupo, dropna=False):
        semanal = (
            bloque.groupby("semana_inicio", as_index=True)
            .agg(real_kg=("real_kg", "sum"), pred_kg=("pred_base_kg", "sum"))
            .sort_index()
        )
        if len(semanal) < config.semanas_minimas_desplazamiento:
            resultados[str(nombre)] = 0
            continue
        indice = pd.date_range(semanal.index.min(), semanal.index.max(), freq="7D")
        semanal = semanal.reindex(indice, fill_value=0.0)
        denom = float(semanal.real_kg.abs().sum())
        scores: list[tuple[float, int]] = []
        for shift in range(
            -config.desplazamiento_max_semanas,
            config.desplazamiento_max_semanas + 1,
        ):
            pred = semanal.pred_kg.shift(shift, fill_value=0.0)
            wape = float((pred - semanal.real_kg).abs().sum() / denom) if denom else np.inf
            score = wape + config.penalizacion_desplazamiento * abs(shift)
            scores.append((score, shift))
        resultados[str(nombre)] = min(scores, key=lambda valor: (valor[0], abs(valor[1])))[1]
    return resultados


def aplicar_turno_reingreso_candidate(
    curva_base: pd.DataFrame,
    cosecha_diaria: pd.DataFrame,
    *,
    desplazamientos: dict[str, int] | None = None,
    config: ConfiguracionTurnoTemporal | None = None,
) -> pd.DataFrame:
    """Redistribuye la curva sin cambiar los kg totales por emisión y lote."""

    config = config or ConfiguracionTurnoTemporal()
    base = normalizar_forecast_candidate(curva_base)
    requeridas_base = {"turno", "dias_reingreso"}
    faltantes = sorted(requeridas_base.difference(base.columns))
    if faltantes:
        raise ValueError(f"Faltan datos operativos del calendario: {faltantes}")
    requeridas_real = {"campania", "lote_id", "fecha", "kg"}
    faltantes_real = sorted(requeridas_real.difference(cosecha_diaria.columns))
    if faltantes_real:
        raise ValueError(f"Faltan columnas de cosecha diaria: {faltantes_real}")

    real = cosecha_diaria.copy()
    real["fecha"] = pd.to_datetime(real.fecha, errors="raise").dt.normalize()
    real["kg"] = pd.to_numeric(real.kg, errors="coerce").fillna(0.0).clip(lower=0.0)
    if "fecha_disponible" in real:
        real["fecha_disponible"] = pd.to_datetime(
            real.fecha_disponible, errors="coerce"
        ).dt.normalize()
    desplazamientos = desplazamientos or {}
    salidas: list[pd.DataFrame] = []
    grupos = [
        "evaluation_contract_id",
        "campania",
        "modelo",
        "fecha_emision",
        "lote_id",
    ]
    for clave, bloque in base.groupby(grupos, sort=False, dropna=False):
        bloque = bloque.sort_values("fecha_objetivo").copy()
        horizontes = bloque.horizonte_semanas.tolist()
        if horizontes != list(range(min(horizontes), max(horizontes) + 1)):
            raise ValueError("La redistribución exige horizontes semanales contiguos")
        _, campania, _, emision, lote_id = clave
        historia = real[
            real.campania.astype(str).eq(str(campania))
            & real.lote_id.astype(str).eq(str(lote_id))
            & real.fecha.lt(pd.Timestamp(emision))
            & real.kg.gt(0)
        ].copy()
        if "fecha_disponible" in historia:
            historia = historia[historia.fecha_disponible.lt(pd.Timestamp(emision))]
        dias = pd.to_numeric(bloque.dias_reingreso, errors="coerce").dropna()
        estado = "sin_historia_asof"
        fecha_reingreso = pd.NaT
        if not historia.empty and not dias.empty and int(dias.iloc[0]) > 0:
            ultima = historia.fecha.max().date()
            fecha_reingreso = pd.Timestamp(
            ajustar_dia_habil(ultima + pd.to_timedelta(int(dias.iloc[0]), unit="D"))
            )
            grupo_desplazamiento = str(bloque["fundo"].iloc[0] if "fundo" in bloque else "global")
            shift = int(desplazamientos.get(grupo_desplazamiento, 0))
            fecha_reingreso += pd.to_timedelta(shift, unit="W")
            objetivo_centro = _semana_inicio(fecha_reingreso)
            distancia = (bloque.fecha_objetivo - objetivo_centro).dt.days.astype(float) / 7.0
            pesos_calendario = np.exp(-0.5 * (distancia / config.dispersion_semanas) ** 2)
            if float(pesos_calendario.sum()) > 0:
                pesos_calendario = pesos_calendario / pesos_calendario.sum()
                total = float(bloque.p50_kg.sum())
                if total > 0:
                    peso_base = bloque.p50_kg.to_numpy(float) / total
                    mezcla = (
                        1 - config.peso_calendario
                    ) * peso_base + config.peso_calendario * pesos_calendario.to_numpy(float)
                    mezcla = mezcla / mezcla.sum()
                    bloque["p50_kg"] = total * mezcla
                    estado = "calendario_reingreso_aplicado"
        bloque["modelo"] = "CandidateTurnoTemporal_v1"
        bloque["version_modelo"] = "candidate_only_no_persistir_v1"
        bloque["tipo_prediccion"] = "forecast"
        bloque["incluye_en_metricas_forecast"] = True
        bloque["fecha_reingreso_asof"] = fecha_reingreso
        bloque["estado_candidate"] = estado
        bloque["configuracion_candidate"] = [asdict(config)] * len(bloque)
        salidas.append(bloque)
    return pd.concat(salidas, ignore_index=True) if salidas else base.iloc[0:0].copy()


__all__ = ["aplicar_turno_reingreso_candidate", "estimar_desplazamiento_temporal_asof"]

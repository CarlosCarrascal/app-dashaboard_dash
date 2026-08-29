"""Aplicación del candidato temporal y auditoría de paridad para run73."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from analitica.proyeccion.candidate_turno_temporal import (
    ConfiguracionTurnoTemporal,
    aplicar_turno_reingreso_candidate,
    normalizar_forecast_candidate,
)

from .turno_reingreso_fuentes import CLAVE, GRUPO_CURVA


def rejilla_configuraciones() -> list[ConfiguracionTurnoTemporal]:
    configuraciones = [
        ConfiguracionTurnoTemporal(
            peso_calendario=0.0,
            dispersion_semanas=0.85,
            desplazamiento_max_semanas=0,
        )
    ]
    configuraciones.extend(
        ConfiguracionTurnoTemporal(
            peso_calendario=peso,
            dispersion_semanas=dispersion,
            desplazamiento_max_semanas=0,
        )
        for peso in (0.20, 0.40, 0.60, 0.80)
        for dispersion in (0.60, 1.00)
    )
    return configuraciones


def aplicar_configuracion(
    curva: pd.DataFrame,
    config: ConfiguracionTurnoTemporal,
) -> pd.DataFrame:
    """Aplica vectorizadamente la ecuacion de la funcion pura ya auditada.

    Invocar la implementacion pura 17.974 veces por configuracion agrega varios
    minutos de overhead de pandas. Aqui se conserva su misma ecuacion y el
    screening certifica paridad numerica sobre una muestra determinista mediante
    :func:`aplicar_turno_reingreso_candidate`.
    """

    candidato = normalizar_forecast_candidate(curva)
    grupos = [
        "evaluation_contract_id",
        "campania",
        "modelo",
        "fecha_emision",
        "lote_id",
    ]
    total = candidato.groupby(grupos, dropna=False).p50_kg.transform("sum")
    reingreso = candidato.fecha_ultima_cosecha_asof + pd.to_timedelta(
        pd.to_numeric(candidato.dias_reingreso, errors="coerce").round(), unit="D"
    )
    reingreso = pd.to_datetime(reingreso, errors="coerce").dt.normalize()
    ajuste = np.select(
        [reingreso.dt.weekday.eq(5), reingreso.dt.weekday.eq(6)],
        [2, 1],
        default=0,
    )
    reingreso = reingreso + pd.to_timedelta(ajuste, unit="D")
    centro = reingreso - pd.to_timedelta(reingreso.dt.weekday, unit="D")
    distancia = (candidato.fecha_objetivo - centro).dt.days.astype(float) / 7.0
    peso_calendario = np.exp(-0.5 * (distancia / config.dispersion_semanas) ** 2)
    peso_calendario = pd.Series(peso_calendario, index=candidato.index)
    suma_calendario = peso_calendario.groupby(
        [candidato[columna] for columna in grupos], dropna=False
    ).transform("sum")
    share_calendario = peso_calendario / suma_calendario.replace(0.0, np.nan)
    share_base = candidato.p50_kg / total.replace(0.0, np.nan)
    mezcla = (1.0 - config.peso_calendario) * share_base + config.peso_calendario * share_calendario
    suma_mezcla = mezcla.groupby(
        [candidato[columna] for columna in grupos], dropna=False
    ).transform("sum")
    mezcla = mezcla / suma_mezcla.replace(0.0, np.nan)
    valido = (
        candidato.fecha_ultima_cosecha_asof.notna()
        & candidato.turno.ne("")
        & candidato.dias_reingreso.notna()
        & total.gt(0)
        & mezcla.notna()
    )
    candidato.loc[valido, "p50_kg"] = total[valido] * mezcla[valido]
    candidato["modelo"] = "CandidateTurnoTemporal_v1"
    candidato["version_modelo"] = "candidate_only_no_persistir_v1"
    candidato["tipo_prediccion"] = "forecast"
    candidato["incluye_en_metricas_forecast"] = True
    candidato["fecha_reingreso_asof"] = reingreso
    candidato["estado_candidate"] = np.where(
        valido, "calendario_reingreso_aplicado", "sin_historia_asof"
    )
    candidato["configuracion_candidate"] = [asdict(config)] * len(candidato)

    base_total = (
        curva.groupby(GRUPO_CURVA, as_index=False)
        .p50_kg.sum()
        .rename(columns={"p50_kg": "base_total"})
    )
    cand_total = (
        candidato.groupby(GRUPO_CURVA, as_index=False)
        .p50_kg.sum()
        .rename(columns={"p50_kg": "cand_total"})
    )
    totales = base_total.merge(cand_total, on=GRUPO_CURVA, validate="one_to_one")
    if not np.allclose(totales.base_total, totales.cand_total, rtol=1e-10, atol=1e-7):
        raise ValueError("El candidato cambio el total h1-h6 de una emision-lote")
    return candidato


def auditar_paridad_funcion_pura(
    curva: pd.DataFrame,
    config: ConfiguracionTurnoTemporal,
    candidato_vectorizado: pd.DataFrame,
) -> dict[str, Any]:
    """Compara el camino rapido con la funcion pura en curvas representativas."""

    disponibles = curva[
        curva.fecha_ultima_cosecha_asof.notna() & curva.turno.ne("") & curva.dias_reingreso.notna()
    ].copy()
    claves = disponibles[GRUPO_CURVA].drop_duplicates().head(16)
    muestra = curva.merge(claves, on=GRUPO_CURVA, how="inner")
    vector = candidato_vectorizado.merge(claves, on=GRUPO_CURVA, how="inner")
    salidas: list[pd.DataFrame] = []
    for _emision, bloque in muestra.groupby("fecha_emision", sort=True):
        historia = bloque[["campania", "lote_id", "fecha_ultima_cosecha_asof"]].drop_duplicates(
            ["campania", "lote_id"]
        )
        historia = historia.rename(columns={"fecha_ultima_cosecha_asof": "fecha"})
        historia["kg"] = 1.0
        salidas.append(
            aplicar_turno_reingreso_candidate(
                bloque,
                historia[["campania", "lote_id", "fecha", "kg"]],
                config=config,
            )
        )
    puro = pd.concat(salidas, ignore_index=True)
    orden = CLAVE
    comparacion = puro[orden + ["p50_kg"]].merge(
        vector[orden + ["p50_kg"]],
        on=orden,
        validate="one_to_one",
        suffixes=("_puro", "_vector"),
    )
    diferencia = (comparacion.p50_kg_puro - comparacion.p50_kg_vector).abs()
    return {
        "filas": int(len(comparacion)),
        "curvas": int(len(claves)),
        "cambio_max_abs_kg": float(diferencia.max()) if len(diferencia) else np.nan,
        "paridad": bool(
            np.allclose(
                comparacion.p50_kg_puro,
                comparacion.p50_kg_vector,
                rtol=1e-10,
                atol=1e-8,
            )
        ),
    }

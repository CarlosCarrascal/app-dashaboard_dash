"""Lectura de fuentes y derivación temporal as-of del scheduler."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd
import psycopg

from analitica.aplicacion.servicios.cross_campaign import normalizar_fundo
from analitica.settings import postgres_dsn

from .active_lot_scheduler_contratos import CAMPANIAS, RUN_ID


def _normalizar_fechas(tabla: pd.DataFrame, columnas: Iterable[str]) -> pd.DataFrame:
    salida = tabla.copy()
    for columna in columnas:
        salida[columna] = pd.to_datetime(salida[columna], errors="raise").dt.normalize()
    return salida


def leer_fuentes(run_id: int = RUN_ID) -> tuple[pd.DataFrame, pd.DataFrame]:
    consulta_macro = """
        SELECT campania, fecha_emision, fecha_objetivo, lote_id, fundo, modulo,
               SUM(p50_kg) AS macro_kg
        FROM analytics.prediction
        WHERE run_id=%s AND modelo='MacroLegacy_v1'
          AND horizonte_semanas=1 AND campania = ANY(%s)
          AND fecha_emision < fecha_objetivo
        GROUP BY campania, fecha_emision, fecha_objetivo, lote_id, fundo, modulo
        ORDER BY campania, fecha_objetivo, lote_id
    """
    consulta_h01 = """
        SELECT campania, lote_id, fecha, turno, SUM(kg) AS kg
        FROM stg.h01_cosecha
        WHERE campania = ANY(%s)
        GROUP BY campania, lote_id, fecha, turno
        ORDER BY campania, lote_id, fecha
    """
    with psycopg.connect(postgres_dsn()) as conexion:
        macro = pd.read_sql_query(consulta_macro, conexion, params=[run_id, list(CAMPANIAS)])
        h01 = pd.read_sql_query(consulta_h01, conexion, params=[list(CAMPANIAS)])
    if macro.empty or h01.empty:
        raise RuntimeError("No se pudo leer Macro h1 o H01")
    macro = _normalizar_fechas(macro, ("fecha_emision", "fecha_objetivo"))
    h01 = _normalizar_fechas(h01, ("fecha",))
    macro["fundo"] = macro.fundo.map(normalizar_fundo)
    macro["macro_kg"] = pd.to_numeric(macro.macro_kg, errors="raise").clip(lower=0.0)
    h01["kg"] = pd.to_numeric(h01.kg, errors="coerce").fillna(0.0)
    h01["turno"] = h01.turno.fillna("").astype(str).str.strip()
    if macro.duplicated(["campania", "fecha_emision", "fecha_objetivo", "lote_id"]).any():
        raise ValueError("Macro contiene claves lote-emision-objetivo duplicadas")
    return macro, h01


def _intervalo_mediano(fechas: pd.Series, ventana: int = 6) -> float:
    unicas = fechas.drop_duplicates().sort_values()
    dias = unicas.diff().dt.days.dropna()
    validos = dias[dias.between(5, 21)].tail(ventana)
    return float(validos.median()) if len(validos) else math.nan


def _distancia_periodica(
    ultima: pd.Timestamp | pd.NaT,
    intervalo: float,
    centro_objetivo: pd.Timestamp,
) -> float:
    if pd.isna(ultima) or not np.isfinite(intervalo) or intervalo <= 0:
        return math.nan
    transcurridos = float((centro_objetivo - pd.Timestamp(ultima)).days)
    if transcurridos <= 0:
        return abs(transcurridos)
    ciclo = max(1, int(round(transcurridos / intervalo)))
    regreso = pd.Timestamp(ultima) + pd.Timedelta(days=ciclo * intervalo)
    return float(abs((regreso - centro_objetivo).days))


def derivar_contexto_asof(macro: pd.DataFrame, h01: pd.DataFrame) -> pd.DataFrame:
    """Deriva actividad lote/Turno sin consultar H01 en o despues de la emision."""

    macro = _normalizar_fechas(macro, ("fecha_emision", "fecha_objetivo"))
    historia = _normalizar_fechas(h01, ("fecha",))
    historia = historia.loc[pd.to_numeric(historia.kg, errors="coerce").fillna(0).gt(0)].copy()
    historia["turno"] = historia.turno.fillna("").astype(str).str.strip()
    mapa_lote = macro.sort_values("fecha_objetivo").drop_duplicates(
        ["campania", "lote_id"], keep="last"
    )[["campania", "lote_id", "fundo", "modulo"]]
    historia = historia.merge(
        mapa_lote, on=["campania", "lote_id"], how="left", validate="many_to_one"
    )

    salidas: list[pd.DataFrame] = []
    grupos = macro.groupby(["campania", "fecha_emision", "fecha_objetivo", "fundo"], sort=True)
    for (campania, emision, objetivo, fundo), bloque_macro in grupos:
        previo_fundo = historia.loc[
            historia.campania.eq(campania) & historia.fundo.eq(fundo) & historia.fecha.lt(emision)
        ].copy()
        lotes_previos = previo_fundo[["lote_id", "modulo"]].drop_duplicates("lote_id")
        universo = bloque_macro.merge(
            lotes_previos,
            on="lote_id",
            how="outer",
            suffixes=("", "_hist"),
            validate="one_to_one",
        )
        universo["campania"] = campania
        universo["fecha_emision"] = emision
        universo["fecha_objetivo"] = objetivo
        universo["fundo"] = fundo
        universo["modulo"] = universo.modulo.fillna(universo.get("modulo_hist"))
        universo["macro_kg"] = pd.to_numeric(universo.macro_kg, errors="coerce").fillna(0.0)
        centro = pd.Timestamp(objetivo) + pd.Timedelta(days=3)

        intervalos_turno: dict[str, float] = {}
        ultima_turno: dict[str, pd.Timestamp] = {}
        for turno, bloque_turno in previo_fundo.loc[previo_fundo.turno.ne("")].groupby(
            "turno", sort=False
        ):
            fechas_turno = bloque_turno.fecha.drop_duplicates().sort_values()
            intervalos_turno[str(turno)] = _intervalo_mediano(fechas_turno)
            ultima_turno[str(turno)] = pd.Timestamp(fechas_turno.max())
        intervalo_fundo = _intervalo_mediano(previo_fundo.fecha)
        if not np.isfinite(intervalo_fundo):
            intervalo_fundo = 13.0

        registros: list[dict[str, Any]] = []
        por_lote = {int(k): v for k, v in previo_fundo.groupby("lote_id", sort=False)}
        for fila in universo.itertuples(index=False):
            lote_id = int(fila.lote_id)
            hist = por_lote.get(lote_id)
            if hist is None or hist.empty:
                registros.append(
                    {
                        "lote_id": lote_id,
                        "turno_asof": "",
                        "ultima_cosecha_asof": pd.NaT,
                        "dias_reingreso_asof": intervalo_fundo,
                        "n_cosechas_asof": 0,
                        "kg_reciente_asof": math.nan,
                        "distancia_lote_dias": math.nan,
                        "distancia_turno_dias": math.nan,
                    }
                )
                continue
            diario = hist.groupby("fecha", as_index=False).kg.sum().sort_values("fecha")
            fechas = diario.fecha
            turno_valido = hist.loc[hist.turno.ne(""), "turno"]
            turno = str(turno_valido.iloc[-1]) if len(turno_valido) else ""
            intervalo_lote = _intervalo_mediano(fechas)
            if not np.isfinite(intervalo_lote):
                intervalo_lote = intervalos_turno.get(turno, math.nan)
            if not np.isfinite(intervalo_lote):
                intervalo_lote = intervalo_fundo
            ultima = pd.Timestamp(fechas.max())
            distancia_lote = _distancia_periodica(ultima, intervalo_lote, centro)
            distancia_turno = _distancia_periodica(
                ultima_turno.get(turno, pd.NaT),
                intervalos_turno.get(turno, intervalo_fundo),
                centro,
            )
            registros.append(
                {
                    "lote_id": lote_id,
                    "turno_asof": turno,
                    "ultima_cosecha_asof": ultima,
                    "dias_reingreso_asof": float(intervalo_lote),
                    "n_cosechas_asof": int(len(fechas)),
                    "kg_reciente_asof": float(diario.kg.tail(3).median()),
                    "distancia_lote_dias": distancia_lote,
                    "distancia_turno_dias": distancia_turno,
                }
            )
        contexto = universo.merge(
            pd.DataFrame(registros), on="lote_id", how="left", validate="one_to_one"
        )
        contexto.drop(columns=["modulo_hist"], errors="ignore", inplace=True)
        salidas.append(contexto)
    salida = pd.concat(salidas, ignore_index=True)
    salida["semana_fin"] = salida.fecha_objetivo + pd.Timedelta(days=6)
    salida["semana_iso"] = salida.fecha_objetivo.dt.isocalendar().week.astype(int)
    return salida

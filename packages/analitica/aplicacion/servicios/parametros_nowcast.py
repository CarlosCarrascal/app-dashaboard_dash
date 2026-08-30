"""Lecturas compartidas por los screenings nowcast, experto y temporal.

Este módulo contiene únicamente adaptadores de entrada. No importa módulos
ejecutables de ``analitica.interfaces.scripts``; los scripts que necesitan estas lecturas
las reciben desde aquí conservando sus nombres públicos históricos.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

from analitica.aplicacion.servicios.parametros_replay import (
    ACCESS_DEFAULT,
    ROOT_DEFAULT,
    TRANSITIONS_DEFAULT,
    columna_campania,
)
from analitica.settings import postgres_dsn

MAPEO_FUNDO = {
    "aqu anqa 1": "Arena",
    "aqu anqa 2": "Quri",
    "aqu anqa 3": "Kawsay",
    "aqu anqa 4": "Ayllu",
    "aqu anqa 5": "Kawsay",
}


def normalizar_fundo(valor: object) -> str:
    texto = str(valor or "").strip()
    return MAPEO_FUNDO.get(texto.casefold(), texto)


def leer_macro_h1(campania: str = "C2026", run_id: int = 76) -> pd.DataFrame:
    consulta = """
        SELECT campania, fecha_emision, fecha_objetivo, fundo,
               SUM(p50_kg) AS macro_kg, SUM(real_kg) AS real_pg_kg
        FROM analytics.prediction
        WHERE run_id=%s AND campania=%s AND modelo='MacroLegacy_v1'
          AND horizonte_semanas=1 AND fecha_emision < fecha_objetivo
        GROUP BY campania, fecha_emision, fecha_objetivo, fundo
    """
    with psycopg.connect(postgres_dsn()) as conexion:
        tabla = pd.read_sql_query(consulta, conexion, params=[run_id, campania])
    tabla["fecha_emision"] = pd.to_datetime(tabla.fecha_emision).dt.normalize()
    tabla["fecha_objetivo"] = pd.to_datetime(tabla.fecha_objetivo).dt.normalize()
    tabla["semana_emision"] = tabla.fecha_emision.dt.isocalendar().week.astype(int)
    tabla["semana_objetivo"] = tabla.fecha_objetivo.dt.isocalendar().week.astype(int)
    tabla["fundo_operativo"] = tabla.fundo.map(normalizar_fundo)
    return tabla.groupby(
        [
            "campania",
            "fecha_emision",
            "fecha_objetivo",
            "semana_emision",
            "semana_objetivo",
            "fundo_operativo",
        ],
        as_index=False,
    ).agg(macro_kg=("macro_kg", "sum"), real_pg_kg=("real_pg_kg", "sum"))


def leer_reales_r09_fundo(
    access: Path, campania: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError(
            "Este comando necesita pyodbc y el controlador ODBC de Microsoft Access."
        ) from exc
    cadena = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + str(access)
    with pyodbc.connect(cadena) as conexion:
        cursor = conexion.cursor()
        camp_h01 = columna_campania(cursor, "H01_ProdHistorica")
        camp_r09 = columna_campania(cursor, "R09_Forecast_Semanal")
        r09 = pd.read_sql(
            "SELECT [Fundo], [Version], [Sem], Sum([Kg]) AS total_kg "
            "FROM [R09_Forecast_Semanal] "
            f"WHERE [{camp_r09}] = ? GROUP BY [Fundo], [Version], [Sem]",
            conexion,
            params=[campania],
        )
    # M01-M04 de Aqu Anqa y M01-M05 de Aqu Anqa II colisionan si se ignora
    # el fundo físico; ambos campos son parte de la clave operativa.
    with pyodbc.connect(cadena) as conexion:
        reales = pd.read_sql(
            "SELECT [Fundo], [Modulo], [Semana], Sum([KG]) AS total_kg "
            "FROM [H01_ProdHistorica] "
            f"WHERE [{camp_h01}] = ? GROUP BY [Fundo], [Modulo], [Semana]",
            conexion,
            params=[campania],
        )
    reales.columns = ["fundo_fisico", "modulo", "semana_objetivo", "real_kg"]
    modulo = reales.modulo.astype(str).str.extract(r"(\d+)", expand=False).astype(float)
    fisico = reales.fundo_fisico.astype(str).str.casefold()
    reales["fundo_operativo"] = np.select(
        [
            fisico.eq("aqu anqa") & modulo.between(1, 4),
            fisico.eq("aqu anqa ii") & modulo.between(1, 5),
            fisico.eq("aqu anqa ii") & modulo.between(6, 11),
            fisico.eq("aqu anqa ii") & modulo.between(12, 15),
            fisico.eq("aqu anqa ii") & modulo.between(16, 17),
        ],
        ["Arena", "Quri", "Kawsay", "Ayllu", "Kawsay"],
        default="",
    )
    if reales.fundo_operativo.eq("").any():
        faltantes = reales.loc[
            reales.fundo_operativo.eq(""), ["fundo_fisico", "modulo"]
        ].drop_duplicates()
        raise ValueError(f"H01 contiene fundos/módulos sin mapear: {faltantes.to_dict('records')}")
    reales = reales.groupby(["semana_objetivo", "fundo_operativo"], as_index=False).real_kg.sum()

    r09.columns = ["fundo", "version", "semana_objetivo", "r09_kg"]
    r09["fundo_operativo"] = r09.fundo.map(normalizar_fundo)
    r09["semana_emision"] = r09.version.astype(str).str.upper().str.removeprefix("S")
    r09 = r09[r09.semana_emision.str.isdigit()].copy()
    r09["semana_emision"] = r09.semana_emision.astype(int)
    r09 = r09.groupby(
        ["semana_emision", "semana_objetivo", "fundo_operativo"], as_index=False
    ).r09_kg.sum()
    return reales, r09


__all__ = [
    "ACCESS_DEFAULT",
    "MAPEO_FUNDO",
    "ROOT_DEFAULT",
    "TRANSITIONS_DEFAULT",
    "columna_campania",
    "leer_macro_h1",
    "leer_reales_r09_fundo",
    "normalizar_fundo",
]

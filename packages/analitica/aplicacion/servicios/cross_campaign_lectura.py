"""Lectura y ensamblaje del panel del screening cross-campaign h1."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psycopg

from analitica.settings import postgres_dsn

R09_ACCESS_DEFAULT = Path(r"C:\Users\CCARRASCAL\Downloads\BD_AQUANQA_26_v2.accdb")
CAMPAIGNAS = ("C2024", "C2025", "C2026")
MACRO_RUN_ID = 78
FUNDOS = ("Arena", "Ayllu", "Kawsay", "Quri")
SEMANA_DESARROLLO_C2026 = 30
SEMANAS_HOLDOUT_C2026 = (31, 32, 33)
CIERRE_CERTIFICADO_C2026 = pd.Timestamp("2026-08-16")

REAL_ACCESS_DEFAULT = (
    Path(r"C:\Users\CCARRASCAL\Proyectos\aquanqa-data-platform\.cache")
    / "analitica"
    / "source-snapshots"
    / "BD_AQUANQA_26_snapshot_2026-08-25.accdb"
)


def normalizar_fundo(valor: object) -> str:
    texto = str(valor or "").strip()
    clave = texto.casefold()
    if clave in {"aqu anqa 1", "arena", "arena azul"} or "arena" in clave:
        return "Arena"
    if clave in {"aqu anqa 2", "quri", "quri allpa"} or "quri" in clave:
        return "Quri"
    if clave in {"aqu anqa 3", "aqu anqa 5", "kawsay", "kawsay allpa"} or "kawsay" in clave:
        return "Kawsay"
    if clave in {"aqu anqa 4", "ayllu", "ayllu allpa"} or "ayllu" in clave:
        return "Ayllu"
    return texto


def _conexion_access(ruta: Path):
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError(
            "Este comando necesita pyodbc y el controlador ODBC de Microsoft Access."
        ) from exc
    if not ruta.exists():
        raise FileNotFoundError(ruta)
    cadena = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + str(ruta)
    return pyodbc.connect(cadena, readonly=True)


def _columna_campania(cursor: Any, tabla: str) -> str:
    columnas = [fila.column_name for fila in cursor.columns(table=tabla)]
    candidatas = [columna for columna in columnas if columna.casefold().startswith("campa")]
    if len(candidatas) != 1:
        raise ValueError(f"No se pudo identificar campaña en {tabla}: {columnas}")
    return candidatas[0]


_VERSION_RE = re.compile(r"^S(?P<semana>\d{1,2})(?:_v(?P<variante>\d+))?$", re.I)


def _fecha_emision_r09(fecha_objetivo: pd.Timestamp, semana_version: int) -> pd.Timestamp:
    iso = fecha_objetivo.isocalendar()
    anio_iso = int(iso.year) if semana_version <= int(iso.week) else int(iso.year) - 1
    lunes = date.fromisocalendar(anio_iso, int(semana_version), 1)
    return pd.Timestamp(lunes) + pd.Timedelta(days=2)


def preparar_r09_crudo(tabla: pd.DataFrame) -> pd.DataFrame:
    """Selecciona la última variante numérica emitida antes del lunes objetivo."""

    base = tabla.copy()
    extraida = base.version.astype(str).str.extract(_VERSION_RE)
    base["semana_version"] = pd.to_numeric(extraida.semana, errors="coerce")
    base["rango_variante"] = pd.to_numeric(extraida.variante, errors="coerce").fillna(0)
    base = base.loc[base.semana_version.notna()].copy()
    base["semana_version"] = base.semana_version.astype(int)
    base["fecha_cosecha"] = pd.to_datetime(base.fecha_cosecha).dt.normalize()
    base["fecha_objetivo"] = base.fecha_cosecha - pd.to_timedelta(
        base.fecha_cosecha.dt.weekday, unit="D"
    )
    base["fecha_emision"] = [
        _fecha_emision_r09(objetivo, semana)
        for objetivo, semana in zip(base.fecha_objetivo, base.semana_version, strict=True)
    ]
    base = base.loc[base.fecha_emision.lt(base.fecha_objetivo)].copy()
    base["fundo_operativo"] = base.fundo.map(normalizar_fundo)
    base["r09_kg"] = pd.to_numeric(base.r09_kg, errors="coerce").fillna(0.0)
    agregado = base.groupby(
        [
            "campania",
            "fecha_objetivo",
            "fundo_operativo",
            "fecha_emision",
            "semana_version",
            "rango_variante",
            "version",
        ],
        as_index=False,
    ).r09_kg.sum()
    agregado = agregado.sort_values(
        [
            "campania",
            "fecha_objetivo",
            "fundo_operativo",
            "fecha_emision",
            "rango_variante",
        ],
        kind="stable",
    )
    return agregado.drop_duplicates(
        ["campania", "fecha_objetivo", "fundo_operativo"], keep="last"
    ).reset_index(drop=True)


def leer_r09_access(ruta: Path = R09_ACCESS_DEFAULT) -> pd.DataFrame:
    partes: list[pd.DataFrame] = []
    with _conexion_access(ruta) as conexion:
        cursor = conexion.cursor()
        camp_col = _columna_campania(cursor, "R09_Forecast_Semanal")
        for campania in CAMPAIGNAS:
            consulta = (
                "SELECT [Version], [FCos], [Fundo], [Kg] "
                "FROM [R09_Forecast_Semanal] "
                f"WHERE [{camp_col}] = ?"
            )
            parte = pd.read_sql(consulta, conexion, params=[campania])
            parte.columns = ["version", "fecha_cosecha", "fundo", "r09_kg"]
            parte["campania"] = campania
            partes.append(parte)
    return preparar_r09_crudo(pd.concat(partes, ignore_index=True))


def _mapear_fundo_h01(tabla: pd.DataFrame) -> pd.DataFrame:
    salida = tabla.copy()
    modulo = pd.to_numeric(
        salida.modulo.astype(str).str.extract(r"(\d+)", expand=False), errors="coerce"
    )
    fisico = salida.fundo_fisico.astype(str).str.strip().str.casefold()
    salida["fundo_operativo"] = np.select(
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
    if salida.fundo_operativo.eq("").any():
        ejemplos = salida.loc[salida.fundo_operativo.eq(""), ["fundo_fisico", "modulo"]]
        raise ValueError(
            f"H01 contiene fundo/módulo sin mapeo: {ejemplos.head().to_dict('records')}"
        )
    return salida


def leer_macro_h1(run_id: int = MACRO_RUN_ID) -> pd.DataFrame:
    consulta = """
        SELECT campania, fecha_emision, fecha_objetivo, fundo,
               SUM(p50_kg) AS macro_kg
        FROM analytics.prediction
        WHERE run_id=%s
          AND modelo='MacroLegacy_v1'
          AND horizonte_semanas=1
          AND campania = ANY(%s)
          AND fecha_emision < fecha_objetivo
        GROUP BY campania, fecha_emision, fecha_objetivo, fundo
        ORDER BY campania, fecha_objetivo, fundo
    """
    with psycopg.connect(postgres_dsn()) as conexion, conexion.cursor() as cursor:
        cursor.execute(consulta, (run_id, list(CAMPAIGNAS)))
        columnas = [descripcion.name for descripcion in cursor.description]
        tabla = pd.DataFrame(cursor.fetchall(), columns=columnas)
    if tabla.empty:
        raise RuntimeError(f"run {run_id} no contiene MacroLegacy h1")
    tabla["fecha_emision"] = pd.to_datetime(tabla.fecha_emision).dt.normalize()
    tabla["fecha_objetivo"] = pd.to_datetime(tabla.fecha_objetivo).dt.normalize()
    tabla["fundo_operativo"] = tabla.fundo.map(normalizar_fundo)
    tabla["macro_kg"] = pd.to_numeric(tabla.macro_kg, errors="raise")
    tabla = tabla.groupby(
        ["campania", "fecha_emision", "fecha_objetivo", "fundo_operativo"],
        as_index=False,
    ).macro_kg.sum()
    if tabla.duplicated(["campania", "fecha_objetivo", "fundo_operativo"]).any():
        raise ValueError("Macro h1 mezcla más de una emisión para una semana objetivo")
    if set(tabla.campania.unique()) != set(CAMPAIGNAS):
        raise ValueError(f"Macro no cubre las tres campañas: {sorted(tabla.campania.unique())}")
    return tabla


def leer_reales_access(
    ruta: Path = REAL_ACCESS_DEFAULT,
) -> tuple[pd.DataFrame, dict[str, pd.Timestamp]]:
    partes: list[pd.DataFrame] = []
    maximos: dict[str, pd.Timestamp] = {}
    with _conexion_access(ruta) as conexion:
        cursor = conexion.cursor()
        camp_col = _columna_campania(cursor, "H01_ProdHistorica")
        for campania in CAMPAIGNAS:
            consulta = (
                "SELECT [Fundo], [Modulo], [Fecha], Sum([KG]) AS total_kg "
                "FROM [H01_ProdHistorica] "
                f"WHERE [{camp_col}] = ? GROUP BY [Fundo], [Modulo], [Fecha]"
            )
            tabla = pd.read_sql(consulta, conexion, params=[campania])
            if tabla.empty:
                raise RuntimeError(f"H01 congelada no contiene {campania}")
            tabla.columns = ["fundo_fisico", "modulo", "fecha", "real_kg"]
            tabla["campania"] = campania
            tabla["fecha"] = pd.to_datetime(tabla.fecha).dt.normalize()
            maximos[campania] = pd.Timestamp(tabla.fecha.max()).normalize()
            partes.append(_mapear_fundo_h01(tabla))
    datos = pd.concat(partes, ignore_index=True)
    datos["fecha_objetivo"] = datos.fecha - pd.to_timedelta(datos.fecha.dt.weekday, unit="D")
    semanal = datos.groupby(
        ["campania", "fecha_objetivo", "fundo_operativo"], as_index=False
    ).real_kg.sum()
    return semanal, maximos


def construir_panel(
    macro: pd.DataFrame,
    reales: pd.DataFrame,
    maximos_reales: dict[str, pd.Timestamp],
) -> pd.DataFrame:
    semanas = macro[["campania", "fecha_emision", "fecha_objetivo"]].drop_duplicates()
    rejilla = semanas.merge(pd.DataFrame({"fundo_operativo": FUNDOS}), how="cross")
    panel = rejilla.merge(
        macro,
        on=["campania", "fecha_emision", "fecha_objetivo", "fundo_operativo"],
        how="left",
        validate="one_to_one",
    )
    panel = panel.merge(
        reales,
        on=["campania", "fecha_objetivo", "fundo_operativo"],
        how="left",
        validate="one_to_one",
    )
    panel["macro_kg"] = panel.macro_kg.fillna(0.0).astype(float)
    panel["real_kg"] = panel.real_kg.fillna(0.0).astype(float)
    panel["semana_fin"] = panel.fecha_objetivo + pd.Timedelta(days=6)
    limites = dict(maximos_reales)
    limites["C2026"] = min(limites["C2026"], CIERRE_CERTIFICADO_C2026)
    panel["limite_real"] = panel.campania.map(limites)
    panel = panel.loc[panel.semana_fin.le(panel.limite_real)].copy()
    panel["semana_iso"] = panel.fecha_objetivo.dt.isocalendar().week.astype(int)
    panel["residuo_objetivo"] = np.log1p(panel.real_kg) - np.log1p(panel.macro_kg)
    if panel.duplicated(["campania", "fecha_objetivo", "fundo_operativo"]).any():
        raise ValueError("El panel cross-campaign contiene claves duplicadas")
    return panel.sort_values(
        ["fecha_objetivo", "campania", "fundo_operativo"], kind="stable"
    ).reset_index(drop=True)


__all__ = [
    "CAMPAIGNAS",
    "CIERRE_CERTIFICADO_C2026",
    "FUNDOS",
    "MACRO_RUN_ID",
    "REAL_ACCESS_DEFAULT",
    "R09_ACCESS_DEFAULT",
    "SEMANA_DESARROLLO_C2026",
    "SEMANAS_HOLDOUT_C2026",
    "construir_panel",
    "leer_macro_h1",
    "leer_reales_access",
    "leer_r09_access",
    "normalizar_fundo",
    "preparar_r09_crudo",
]

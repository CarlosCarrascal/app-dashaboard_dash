"""Lectura y preparación de las corridas del loop por horizontes."""

from __future__ import annotations

import pandas as pd
import psycopg

from analitica.settings import postgres_dsn

from . import loop_forecast_horizontes_configuracion as _configuracion

CIERRES = _configuracion.CIERRES
HORIZONTES = _configuracion.HORIZONTES
HORIZONTES_LARGOS = _configuracion.HORIZONTES_LARGOS
RUN_H1_APROBADO = _configuracion.RUN_H1_APROBADO
RUN_MACRO_MULTI = _configuracion.RUN_MACRO_MULTI
RUN_R09_MULTI = _configuracion.RUN_R09_MULTI


def _leer_predicciones(
    run_id: int,
    modelo: str,
    campania: str,
    cierre: pd.Timestamp,
    horizontes: tuple[int, ...] = HORIZONTES,
) -> pd.DataFrame:
    """Agrega una corrida a fundo antes de entregarla al loop."""

    consulta = """
        SELECT campania, fecha_emision, fecha_objetivo, horizonte_semanas,
               COALESCE(fundo, '__sin_fundo__') AS fundo,
               SUM(p50_kg) AS p50_kg,
               SUM(real_kg) AS real_kg,
               COUNT(*) AS n_filas,
               COUNT(real_kg) AS n_reales
        FROM analytics.prediction
        WHERE run_id = %s
          AND modelo = %s
          AND campania = %s
          AND horizonte_semanas = ANY(%s::smallint[])
          AND fecha_emision < fecha_objetivo
          AND fecha_objetivo + 6 <= %s
        GROUP BY campania, fecha_emision, fecha_objetivo,
                 horizonte_semanas, COALESCE(fundo, '__sin_fundo__')
        ORDER BY fecha_emision, fecha_objetivo, horizonte_semanas, fundo
    """
    with psycopg.connect(postgres_dsn()) as conexion, conexion.cursor() as cursor:
        cursor.execute(
            consulta,
            (run_id, modelo, campania, list(horizontes), cierre.date()),
        )
        salida = pd.DataFrame(cursor.fetchall(), columns=[d.name for d in cursor.description])
    if salida.empty:
        return salida
    for columna in ("fecha_emision", "fecha_objetivo"):
        salida[columna] = pd.to_datetime(salida[columna], errors="raise").dt.normalize()
    salida["horizonte_semanas"] = salida["horizonte_semanas"].astype(int)
    salida["p50_kg"] = pd.to_numeric(salida["p50_kg"], errors="raise")
    salida["real_kg"] = pd.to_numeric(salida["real_kg"], errors="coerce")
    salida["fundo"] = salida["fundo"].astype(str)
    return salida


def _normalizar_fundo(valor: object) -> str:
    texto = str(valor or "").strip().casefold()
    if texto in {"arena", "arena azul", "aqu anqa 1"}:
        return "Arena"
    if texto in {"ayllu", "ayllu allpa", "aqu anqa 4"}:
        return "Ayllu"
    if texto in {"kawsay", "kawsay allpa", "aqu anqa 3", "aqu anqa 5"}:
        return "Kawsay"
    if texto in {"quri", "quri allpa", "aqu anqa 2"}:
        return "Quri"
    return str(valor or "__sin_fundo__").strip()


def _consolidar_fundos(tabla: pd.DataFrame) -> pd.DataFrame:
    """Agrupa después de normalizar Aqu Anqa 3/5 bajo Kawsay."""

    if tabla.empty:
        return tabla
    claves = ["campania", "fecha_emision", "fecha_objetivo", "horizonte_semanas", "fundo"]
    return tabla.groupby(claves, as_index=False, dropna=False).agg(
        p50_kg=("p50_kg", "sum"),
        real_kg=("real_kg", lambda values: values.sum(min_count=1)),
        n_filas=("n_filas", "sum"),
        n_reales=("n_reales", "sum"),
    )


def _panel_base(campania: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Construye el panel base Macro/v2 y deja R09 fuera de los predictores."""

    cierre = CIERRES[campania]
    macro = _leer_predicciones(RUN_MACRO_MULTI[campania], "MacroLegacy_v1", campania, cierre)
    v2 = _leer_predicciones(
        RUN_H1_APROBADO[campania],
        "HibridoOcurrenciaOnline_v2",
        campania,
        cierre,
        (1,),
    )
    r09 = _leer_predicciones(RUN_R09_MULTI[campania], "R09_publicado", campania, cierre)
    if macro.empty:
        raise RuntimeError(f"No existe MacroLegacy cerrada para {campania}")
    for tabla in (macro, v2, r09):
        if not tabla.empty:
            tabla["fundo"] = tabla["fundo"].map(_normalizar_fundo)
    macro = _consolidar_fundos(macro)
    v2 = _consolidar_fundos(v2)
    r09 = _consolidar_fundos(r09)

    # Para h1 se conserva la v2 aprobada cuando existe; h2--h6 parten de la
    # Macro congelada porque la v2 aprobada no tiene una release multi-horizonte
    # certificada. Así no se usa accidentalmente la corrida experimental 81.
    macro["macro_kg"] = macro["p50_kg"]
    base = macro.copy()
    base["p50_kg"] = base["macro_kg"]
    if not v2.empty:
        v2_h1 = v2.rename(columns={"p50_kg": "v2_kg", "real_kg": "real_v2"})[
            [
                "campania",
                "fecha_emision",
                "fecha_objetivo",
                "horizonte_semanas",
                "fundo",
                "v2_kg",
                "real_v2",
            ]
        ]
        base = base.merge(
            v2_h1,
            on=["campania", "fecha_emision", "fecha_objetivo", "horizonte_semanas", "fundo"],
            how="left",
            validate="one_to_one",
        )
        h1 = base["horizonte_semanas"].eq(1) & base["v2_kg"].notna()
        base.loc[h1, "p50_kg"] = base.loc[h1, "v2_kg"]
        base.loc[h1 & base["real_v2"].notna(), "real_kg"] = base.loc[
            h1 & base["real_v2"].notna(), "real_v2"
        ]
    base["modulo"] = "__agregado_fundo__"
    base["lote_id"] = "F::" + base["fundo"].astype(str)
    columnas = [
        "campania",
        "fecha_emision",
        "fecha_objetivo",
        "horizonte_semanas",
        "lote_id",
        "fundo",
        "modulo",
        "p50_kg",
        "real_kg",
        "macro_kg",
    ]
    return base[columnas].copy(), r09, v2


def _leer_nowcast(campania: str) -> pd.DataFrame:
    run_id = _configuracion.RUN_NOWCAST.get(campania)
    if run_id is None:
        return pd.DataFrame()
    consulta = """
        SELECT campania, semana_inicio AS fecha_objetivo, fecha_emision,
               fundo, p50_kg, real_kg
        FROM reporting.nowcast_cierre_semanal
        WHERE run_id = %s AND campania = %s
    """
    with psycopg.connect(postgres_dsn()) as conexion, conexion.cursor() as cursor:
        cursor.execute(consulta, (run_id, campania))
        return pd.DataFrame(cursor.fetchall(), columns=[d.name for d in cursor.description])


__all__ = [
    "CIERRES",
    "HORIZONTES",
    "HORIZONTES_LARGOS",
    "RUN_H1_APROBADO",
    "RUN_MACRO_MULTI",
    "RUN_R09_MULTI",
    "_consolidar_fundos",
    "_leer_nowcast",
    "_leer_predicciones",
    "_normalizar_fundo",
    "_panel_base",
    "postgres_dsn",
    "psycopg",
]

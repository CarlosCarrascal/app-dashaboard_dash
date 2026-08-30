"""Servicio compartido para cargar el universo de lotes de screening H1."""

from __future__ import annotations

import pandas as pd
import psycopg

from analitica.settings import postgres_dsn

RUN_ID_DEFAULT = 76
CAMPANIA_DEFAULT = "C2026"
ULTIMO_CIERRE_DEFAULT = pd.Timestamp("2026-08-16")

__all__ = [
    "CAMPANIA_DEFAULT",
    "RUN_ID_DEFAULT",
    "ULTIMO_CIERRE_DEFAULT",
    "cargar_universo_lote",
]


def _normalizar_fundo(valor: object) -> str:
    clave = str(valor or "").strip().casefold()
    if clave in {"aqu anqa 1", "arena", "arena azul"}:
        return "Arena"
    if clave in {"aqu anqa 2", "quri", "quri allpa"}:
        return "Quri"
    if clave in {"aqu anqa 3", "aqu anqa 5", "kawsay", "kawsay allpa"}:
        return "Kawsay"
    if clave in {"aqu anqa 4", "ayllu", "ayllu allpa"}:
        return "Ayllu"
    return str(valor)


def _emitio_prediccion(componentes: object) -> bool:
    if not isinstance(componentes, dict):
        return False
    return bool(componentes.get("emitio_prediccion", False))


def cargar_universo_lote(
    *,
    run_id: int = RUN_ID_DEFAULT,
    campania: str = CAMPANIA_DEFAULT,
    ultimo_cierre: pd.Timestamp = ULTIMO_CIERRE_DEFAULT,
) -> pd.DataFrame:
    """Carga Macro congelada y adjunta R09 sin convertirla en predictor."""

    consulta = """
        SELECT modelo, campania, fecha_emision, fecha_objetivo,
               horizonte_semanas, fundo, modulo, lote_id,
               p50_kg, real_kg, componentes
        FROM analytics.prediction
        WHERE run_id=%s AND campania=%s
          AND modelo IN ('MacroLegacy_v1', 'R09_publicado')
          AND horizonte_semanas=1
          AND fecha_emision < fecha_objetivo
    """
    with psycopg.connect(postgres_dsn()) as conexion, conexion.cursor() as cursor:
        cursor.execute(consulta, (run_id, campania))
        columnas = [descripcion.name for descripcion in cursor.description]
        datos = pd.DataFrame(cursor.fetchall(), columns=columnas)
    if datos.empty:
        raise RuntimeError(f"No existen predicciones h1 en run {run_id} para {campania}")

    for columna in ("fecha_emision", "fecha_objetivo"):
        datos[columna] = pd.to_datetime(datos[columna]).dt.normalize()
    datos["semana_fin"] = datos.fecha_objetivo + pd.Timedelta(days=6)
    datos = datos.loc[datos.semana_fin.le(pd.Timestamp(ultimo_cierre))].copy()
    datos["semana_objetivo"] = datos.fecha_objetivo.dt.isocalendar().week.astype(int)
    datos["fundo_operativo"] = datos.fundo.map(_normalizar_fundo)

    claves = [
        "campania",
        "fecha_emision",
        "fecha_objetivo",
        "fundo",
        "modulo",
        "lote_id",
    ]
    macro = datos.loc[datos.modelo.eq("MacroLegacy_v1")].copy()
    referencia = datos.loc[datos.modelo.eq("R09_publicado")].copy()
    if macro.duplicated(claves).any() or referencia.duplicated(claves).any():
        raise ValueError("Macro o R09 contienen claves lote-emisión-objetivo duplicadas")

    macro = macro.rename(columns={"p50_kg": "macro_kg"})
    referencia["r09_emitio"] = referencia.componentes.map(_emitio_prediccion)
    referencia = referencia.rename(columns={"p50_kg": "r09_kg"})
    columnas_r09 = [*claves, "r09_kg", "r09_emitio"]
    universo = macro.merge(
        referencia[columnas_r09],
        on=claves,
        how="left",
        validate="one_to_one",
    )
    universo["macro_kg"] = pd.to_numeric(universo.macro_kg, errors="coerce").fillna(0.0)
    universo["real_kg"] = pd.to_numeric(universo.real_kg, errors="coerce").fillna(0.0)
    universo["r09_kg"] = pd.to_numeric(universo.r09_kg, errors="coerce")
    universo["r09_emitio"] = universo.r09_emitio.fillna(False).astype(bool)
    universo["fundo_operativo"] = universo.fundo.map(_normalizar_fundo)
    universo["semana_fin"] = universo.fecha_objetivo + pd.Timedelta(days=6)
    universo["semana_objetivo"] = universo.fecha_objetivo.dt.isocalendar().week.astype(int)
    return universo.sort_values(
        ["fecha_objetivo", "fundo_operativo", "fundo", "modulo", "lote_id"],
        kind="stable",
    ).reset_index(drop=True)

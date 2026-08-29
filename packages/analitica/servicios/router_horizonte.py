"""Lectura y agregación compartidas por los routers de horizonte."""

from __future__ import annotations

import numpy as np
import pandas as pd
import psycopg

from analitica.settings import postgres_dsn

RUNS_MULTI = {"C2024": 71, "C2025": 72, "C2026": 73}
RUNS_H1 = {"C2024": 76, "C2025": 78, "C2026": 76}
CIERRES = {
    "C2024": pd.Timestamp("2025-04-20"),
    "C2025": pd.Timestamp("2026-03-01"),
    "C2026": pd.Timestamp("2026-08-16"),
}


def leer(run_id: int, campania: str, modelo: str, horizontes: tuple[int, ...]) -> pd.DataFrame:
    consulta = """
        SELECT campania, fecha_emision, fecha_objetivo, horizonte_semanas,
               lote_id, fundo, modulo, p50_kg, real_kg
        FROM analytics.prediction
        WHERE run_id=%s AND campania=%s AND modelo=%s
          AND horizonte_semanas = ANY(%s::smallint[])
          AND fecha_emision < fecha_objetivo
    """
    with psycopg.connect(postgres_dsn()) as conexion, conexion.cursor() as cursor:
        cursor.execute(consulta, (run_id, campania, modelo, list(horizontes)))
        columnas = [d.name for d in cursor.description]
        tabla = pd.DataFrame(cursor.fetchall(), columns=columnas)
    tabla["fecha_emision"] = pd.to_datetime(tabla.fecha_emision).dt.normalize()
    tabla["fecha_objetivo"] = pd.to_datetime(tabla.fecha_objetivo).dt.normalize()
    return tabla[tabla.fecha_objetivo.add(pd.Timedelta(days=6)).le(CIERRES[campania])].copy()


def agregar(tabla: pd.DataFrame, nombre: str) -> pd.DataFrame:
    claves = ["campania", "fecha_emision", "fecha_objetivo", "horizonte_semanas"]
    return tabla.groupby(claves, as_index=False).agg(
        **{nombre: ("p50_kg", "sum")},
        # Un real completamente desconocido no significa cosecha cero.
        real_kg=("real_kg", lambda valores: valores.sum(min_count=1)),
    )


def evaluar_campania(campania: str) -> dict:
    h1 = _leer(RUNS_H1[campania], campania, "HibridoOcurrenciaOnline_v2", (1,))
    macro_h1 = _leer(RUNS_H1[campania], campania, "MacroLegacy_v1", (1,))
    r09_h1 = _leer(RUNS_H1[campania], campania, "R09_publicado", (1,))
    macro_h2 = _leer(RUNS_MULTI[campania], campania, "MacroLegacy_v1", (2, 3, 4, 5))
    r09_h2 = _leer(RUNS_MULTI[campania], campania, "R09_publicado", (2, 3, 4, 5))

    candidato = pd.concat([h1, macro_h2], ignore_index=True)
    macro = pd.concat([macro_h1, macro_h2], ignore_index=True)
    r09 = pd.concat([r09_h1, r09_h2], ignore_index=True)
    c = _agregar(candidato, "candidate_kg")
    m = _agregar(macro, "macro_kg")
    r = _agregar(r09, "r09_kg")
    claves = ["campania", "fecha_emision", "fecha_objetivo", "horizonte_semanas"]
    comun = c.merge(m.drop(columns="real_kg"), on=claves).merge(
        r.drop(columns="real_kg"), on=claves
    )
    real = comun.real_kg.astype(float)
    denom = float(real.abs().sum())
    salida = {
        "campania": campania,
        "n_emision_objetivo_horizonte": int(len(comun)),
        "volumen_real_kg": float(real.sum()),
        "por_modelo": {},
        "por_horizonte": {},
    }
    for nombre, columna in (
        ("RouterHorizonte_v1", "candidate_kg"),
        ("MacroLegacy_v1", "macro_kg"),
        ("R09_publicado", "r09_kg"),
    ):
        error = comun[columna] - real
        salida["por_modelo"][nombre] = {
            "wape": float(error.abs().sum() / denom) if denom else np.nan,
            "sesgo": float(error.sum() / denom) if denom else np.nan,
            "mae_kg": float(error.abs().mean()),
        }
    for horizonte, grupo in comun.groupby("horizonte_semanas"):
        d = float(grupo.real_kg.abs().sum())
        salida["por_horizonte"][str(int(horizonte))] = {
            nombre: float((grupo[columna] - grupo.real_kg).abs().sum() / d) if d else np.nan
            for nombre, columna in (
                ("router_wape", "candidate_kg"),
                ("macro_wape", "macro_kg"),
                ("r09_wape", "r09_kg"),
            )
        }
    salida["porcentaje_cortes_ganados_r09"] = float(
        ((comun.candidate_kg - real).abs() < (comun.r09_kg - real).abs()).mean()
    )
    return salida


def ejecutar() -> dict:
    resultados = {campania: evaluar_campania(campania) for campania in RUNS_MULTI}
    decisiones = {}
    for campania, resultado in resultados.items():
        c = resultado["por_modelo"]["RouterHorizonte_v1"]
        r = resultado["por_modelo"]["R09_publicado"]
        m = resultado["por_modelo"]["MacroLegacy_v1"]
        decisiones[campania] = {
            "mejora_macro_relativa": float((m["wape"] - c["wape"]) / m["wape"]),
            "mejora_r09_relativa": float((r["wape"] - c["wape"]) / r["wape"]),
            "iguala_o_supera_r09": bool(c["wape"] <= r["wape"]),
            "sesgo_abs_le_10pct": bool(abs(c["sesgo"]) <= 0.10),
        }
    return {
        "schema": "screening-router-horizonte-v1",
        "formula": "HibridoOcurrenciaOnline_v2 en h1; MacroLegacy_v1 en h2-h5",
        "usa_r09_como_predictor": False,
        "runs_h1": RUNS_H1,
        "runs_multi": RUNS_MULTI,
        "resultados": resultados,
        "decisiones": decisiones,
        "publicable": False,
    }


# Alias privados conservados para consumidores históricos que los importan o
# sustituyen durante pruebas locales. La implementación única sigue en este servicio.
_leer = leer
_agregar = agregar


__all__ = [
    "CIERRES",
    "RUNS_H1",
    "RUNS_MULTI",
    "agregar",
    "ejecutar",
    "evaluar_campania",
    "leer",
]

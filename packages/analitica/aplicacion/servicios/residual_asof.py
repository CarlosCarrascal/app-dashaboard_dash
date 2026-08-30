"""Servicio de screening de calibración residual as-of.

La implementación conserva el contrato histórico de
``screening_residual_asof``: compara MacroLegacy, el candidato calibrado y
R09 sobre el universo común, selecciona únicamente con campañas cerradas de
desarrollo y mantiene C2026 como validación externa fuera de la selección.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import numpy as np
import pandas as pd
import psycopg

from analitica.aplicacion.procesos.candidate_residual_asof import (
    ConfiguracionResidualAsOf,
    aplicar_calibracion_residual_asof,
)
from analitica.aplicacion.procesos.candidatos import (
    escribir_json_reproducible as _escribir_json_reproducible,
)
from analitica.settings import postgres_dsn

RUNS = {"C2024": 71, "C2025": 72, "C2026": 73}
CIERRES = {
    "C2024": pd.Timestamp("2025-04-20"),
    "C2025": pd.Timestamp("2026-03-01"),
    "C2026": pd.Timestamp("2026-08-16"),
}

escribir_json_reproducible = _escribir_json_reproducible


def configuraciones() -> list[ConfiguracionResidualAsOf]:
    return [
        ConfiguracionResidualAsOf(
            nivel=nivel,
            ventana=ventana,
            regularizacion=regularizacion,
            factor_min=limites[0],
            factor_max=limites[1],
            usar_campanias_previas=usar_previas,
        )
        for nivel in ("global", "fundo")
        for ventana in (4, 8)
        for regularizacion in (2.0, 6.0)
        for limites in ((0.80, 1.30),)
        for usar_previas in (False, True)
    ]


def leer_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    dsn = postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL no esta configurado")
    macros: list[pd.DataFrame] = []
    referencias: list[pd.DataFrame] = []
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
    ]
    consulta = """
        SELECT campania, fecha_emision, fecha_objetivo, horizonte_semanas,
               lote_id, fundo, modulo, p50_kg, real_kg
        FROM analytics.prediction
        WHERE run_id = %s AND campania = %s AND modelo = %s
          AND horizonte_semanas BETWEEN 1 AND 6
          AND fecha_emision < fecha_objetivo
    """
    with psycopg.connect(dsn) as conexion:
        for campania, run_id in RUNS.items():
            for modelo, destino in (("MacroLegacy_v1", macros), ("R09_publicado", referencias)):
                with conexion.cursor() as cursor:
                    cursor.execute(consulta, (run_id, campania, modelo))
                    tabla = pd.DataFrame(cursor.fetchall(), columns=columnas)
                tabla["fecha_objetivo"] = pd.to_datetime(tabla.fecha_objetivo)
                tabla = tabla[
                    tabla.fecha_objetivo.add(pd.Timedelta(days=6)).le(CIERRES[campania])
                ].copy()
                destino.append(tabla)
    macro = pd.concat(macros, ignore_index=True)
    r09 = pd.concat(referencias, ignore_index=True)
    for tabla in (macro, r09):
        tabla["fecha_emision"] = pd.to_datetime(tabla.fecha_emision).dt.normalize()
        tabla["fecha_objetivo"] = pd.to_datetime(tabla.fecha_objetivo).dt.normalize()
    return macro, r09


def _semanal(tabla: pd.DataFrame, columna: str) -> pd.DataFrame:
    claves = ["campania", "fecha_emision", "fecha_objetivo", "horizonte_semanas"]
    return tabla.groupby(claves, as_index=False).agg(
        pred_kg=(columna, "sum"), real_kg=("real_kg", "sum")
    )


def comparar_comun(
    macro: pd.DataFrame, candidato: pd.DataFrame, r09: pd.DataFrame, campanias: set[str]
) -> dict:
    m = _semanal(macro[macro.campania.isin(campanias)], "p50_kg").rename(
        columns={"pred_kg": "macro_kg", "real_kg": "real_macro"}
    )
    c = _semanal(candidato[candidato.campania.isin(campanias)], "p50_kg").rename(
        columns={"pred_kg": "candidate_kg", "real_kg": "real_candidate"}
    )
    r = _semanal(r09[r09.campania.isin(campanias)], "p50_kg").rename(
        columns={"pred_kg": "r09_kg", "real_kg": "real_r09"}
    )
    claves = ["campania", "fecha_emision", "fecha_objetivo", "horizonte_semanas"]
    comun = m.merge(c, on=claves, validate="one_to_one").merge(r, on=claves)
    if comun.empty:
        raise ValueError("No existe universo comun Macro-candidato-R09")
    if not (
        np.isclose(comun.real_macro, comun.real_candidate, equal_nan=True).all()
        and np.isclose(comun.real_macro, comun.real_r09, equal_nan=True).all()
    ):
        # El real adjunto a R09 puede estar repetido solo sobre sus lotes. El
        # denominador contractual siempre lo fija Macro, que cubre el panel total.
        comun["real_r09"] = comun.real_macro
    real = comun.real_macro.astype(float)
    denom = float(real.abs().sum())
    resultado = {
        "n_emision_objetivo_horizonte": int(len(comun)),
        "volumen_real_kg": float(real.sum()),
        "por_modelo": {},
        "por_horizonte": {},
    }
    for nombre, columna in (
        ("MacroLegacy_v1", "macro_kg"),
        ("CandidateResidualAsOf_v1", "candidate_kg"),
        ("R09_publicado", "r09_kg"),
    ):
        error = comun[columna].astype(float) - real
        resultado["por_modelo"][nombre] = {
            "wape": float(error.abs().sum() / denom) if denom else np.nan,
            "sesgo": float(error.sum() / denom) if denom else np.nan,
            "mae_kg": float(error.abs().mean()),
        }
    for horizonte, grupo in comun.groupby("horizonte_semanas"):
        d = float(grupo.real_macro.abs().sum())
        fila = {"n": int(len(grupo))}
        for nombre, columna in (
            ("macro", "macro_kg"),
            ("candidato", "candidate_kg"),
            ("r09", "r09_kg"),
        ):
            error = grupo[columna] - grupo.real_macro
            fila[f"wape_{nombre}"] = float(error.abs().sum() / d) if d else np.nan
            fila[f"sesgo_{nombre}"] = float(error.sum() / d) if d else np.nan
        resultado["por_horizonte"][str(int(horizonte))] = fila
    err_c = (comun.candidate_kg - real).abs()
    err_r = (comun.r09_kg - real).abs()
    resultado["porcentaje_cortes_ganados_a_r09"] = float((err_c < err_r).mean())
    return resultado


def score(resultado: dict) -> float:
    met = resultado["por_modelo"]["CandidateResidualAsOf_v1"]
    return float(met["wape"] + max(0.0, abs(met["sesgo"]) - 0.10))


def ejecutar() -> dict:
    macro, r09 = leer_panel()
    vivos = configuraciones()
    rondas = []
    cache: dict[str, pd.DataFrame] = {}
    for campanias, conservar in (({"C2024"}, 12), ({"C2024", "C2025"}, 4)):
        ranking = []
        for config in vivos:
            clave = json.dumps(asdict(config), sort_keys=True)
            if clave not in cache:
                cache[clave] = aplicar_calibracion_residual_asof(macro, config)
            candidato = cache[clave]
            resultado = comparar_comun(macro, candidato, r09, campanias)
            ranking.append((score(resultado), config, resultado))
        ranking.sort(key=lambda x: (x[0], json.dumps(asdict(x[1]), sort_keys=True)))
        rondas.append(
            {
                "campanias": sorted(campanias),
                "n_candidatos": len(ranking),
                "ranking": [
                    {"score": s, "configuracion": asdict(c), "metricas": m} for s, c, m in ranking
                ],
            }
        )
        vivos = [c for _, c, _ in ranking[:conservar]]
    finalistas = []
    for config in vivos:
        clave = json.dumps(asdict(config), sort_keys=True)
        candidato = cache[clave]
        externo = comparar_comun(macro, candidato, r09, {"C2026"})
        desarrollo = comparar_comun(macro, candidato, r09, {"C2024", "C2025"})
        finalistas.append(
            {"configuracion": asdict(config), "desarrollo": desarrollo, "externo_c2026": externo}
        )
    # La validacion externa no participa en la seleccion.
    finalistas.sort(key=lambda x: score(x["desarrollo"]))
    mejor = finalistas[0]
    c = mejor["externo_c2026"]["por_modelo"]["CandidateResidualAsOf_v1"]
    r = mejor["externo_c2026"]["por_modelo"]["R09_publicado"]
    m = mejor["externo_c2026"]["por_modelo"]["MacroLegacy_v1"]
    decision = {
        "iguala_o_supera_r09_wape": bool(c["wape"] <= r["wape"]),
        "mejora_macro_relativa": float((m["wape"] - c["wape"]) / m["wape"]),
        "mejora_r09_relativa": float((r["wape"] - c["wape"]) / r["wape"]),
        "sesgo_abs_le_10pct": bool(abs(c["sesgo"]) <= 0.10),
        "publicable": False,
        "motivo": "screening candidate-only; falta bootstrap, fundo y replay certificado",
    }
    # Segundo protocolo: seleccion temporal dentro de la campaña vigente. La
    # parte julio-agosto permanece intocable hasta elegir la configuracion con
    # marzo-junio. Esto permite evaluar adaptacion online sin trasladar a ciegas
    # el sesgo de campañas con otra parametrizacion.
    temprano_hasta = pd.Timestamp("2026-06-28")
    holdout_desde = pd.Timestamp("2026-06-29")
    ranking_actual = []
    for config in configuraciones():
        clave = json.dumps(asdict(config), sort_keys=True)
        if clave not in cache:
            cache[clave] = aplicar_calibracion_residual_asof(macro, config)
        candidato = cache[clave]
        temprano = comparar_comun(
            macro[macro.fecha_objetivo.le(temprano_hasta)],
            candidato[candidato.fecha_objetivo.le(temprano_hasta)],
            r09[r09.fecha_objetivo.le(temprano_hasta)],
            {"C2026"},
        )
        ranking_actual.append((score(temprano), config, temprano, candidato))
    ranking_actual.sort(key=lambda x: (x[0], json.dumps(asdict(x[1]), sort_keys=True)))
    _, config_actual, temprano, candidato_actual = ranking_actual[0]
    holdout = comparar_comun(
        macro[macro.fecha_objetivo.ge(holdout_desde)],
        candidato_actual[candidato_actual.fecha_objetivo.ge(holdout_desde)],
        r09[r09.fecha_objetivo.ge(holdout_desde)],
        {"C2026"},
    )
    c_h = holdout["por_modelo"]["CandidateResidualAsOf_v1"]
    r_h = holdout["por_modelo"]["R09_publicado"]
    m_h = holdout["por_modelo"]["MacroLegacy_v1"]
    protocolo_actual = {
        "seleccion_hasta": str(temprano_hasta.date()),
        "holdout_desde": str(holdout_desde.date()),
        "configuracion": asdict(config_actual),
        "desarrollo_temprano": temprano,
        "holdout_tardio": holdout,
        "decision": {
            "iguala_o_supera_r09_wape": bool(c_h["wape"] <= r_h["wape"]),
            "mejora_macro_relativa": float((m_h["wape"] - c_h["wape"]) / m_h["wape"]),
            "mejora_r09_relativa": float((r_h["wape"] - c_h["wape"]) / r_h["wape"]),
            "sesgo_abs_le_10pct": bool(abs(c_h["sesgo"]) <= 0.10),
        },
    }
    return {
        "schema": "screening-residual-asof-v1",
        "runs_congelados": RUNS,
        "cierres": {k: str(v.date()) for k, v in CIERRES.items()},
        "n_configuraciones": len(configuraciones()),
        "rondas": rondas,
        "finalistas": finalistas,
        "mejor": mejor,
        "decision": decision,
        "protocolo_c2026_temporal": protocolo_actual,
    }

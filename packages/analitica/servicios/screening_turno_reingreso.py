"""Servicio reutilizable del screening rápido del calendario de reingreso.

Contiene la lógica histórica de ``screening_turno_reingreso`` sin cambiar sus
resultados, fórmulas, calendario, semántica as-of, configuraciones, métricas ni
contrato JSON. La fachada CLI histórica permanece en
``analitica.scripts.screening_turno_reingreso``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
import psycopg

from analitica.proyeccion.candidate_preflight import (
    escribir_json_reproducible as _escribir_json_reproducible,
)
from analitica.settings import postgres_dsn

escribir_json_reproducible = _escribir_json_reproducible

RUNS = {"C2024": 71, "C2025": 72, "C2026": 73}
CIERRES = {
    "C2024": pd.Timestamp("2025-04-20"),
    "C2025": pd.Timestamp("2026-03-01"),
    "C2026": pd.Timestamp("2026-08-16"),
}


@dataclass(frozen=True)
class Config:
    ventana_intervalos: int
    dispersion_dias: float
    peso_calendario: float


def leer_datos() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    consulta = """
        SELECT campania, fecha_emision, fecha_objetivo, horizonte_semanas,
               lote_id, fundo, modulo, p50_kg, real_kg
        FROM analytics.prediction
        WHERE run_id=%s AND campania=%s AND modelo=%s
          AND fecha_emision < fecha_objetivo
    """
    macros: list[pd.DataFrame] = []
    r09s: list[pd.DataFrame] = []
    with psycopg.connect(postgres_dsn()) as conexion:
        for campania, run_id in RUNS.items():
            for modelo, destino in (("MacroLegacy_v1", macros), ("R09_publicado", r09s)):
                with conexion.cursor() as cursor:
                    cursor.execute(consulta, (run_id, campania, modelo))
                    columnas = [d.name for d in cursor.description]
                    destino.append(pd.DataFrame(cursor.fetchall(), columns=columnas))
        cosecha = pd.read_sql_query(
            """
            SELECT h.campania, h.lote_id, h.fecha, SUM(h.kg) AS kg,
                   COALESCE(t.codigo, h.turno, '') AS turno
            FROM stg.h01_cosecha h
            LEFT JOIN core.lote l ON l.lote_id=h.lote_id
            LEFT JOIN core.turno t ON t.turno_id=l.turno_id
            WHERE h.campania IN ('C2024','C2025','C2026')
            GROUP BY h.campania, h.lote_id, h.fecha, COALESCE(t.codigo, h.turno, '')
            """,
            conexion,
        )
    macro = pd.concat(macros, ignore_index=True)
    r09 = pd.concat(r09s, ignore_index=True)
    for tabla in (macro, r09):
        tabla["fecha_emision"] = pd.to_datetime(tabla.fecha_emision).dt.normalize()
        tabla["fecha_objetivo"] = pd.to_datetime(tabla.fecha_objetivo).dt.normalize()
        tabla["semana_fin"] = tabla.fecha_objetivo + pd.Timedelta(days=6)
        tabla["p50_kg"] = pd.to_numeric(tabla.p50_kg, errors="coerce").fillna(0.0)
        tabla["real_kg"] = pd.to_numeric(tabla.real_kg, errors="coerce")
        tabla.drop(
            tabla.index[
                [
                    fin > CIERRES[campania]
                    for fin, campania in zip(tabla.semana_fin, tabla.campania, strict=False)
                ]
            ],
            inplace=True,
        )
    cosecha["fecha"] = pd.to_datetime(cosecha.fecha).dt.normalize()
    cosecha["kg"] = pd.to_numeric(cosecha.kg, errors="coerce").fillna(0.0).clip(lower=0)
    cosecha = cosecha[cosecha.kg.gt(0)].sort_values(["campania", "lote_id", "fecha"])
    return macro.reset_index(drop=True), r09.reset_index(drop=True), cosecha.reset_index(drop=True)


def _historia_por_lote(cosecha: pd.DataFrame) -> dict[tuple[str, int], np.ndarray]:
    return {
        (str(campania), int(lote_id)): grupo.fecha.drop_duplicates().sort_values().to_numpy()
        for (campania, lote_id), grupo in cosecha.groupby(["campania", "lote_id"])
    }


def _share_calendario(
    fechas_objetivo: np.ndarray,
    fechas_cosecha: np.ndarray,
    emision: pd.Timestamp,
    ventana: int,
    dispersion: float,
) -> tuple[np.ndarray | None, float | None, pd.Timestamp | None]:
    previas = pd.to_datetime(fechas_cosecha[fechas_cosecha < np.datetime64(emision)])
    if len(previas) < 2:
        return None, None, None
    diferencias = np.diff(previas.values).astype("timedelta64[D]").astype(float)
    diferencias = diferencias[(diferencias >= 5) & (diferencias <= 21)]
    if not len(diferencias):
        return None, None, None
    intervalo = float(np.median(diferencias[-ventana:]))
    ultima = pd.Timestamp(previas.max()).normalize()
    inicio = pd.Timestamp(pd.to_datetime(fechas_objetivo).min()).normalize()
    fin = pd.Timestamp(pd.to_datetime(fechas_objetivo).max()).normalize() + pd.Timedelta(days=6)
    siguiente = ultima + pd.Timedelta(days=intervalo)
    while siguiente < inicio - pd.Timedelta(days=21):
        siguiente += pd.Timedelta(days=intervalo)
    pasadas: list[pd.Timestamp] = []
    cursor = siguiente
    while cursor <= fin + pd.Timedelta(days=21):
        pasadas.append(cursor)
        cursor += pd.Timedelta(days=intervalo)
    if not pasadas:
        return None, intervalo, siguiente
    centros = pd.to_datetime(fechas_objetivo) + pd.Timedelta(days=3)
    scores = np.zeros(len(centros), dtype=float)
    for pasada in pasadas:
        distancia = (centros - pasada).days.astype(float)
        scores += np.exp(-0.5 * (distancia / dispersion) ** 2)
    total = float(scores.sum())
    return (scores / total if total > 0 else None), intervalo, siguiente


def precomputar_shares(macro: pd.DataFrame) -> pd.DataFrame:
    historia = _historia_por_lote(_COSECHA_GLOBAL)
    base = macro.copy()
    configuraciones = [(v, d) for v in (3, 5) for d in (2.5, 4.5, 7.0)]
    for ventana, dispersion in configuraciones:
        base[f"share_{ventana}_{dispersion}"] = np.nan
    base["intervalo_asof"] = np.nan
    base["siguiente_reingreso_asof"] = pd.NaT

    grupos = ["campania", "fecha_emision", "lote_id"]
    for (campania, emision, lote_id), indices in base.groupby(grupos, sort=False).groups.items():
        indices = list(indices)
        bloque = base.loc[indices].sort_values("fecha_objetivo")
        fechas = historia.get((str(campania), int(lote_id)))
        if fechas is None:
            continue
        for ventana, dispersion in configuraciones:
            share, intervalo, siguiente = _share_calendario(
                bloque.fecha_objetivo.to_numpy(), fechas, pd.Timestamp(emision), ventana, dispersion
            )
            if share is None:
                continue
            base.loc[bloque.index, f"share_{ventana}_{dispersion}"] = share
            if ventana == 5 and dispersion == 4.5:
                base.loc[bloque.index, "intervalo_asof"] = intervalo
                base.loc[bloque.index, "siguiente_reingreso_asof"] = siguiente
    return base


def aplicar_config(base: pd.DataFrame, config: Config) -> pd.DataFrame:
    t = base.copy()
    columna = f"share_{config.ventana_intervalos}_{config.dispersion_dias}"
    grupos = ["campania", "fecha_emision", "lote_id"]
    total = t.groupby(grupos).p50_kg.transform("sum")
    share_base = t.p50_kg.div(total.replace(0, np.nan)).fillna(0.0)
    share_cal = t[columna]
    aplicable = share_cal.notna() & total.gt(0)
    share_final = share_base.copy()
    share_final.loc[aplicable] = (1.0 - config.peso_calendario) * share_base.loc[
        aplicable
    ] + config.peso_calendario * share_cal.loc[aplicable]
    t["candidate_kg"] = total * share_final
    t["calendario_aplicado"] = aplicable
    return t


def _serie_empresa(tabla: pd.DataFrame, columna: str) -> pd.DataFrame:
    claves = ["campania", "fecha_emision", "fecha_objetivo", "horizonte_semanas"]
    return tabla.groupby(claves, as_index=False).agg(
        pred_kg=(columna, "sum"), real_kg=("real_kg", "sum")
    )


def metricas(tabla: pd.DataFrame, columna: str) -> dict[str, object]:
    empresa = _serie_empresa(tabla, columna)
    error = empresa.pred_kg - empresa.real_kg
    denom = float(empresa.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / denom) if denom else np.nan,
        "sesgo": float(error.sum() / denom) if denom else np.nan,
        "mae_kg": float(error.abs().mean()),
        "n": int(len(empresa)),
    }


def comparar(tabla: pd.DataFrame, r09: pd.DataFrame, campania: str) -> dict[str, object]:
    candidato = _serie_empresa(tabla[tabla.campania.eq(campania)], "candidate_kg")
    macro = _serie_empresa(tabla[tabla.campania.eq(campania)], "p50_kg").rename(
        columns={"pred_kg": "macro_kg"}
    )
    claves = ["campania", "fecha_emision", "fecha_objetivo", "horizonte_semanas"]
    referencia = (
        r09[r09.campania.eq(campania)]
        .groupby(claves, as_index=False)
        .p50_kg.sum()
        .rename(columns={"p50_kg": "r09_kg"})
    )
    comun = candidato.merge(macro[claves + ["macro_kg"]], on=claves, validate="one_to_one")
    comun = comun.merge(referencia, on=claves, validate="one_to_one")
    denom = float(comun.real_kg.abs().sum())
    por_modelo = {}
    for nombre, columna in (("candidate", "pred_kg"), ("macro", "macro_kg"), ("r09", "r09_kg")):
        error = comun[columna] - comun.real_kg
        por_modelo[nombre] = {
            "wape": float(error.abs().sum() / denom) if denom else np.nan,
            "sesgo": float(error.sum() / denom) if denom else np.nan,
            "mae_kg": float(error.abs().mean()),
        }
    por_horizonte = {}
    for horizonte, bloque in comun.groupby("horizonte_semanas"):
        denom_h = float(bloque.real_kg.abs().sum())
        por_horizonte[str(int(horizonte))] = {
            nombre: float((bloque[columna] - bloque.real_kg).abs().sum() / denom_h)
            for nombre, columna in (
                ("candidate", "pred_kg"),
                ("macro", "macro_kg"),
                ("r09", "r09_kg"),
            )
        }
    return {"n": int(len(comun)), "por_modelo": por_modelo, "por_horizonte": por_horizonte}


def _cortes_micro(tabla: pd.DataFrame) -> pd.DataFrame:
    emisiones_elegidas: list[pd.Timestamp] = []
    for _, bloque in tabla.groupby("campania"):
        emisiones = sorted(pd.to_datetime(bloque.fecha_emision).unique())
        if not emisiones:
            continue
        posiciones = sorted({0, len(emisiones) // 3, (2 * len(emisiones)) // 3, len(emisiones) - 1})
        emisiones_elegidas.extend(pd.Timestamp(emisiones[i]) for i in posiciones)
    return tabla[tabla.fecha_emision.isin(emisiones_elegidas)].copy()


def ejecutar(*, micro: bool = False) -> dict[str, object]:
    global _COSECHA_GLOBAL
    macro, r09, _COSECHA_GLOBAL = leer_datos()
    if micro:
        macro = _cortes_micro(macro)
        r09 = _cortes_micro(r09)
    precomputado = precomputar_shares(macro)
    configs = [
        Config(ventana, dispersion, peso)
        for ventana in (3, 5)
        for dispersion in (2.5, 4.5, 7.0)
        for peso in (0.10, 0.20, 0.35, 0.50)
    ]
    ranking = []
    cache: dict[str, pd.DataFrame] = {}
    for config in configs:
        candidato = aplicar_config(precomputado, config)
        clave = json.dumps(asdict(config), sort_keys=True)
        cache[clave] = candidato
        desarrollo = []
        for campania in ("C2024", "C2025"):
            m = metricas(candidato[candidato.campania.eq(campania)], "candidate_kg")
            desarrollo.append(m["wape"])
        ranking.append(
            {
                "config": asdict(config),
                "wape_desarrollo_promedio_campanias": float(np.mean(desarrollo)),
                "wape_desarrollo_por_campania": dict(
                    zip(("C2024", "C2025"), desarrollo, strict=False)
                ),
            }
        )
    ranking.sort(key=lambda x: x["wape_desarrollo_promedio_campanias"])
    finalistas = []
    for fila in ranking[:6]:
        clave = json.dumps(fila["config"], sort_keys=True)
        candidato = cache[clave]
        finalistas.append({**fila, "externo_c2026": comparar(candidato, r09, "C2026")})
    cobertura = float(precomputado.intervalo_asof.notna().mean())
    return {
        "schema": "turno-reingreso-screening-v1",
        "micro_replay": micro,
        "seleccion": "C2024+C2025; C2026 externa",
        "runs": RUNS,
        "cobertura_lote_emision_con_intervalo": cobertura,
        "n_configuraciones": len(configs),
        "ranking": ranking[:12],
        "finalistas": finalistas,
        "mejor": finalistas[0],
        "publicable": False,
    }


_COSECHA_GLOBAL = pd.DataFrame()

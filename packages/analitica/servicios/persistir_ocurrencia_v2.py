"""Persiste el replay completo y comparable de OcurrenciaOnline v2.

Usa las corridas históricas validadas de MacroLegacy como rejilla maestra. R09 se
expande a esa rejilla únicamente para evaluación: una ausencia se marca como
``emitio_prediccion=False`` y se penaliza como cero en el WAPE operacional.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from analitica import settings
from analitica.proyeccion.gobernanza import RepositorioAnalytics
from analitica.proyeccion.hibrido_ocurrencia import (
    NOMBRE_MODELO as MODELO_V1,
)
from analitica.proyeccion.hibrido_ocurrencia import (
    VERSION_MODELO as VERSION_V1,
)
from analitica.proyeccion.hibrido_ocurrencia import (
    ejecutar_replay_hibrido_ocurrencia,
)
from analitica.proyeccion.hibrido_ocurrencia_v2 import (
    NOMBRE_MODELO as MODELO_V2,
)
from analitica.proyeccion.hibrido_ocurrencia_v2 import (
    VERSION_MODELO as VERSION_V2,
)
from analitica.proyeccion.hibrido_ocurrencia_v2 import (
    ejecutar_replay_hibrido_ocurrencia_v2,
)
from analitica.proyeccion.metricas import (
    metricas_cobertura_operacional,
    metricas_pronostico,
)

MODELO_R09 = "R09_publicado"
MODELO_MACRO = "MacroLegacy_v1"
MODELO_NAIVE = "Naive_lag1"
SNAPSHOT_ID = 40
RUNS_ORIGEN = {"C2024": 71, "C2025": 72, "C2026": 73}
CLAVES = ["campania", "lote_id", "fecha_objetivo"]


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _leer_fuentes() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    import psycopg

    dsn = settings.postgres_dsn()
    consulta = """
        WITH candidatos AS (
            SELECT p.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY p.modelo, p.campania, p.lote_id, p.fecha_objetivo
                       ORDER BY p.fecha_emision DESC, p.prediction_id DESC
                   ) AS rn
            FROM analytics.prediction p
            WHERE p.run_id = ANY(%s)
              AND p.modelo = ANY(%s)
              AND p.horizonte_semanas = 1
        )
        SELECT * FROM candidatos WHERE rn = 1
    """
    with psycopg.connect(dsn) as conexion:
        datos = pd.read_sql_query(
            consulta,
            conexion,
            params=(list(RUNS_ORIGEN.values()), [MODELO_MACRO, MODELO_R09]),
        )
        cierres = pd.read_sql_query(
            """
            SELECT campania, MAX(fecha) AS ultima_fecha_real
            FROM stg.v_h01_cosecha
            WHERE campania IS NOT NULL
            GROUP BY campania
            """,
            conexion,
        )
    datos["fecha_objetivo"] = pd.to_datetime(datos["fecha_objetivo"], errors="raise")
    datos["fecha_emision"] = pd.to_datetime(datos["fecha_emision"], errors="raise")
    cierres["ultima_fecha_real"] = pd.to_datetime(cierres["ultima_fecha_real"])
    maximos = dict(
        zip(cierres.campania.astype(str), cierres.ultima_fecha_real, strict=False)
    )
    macro = datos[datos.modelo.eq(MODELO_MACRO)].copy()
    r09 = datos[datos.modelo.eq(MODELO_R09)].copy()
    if macro.empty:
        raise ValueError("No existe MacroLegacy en las corridas de origen")
    # Una semana es evaluable cuando su domingo ya existe en la fuente real. Así la
    # semana parcial C2026 17–23/08 no se juzga como si estuviera cerrada.
    macro = macro[
        macro.apply(
            lambda fila: (
                fila.fecha_objetivo + pd.Timedelta(days=6)
                <= maximos.get(str(fila.campania), pd.Timestamp.min)
            ),
            axis=1,
        )
    ].copy()
    periodos = macro[["campania", "fecha_objetivo"]].drop_duplicates()
    r09 = r09.merge(periodos, on=["campania", "fecha_objetivo"], how="inner")
    return macro, r09, {k: v.date().isoformat() for k, v in maximos.items()}


def _expandir_referencia(base: pd.DataFrame, fuente: pd.DataFrame, modelo: str) -> pd.DataFrame:
    identidad = [
        c
        for c in (
            "campania",
            "empresa",
            "fundo",
            "modulo",
            "lote",
            "lote_id",
            "fecha_emision",
            "fecha_objetivo",
            "horizonte_semanas",
            "banda_horizonte",
            "real_kg",
            "plantas",
            "frutos_por_planta",
            "peso_baya_g",
        )
        if c in base
    ]
    rejilla = base[identidad].copy()
    valores = fuente[CLAVES + ["p50_kg", "fecha_emision", "version_fuente"]].rename(
        columns={"fecha_emision": "fecha_emision_fuente"}
    )
    salida = rejilla.merge(valores, on=CLAVES, how="left", suffixes=("", "_ref"))
    salida["emitio_prediccion"] = salida["p50_kg"].notna()
    salida["p50_kg"] = pd.to_numeric(salida["p50_kg"], errors="coerce").fillna(0.0)
    salida["modelo"] = modelo
    salida["version_modelo"] = "emision_publicada_no_algoritmo"
    salida["origen_emision"] = salida["fecha_emision_fuente"]
    salida["componentes"] = salida.apply(
        lambda fila: {
            "emitio_prediccion": bool(fila.emitio_prediccion),
            "referencia_publicada": True,
            "ausencia_evaluada_como_cero": not bool(fila.emitio_prediccion),
        },
        axis=1,
    )
    return salida


def _expandir_v1(base: pd.DataFrame, predicho: pd.DataFrame) -> pd.DataFrame:
    salida = _expandir_referencia(base, predicho, MODELO_V1)
    salida["version_modelo"] = VERSION_V1
    salida["componentes"] = salida.apply(
        lambda fila: {
            "emitio_prediccion": bool(fila.emitio_prediccion),
            "calentamiento_sin_emision": not bool(fila.emitio_prediccion),
            "modelo_base": MODELO_MACRO,
        },
        axis=1,
    )
    return salida


def _naive(base: pd.DataFrame) -> pd.DataFrame:
    salida = base.copy().sort_values(["lote_id", "fecha_objetivo"])
    salida["p50_kg"] = salida.groupby("lote_id", sort=False)["real_kg"].shift(1)
    salida["emitio_prediccion"] = salida["p50_kg"].notna()
    salida["p50_kg"] = salida["p50_kg"].fillna(0.0)
    salida["modelo"] = MODELO_NAIVE
    salida["version_modelo"] = "ultimo_real_lote_v1"
    salida["componentes"] = salida["emitio_prediccion"].map(
        lambda emitio: {"emitio_prediccion": bool(emitio), "usa_solo_semana_anterior": True}
    )
    return salida


def _contrato(tabla: pd.DataFrame) -> pd.DataFrame:
    salida = tabla.copy()
    salida["fecha_emision"] = pd.to_datetime(salida["fecha_emision"]).dt.normalize()
    salida["fecha_objetivo"] = pd.to_datetime(salida["fecha_objetivo"]).dt.normalize()
    salida["horizonte_semanas"] = 1
    salida["banda_horizonte"] = "operativo"
    salida["p10_kg"] = np.nan
    salida["p90_kg"] = np.nan
    salida["tipo_prediccion"] = "replay"
    salida["es_replay_ciego"] = True
    salida["es_curva_stitched"] = True
    salida["estado_evaluacion"] = "evaluada"
    salida["confianza"] = salida.get("confianza", "baja")
    return salida


def _metricas_modelo(tabla: pd.DataFrame, modelo: str, campania: str) -> dict:
    parte = tabla[tabla.modelo.eq(modelo)].copy()
    cobertura = metricas_cobertura_operacional(parte)
    semanal = parte.groupby("fecha_objetivo", as_index=False).agg(
        real_kg=("real_kg", "sum"), p50_kg=("p50_kg", "sum")
    )
    semanal["modelo"] = modelo
    semanal["banda_horizonte"] = "operativo"
    semanal["serie_id"] = campania
    semanal["p10_kg"] = np.nan
    semanal["p90_kg"] = np.nan
    diagnostico = metricas_pronostico(semanal).iloc[0].to_dict()
    return {
        "modelo": modelo,
        "campania": campania,
        "banda_horizonte": "operativo",
        "n": int(len(semanal)),
        **{k: v for k, v in diagnostico.items() if k not in {"modelo", "banda_horizonte", "n"}},
        "wape_semanal": diagnostico.get("wape"),
        "wape_operacional_lote_semana": cobertura["wape_operacional"],
        "wape_condicionado_lote_semana": cobertura["wape_condicionado"],
        **cobertura,
    }


def construir_corrida() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    macro, r09, ultimos_reales = _leer_fuentes()
    salidas: list[pd.DataFrame] = []
    metricas: list[dict] = []
    for campania, base in macro.groupby("campania", sort=True):
        base = base.copy().sort_values(["fecha_objetivo", "lote_id"])
        base["emitio_prediccion"] = True
        base["modelo"] = MODELO_MACRO
        base["version_modelo"] = "macro_legacy_postgres_auto_asof_v2"
        base["componentes"] = base.get("componentes", pd.Series([{}] * len(base))).map(
            lambda valor: {**(valor if isinstance(valor, dict) else {}), "emitio_prediccion": True}
        )
        v1, _ = ejecutar_replay_hibrido_ocurrencia(base)
        v2, _ = ejecutar_replay_hibrido_ocurrencia_v2(base)
        referencias = _expandir_referencia(base, r09[r09.campania.eq(campania)], MODELO_R09)
        modelos = [
            _contrato(base),
            _contrato(referencias),
            _contrato(_expandir_v1(base, v1)),
            _contrato(v2),
            _contrato(_naive(base)),
        ]
        bloque = pd.concat(modelos, ignore_index=True, sort=False)
        if bloque.duplicated(["modelo", *CLAVES]).any():
            raise ValueError(f"Duplicados en el universo común de {campania}")
        salidas.append(bloque)
        for modelo in (MODELO_R09, MODELO_MACRO, MODELO_V1, MODELO_V2, MODELO_NAIVE):
            metricas.append(_metricas_modelo(bloque, modelo, str(campania)))

    predicciones = pd.concat(salidas, ignore_index=True, sort=False)
    tabla_metricas = pd.DataFrame(metricas)
    resumen = {
        "snapshot_id": SNAPSHOT_ID,
        "runs_origen": RUNS_ORIGEN,
        "ultima_fecha_real": ultimos_reales,
        "modelos": [MODELO_R09, MODELO_MACRO, MODELO_V1, MODELO_V2, MODELO_NAIVE],
        "campanias": sorted(predicciones.campania.unique()),
        "filas_por_modelo": predicciones.groupby("modelo").size().to_dict(),
        "metricas": tabla_metricas[
            [
                "campania",
                "modelo",
                "n",
                "wape_operacional",
                "wape_condicionado",
                "wape_semanal",
                "wape_operacional_lote_semana",
                "wape_condicionado_lote_semana",
                "mase",
                "rmsse",
                "mae_kg",
                "sesgo_pct",
                "cobertura_lotes",
                "cobertura_volumen",
                "volumen_real_kg",
            ]
        ].to_dict("records"),
    }
    return predicciones, tabla_metricas, resumen


def persistir(dry_run: bool = False) -> dict:
    predicciones, metricas, resumen = construir_corrida()
    if dry_run:
        return resumen
    repo = RepositorioAnalytics(settings.postgres_dsn())
    run_id = repo.crear_run(
        SNAPSHOT_ID,
        "backtest",
        {
            "modelo_hibrido": MODELO_V2,
            "version_modelo": VERSION_V2,
            "universo": "rejilla_completa_MacroLegacy_h1_semana_cerrada",
            "r09": "referencia_publicada_expandida_sin_usarse_como_predictor",
            "semanas_parciales": "excluidas_hasta_domingo_cerrado",
            "runs_origen": RUNS_ORIGEN,
        },
    )
    try:
        repo.guardar_predicciones(run_id, predicciones)
        repo.guardar_metricas(run_id, metricas)
        repo.finalizar_run(run_id, "succeeded")
    except Exception as exc:
        repo.finalizar_run(run_id, "failed", str(exc))
        raise
    resumen["run_id"] = run_id
    return resumen


__all__ = [
    "CLAVES",
    "MODELO_MACRO",
    "MODELO_NAIVE",
    "MODELO_R09",
    "RUNS_ORIGEN",
    "SNAPSHOT_ID",
    "construir_corrida",
    "persistir",
]

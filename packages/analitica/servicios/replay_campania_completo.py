"""Construye y persiste un replay as-of completo para una campaña cerrada.

El replay histórico de R09 no puede cubrir una campaña completa cuando Access solo
conserva unas pocas emisiones. Este script crea emisiones técnicas semanales, una
semana antes de cada cierre real, y vuelve a ejecutar MacroLegacy + OcurrenciaOnline
sin leer ningún dato posterior al corte. Esas emisiones son un instrumento de
validación, no una reconstrucción ficticia de lo que el agrónomo publicó.

La corrida final conserva los modelos de las campañas que ya estaban en la última
corrida exitosa y reemplaza únicamente la campaña solicitada por el replay completo.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from analitica import settings
from analitica.proyeccion.fuentes import cargar_datos
from analitica.proyeccion.gobernanza import RepositorioAnalytics
from analitica.proyeccion.hibrido_legacy import backtest_macro_legacy_v1
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
from analitica.proyeccion.metricas import metricas_cobertura_operacional, metricas_pronostico
from analitica.servicios.replay import (
    emisiones_completas,
    normalizar_modelo,
    semanas_cerradas,
)

# Este contrato es deliberadamente el del script histórico. A diferencia de
# persistir_replay_campania, usa un snapshot fijo, lee la corrida origen para conservar
# R09/otras campañas y persiste cuatro familias (Macro, v1, v2 y Naive).
MODELO_R09 = "R09_publicado"
MODELO_MACRO = "MacroLegacy_v1"
MODELO_NAIVE = "Naive_lag1"
SNAPSHOT_ID = 40
RUN_ORIGEN = 76
CLAVES = ["campania", "lote_id", "fecha_objetivo"]


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campania", default="C2025")
    parser.add_argument("--max-targets", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-run", type=int, default=RUN_ORIGEN)
    return parser.parse_args()


def _marcar_macro(macro: pd.DataFrame) -> pd.DataFrame:
    salida = macro.copy()
    salida["modelo"] = MODELO_MACRO
    salida["version_modelo"] = "macro_legacy_postgres_auto_asof_full_campaign"
    salida["emitio_prediccion"] = True
    salida["tipo_prediccion"] = "replay"
    salida["es_replay_ciego"] = True
    salida["es_curva_stitched"] = True
    salida["estado_evaluacion"] = "evaluada"
    salida["origen_emision"] = salida["fecha_emision"]
    salida["componentes"] = salida.get(
        "componentes", pd.Series([{} for _ in range(len(salida))], index=salida.index)
    ).map(
        lambda valor: {
            **(valor if isinstance(valor, dict) else {}),
            "emitio_prediccion": True,
            "emision_replay": "sintetica_asof",
        }
    )
    return salida


def _expandir_v1(base: pd.DataFrame, v1: pd.DataFrame) -> pd.DataFrame:
    # v1 descarta el calentamiento. Para que la comparación no convierta una ausencia
    # en un cero, se conserva MacroLegacy durante esas primeras semanas y se etiqueta.
    claves = ["campania", "lote_id", "fecha_objetivo"]
    salida = base.copy()
    if v1.empty:
        v1 = pd.DataFrame(columns=claves + ["p50_kg", "componentes", "confianza"])
    for columna in ("p50_kg", "componentes", "confianza"):
        if columna not in v1:
            v1[columna] = np.nan
    reemplazo = v1[claves + ["p50_kg", "componentes", "confianza"]].rename(
        columns={"p50_kg": "p50_v1", "componentes": "componentes_v1", "confianza": "confianza_v1"}
    )
    salida = salida.merge(reemplazo, on=claves, how="left", validate="1:1")
    salida["p50_kg"] = salida["p50_v1"].fillna(salida["p50_kg"])
    salida["p10_kg"] = np.nan
    salida["p90_kg"] = np.nan
    salida["modelo"] = MODELO_V1
    salida["version_modelo"] = VERSION_V1
    salida["tipo_prediccion"] = "replay"
    salida["es_replay_ciego"] = True
    salida["es_curva_stitched"] = True
    salida["estado_evaluacion"] = "evaluada"
    salida["origen_emision"] = salida["fecha_emision"]
    salida["emitio_prediccion"] = True
    salida["confianza"] = salida["confianza_v1"].fillna("baja")
    salida["componentes"] = salida.apply(
        lambda fila: {
            "modelo_base": MODELO_MACRO,
            "emitio_prediccion": True,
            "estado_correccion": "ocurrencia_online"
            if pd.notna(fila.get("p50_v1"))
            else "calentamiento_base",
            "calentamiento_base": pd.isna(fila.get("p50_v1")),
        },
        axis=1,
    )
    return salida.drop(columns=["p50_v1", "componentes_v1", "confianza_v1"], errors="ignore")


def _naive(base: pd.DataFrame) -> pd.DataFrame:
    salida = base.copy().sort_values(["lote_id", "fecha_objetivo"])
    salida["p50_kg"] = salida.groupby("lote_id", sort=False)["real_kg"].shift(1).fillna(0.0)
    salida["p10_kg"] = np.nan
    salida["p90_kg"] = np.nan
    salida["modelo"] = MODELO_NAIVE
    salida["version_modelo"] = "ultimo_real_lote_v1"
    salida["tipo_prediccion"] = "replay"
    salida["es_replay_ciego"] = True
    salida["es_curva_stitched"] = True
    salida["estado_evaluacion"] = "evaluada"
    salida["origen_emision"] = salida["fecha_emision"]
    salida["emitio_prediccion"] = True
    salida["componentes"] = salida["real_kg"].map(
        lambda _: {"usa_solo_real_anterior": True, "emitio_prediccion": True}
    )
    return salida


def _metricas(tabla: pd.DataFrame) -> pd.DataFrame:
    filas: list[dict] = []
    for (campania, modelo), parte in tabla.groupby(["campania", "modelo"], sort=True):
        semanal = parte.groupby("fecha_objetivo", as_index=False).agg(
            real_kg=("real_kg", "sum"), p50_kg=("p50_kg", "sum")
        )
        semanal["modelo"] = modelo
        semanal["banda_horizonte"] = "operativo"
        semanal["serie_id"] = str(campania)
        semanal["p10_kg"] = np.nan
        semanal["p90_kg"] = np.nan
        metricas = metricas_pronostico(semanal)
        if metricas.empty:
            continue
        fila = metricas.iloc[0].to_dict()
        cobertura = metricas_cobertura_operacional(parte)
        fila.update({"campania": str(campania), **cobertura})
        filas.append(fila)
    return pd.DataFrame(filas)


def _leer_anterior(repo_dsn: str, run_id: int, campania: str) -> pd.DataFrame:
    import psycopg

    consulta = """
        SELECT p.*
        FROM analytics.prediction p
        WHERE p.run_id = %s
    """
    with psycopg.connect(repo_dsn) as conexion:
        return pd.read_sql_query(consulta, conexion, params=(run_id,))


def construir(
    campania: str, max_targets: int | None, run_origen: int
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    datos = cargar_datos("postgres")
    emisiones = emisiones_completas(datos, campania, max_targets)
    macro, advertencias = backtest_macro_legacy_v1(
        datos,
        emisiones,
        campania=campania,
        horizonte_semanas=1,
        max_cortes=None,
    )
    if macro.empty:
        raise RuntimeError(f"MacroLegacy no generó filas para {campania}: {advertencias}")
    macro = normalizar_modelo(_marcar_macro(macro))
    v2, resumen_v2 = ejecutar_replay_hibrido_ocurrencia_v2(macro)
    v2 = normalizar_modelo(v2)
    v1_raw, _ = ejecutar_replay_hibrido_ocurrencia(macro)
    v1 = normalizar_modelo(_expandir_v1(macro, v1_raw))
    naive = normalizar_modelo(_naive(macro))
    actuales = [macro, v1, v2, naive]
    dsn = settings.postgres_dsn()
    anterior = _leer_anterior(dsn, run_origen, campania)
    if not anterior.empty:
        # Conservar la referencia publicada de C2025 que sí existe y todos los modelos
        # de las otras campañas. Las filas C2025 automáticas se reemplazan por el replay
        # completo para no dejar mezcladas dos definiciones del universo.
        r09 = anterior[anterior.modelo.eq(MODELO_R09)].copy()
        otras = anterior[
            ~anterior.modelo.eq(MODELO_R09) & ~anterior.campania.astype(str).eq(str(campania))
        ].copy()
        actuales.append(r09)
        base_final = pd.concat([otras, *actuales], ignore_index=True, sort=False)
    else:
        base_final = pd.concat(actuales, ignore_index=True, sort=False)
    # El run anterior puede contener la misma campaña R09; las automáticas nuevas solo
    # deben ser únicas dentro de modelo/campaña/lote/objetivo.
    if base_final.duplicated(["modelo", *CLAVES]).any():
        repetidas = base_final[base_final.duplicated(["modelo", *CLAVES], keep=False)]
        raise ValueError(f"Duplicados en corrida consolidada: {len(repetidas)}")
    metricas = _metricas(base_final)
    resumen = {
        "campania": campania,
        "emisiones_sinteticas": int(len(emisiones)),
        "semanas_objetivo": int(len(emisiones)),
        "filas_campania": int(sum(len(x) for x in actuales if not x.empty)),
        "filas_total": int(len(base_final)),
        "max_real": str(
            pd.to_datetime(
                datos.cosecha.loc[datos.cosecha.campania.astype(str).eq(str(campania)), "fecha"]
            )
            .max()
            .date()
        ),
        "metricas": metricas[metricas.campania.astype(str).eq(str(campania))].to_dict("records"),
        "advertencias": advertencias,
        "resumen_v2": resumen_v2.to_dict("records"),
    }
    return base_final, metricas, resumen


def persistir(args: argparse.Namespace) -> dict:
    predicciones, metricas, resumen = construir(args.campania, args.max_targets, args.keep_run)
    if args.dry_run:
        return resumen
    repo = RepositorioAnalytics(settings.postgres_dsn())
    run_id = repo.crear_run(
        SNAPSHOT_ID,
        "backtest",
        {
            "modelo_hibrido": MODELO_V2,
            "version_modelo": VERSION_V2,
            "campania_reconstruida": args.campania,
            "universo": "campania_completa_asof_semanal",
            "emisiones": "sinteticas_lunes_previo_al_cierre",
            "run_origen_conservado": args.keep_run,
            "r09": "referencia_publicada_no_algoritmo",
            "sin_datos_futuros": True,
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


# Reexports de compatibilidad para consumidores que usaban los nombres
# privados del script durante la migración interna.
_semanas_cerradas = semanas_cerradas
_emisiones_completas = emisiones_completas
_normalizar_modelo = normalizar_modelo

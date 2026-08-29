"""Genera y persiste un replay completo, una campaña por ejecución.

El script es deliberadamente explícito: R09 es una emisión publicada de referencia;
``MacroLegacy_v1`` y ``HibridoLegacyResidual_v1`` se generan con el mismo snapshot y
solo se comparan cuando comparten lote, emisión y semana objetivo. No abre Excel ni
usa una emisión posterior como predictor.

Uso:
    python -m analitica.scripts.persistir_replay_campania --campania C2024

La ejecución no limita cortes por defecto. ``--max-cortes`` solo sirve para una prueba
rápida y no debe usarse para la corrida que se vaya a presentar.
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

from analitica import settings
from analitica.proyeccion.backtest import construir_backtest
from analitica.proyeccion.calidad import controles_predicciones
from analitica.proyeccion.fuentes import cargar_datos
from analitica.proyeccion.gobernanza import RepositorioAnalytics
from analitica.proyeccion.hibrido_legacy import (
    NOMBRE_MODELO,
    VERSION_MODELO,
    backtest_hibrido_v1,
    backtest_macro_legacy_v1,
)
from analitica.proyeccion.metricas import metricas_pareadas_modelos, metricas_pronostico

MODELO_MACRO = "MacroLegacy_v1"
MODELO_R09 = "R09_publicado"


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campania", required=True, help="Campaña exacta, por ejemplo C2024")
    parser.add_argument("--horizonte-semanas", type=int, default=10)
    parser.add_argument(
        "--max-cortes",
        type=int,
        default=0,
        help="0 = todos los cortes evaluables; usar un valor positivo solo para smoke tests",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="genera y calcula métricas, pero no crea ni escribe una corrida",
    )
    return parser.parse_args()


def _completar_prediccion(
    tabla: pd.DataFrame,
    *,
    modelo: str,
    version_modelo: str,
    version_fuente: str | None = None,
) -> pd.DataFrame:
    """Aplica el contrato común antes de concatenar modelos."""

    if tabla.empty:
        return tabla.copy()
    salida = tabla.copy()
    salida["modelo"] = modelo
    if "version_modelo" not in salida or salida["version_modelo"].isna().all():
        salida["version_modelo"] = version_modelo
    else:
        salida["version_modelo"] = salida["version_modelo"].fillna(version_modelo)
    if version_fuente is not None:
        salida["version_fuente"] = version_fuente
    salida["fecha_emision"] = pd.to_datetime(salida.fecha_emision).dt.normalize()
    salida["fecha_objetivo"] = pd.to_datetime(salida.fecha_objetivo).dt.normalize()
    salida["origen_emision"] = salida["fecha_emision"]
    salida["tipo_prediccion"] = "replay"
    salida["es_replay_ciego"] = True
    salida["es_curva_stitched"] = False
    salida["estado_evaluacion"] = np.where(salida["real_kg"].notna(), "evaluada", "pendiente")
    return salida


def _emisiones_r09(backtest: pd.DataFrame, campania: str) -> pd.DataFrame:
    r09 = backtest[backtest.campania.astype(str).eq(campania) & backtest.modelo.eq(MODELO_R09)]
    return r09[["campania", "fecha_emision"]].drop_duplicates().reset_index(drop=True)


def construir_replay(
    datos, campania: str, horizonte: int, max_cortes: int
) -> tuple[pd.DataFrame, dict]:
    """Construye las tres familias sobre un único snapshot en memoria."""

    backtest = construir_backtest(datos.forecast, datos.cosecha)
    campania = str(campania)
    r09 = backtest[
        backtest.campania.astype(str).eq(campania) & backtest.modelo.eq(MODELO_R09)
    ].copy()
    emisiones = _emisiones_r09(backtest, campania)
    if emisiones.empty:
        raise ValueError(f"No existen emisiones R09 publicadas para {campania}.")

    limite = None if max_cortes == 0 else max_cortes
    inicio = time.perf_counter()
    macro, advertencias_macro = backtest_macro_legacy_v1(
        datos,
        emisiones,
        campania=campania,
        horizonte_semanas=horizonte,
        max_cortes=limite,
    )
    segundos_macro = time.perf_counter() - inicio

    inicio = time.perf_counter()
    hibrido, advertencias_hibrido = backtest_hibrido_v1(
        datos,
        emisiones,
        campania=campania,
        horizonte_semanas=horizonte,
        max_cortes=limite,
    )
    segundos_hibrido = time.perf_counter() - inicio

    # La caché de parámetros as-of queda en ``datos``: el híbrido reutiliza la
    # calibración que ya hizo MacroLegacy, sin modificar el conjunto de información.
    tablas = [
        _completar_prediccion(
            r09,
            modelo=MODELO_R09,
            version_modelo="emision_publicada_no_algoritmo",
            version_fuente="R09_PostgreSQL_snapshot",
        ),
        _completar_prediccion(
            macro,
            modelo=MODELO_MACRO,
            version_modelo="macro_legacy_reconstruida_v2",
        ),
        _completar_prediccion(
            hibrido,
            modelo=NOMBRE_MODELO,
            version_modelo=VERSION_MODELO,
        ),
    ]
    persistir = pd.concat(
        [tabla for tabla in tablas if not tabla.empty], ignore_index=True, sort=False
    )
    clave = ["modelo", "campania", "lote_id", "fecha_emision", "fecha_objetivo", "version_fuente"]
    duplicados = persistir.duplicated(clave, keep=False)
    if duplicados.any():
        raise ValueError(f"El replay generó {int(duplicados.sum())} predicciones duplicadas.")

    resumen = {
        "campania": campania,
        "emisiones_r09": int(len(emisiones)),
        "cortes_macro": int(macro.fecha_emision.nunique()) if not macro.empty else 0,
        "cortes_hibrido": int(hibrido.fecha_emision.nunique()) if not hibrido.empty else 0,
        "filas": {
            modelo: int(len(persistir[persistir.modelo.eq(modelo)]))
            for modelo in persistir.modelo.unique()
        },
        "segundos_macro": round(segundos_macro, 2),
        "segundos_hibrido": round(segundos_hibrido, 2),
        "advertencias": [*advertencias_macro, *advertencias_hibrido],
    }
    return persistir, resumen


def persistir_campania(
    campania: str, horizonte: int = 10, max_cortes: int = 0, dry_run: bool = False
) -> dict:
    dsn = settings.postgres_dsn()
    if not dsn:
        raise RuntimeError("No hay DSN de PostgreSQL configurado.")
    datos = cargar_datos("postgres")
    predicciones, resumen = construir_replay(datos, campania, horizonte, max_cortes)
    calidad = controles_predicciones(predicciones)
    errores = calidad[calidad.estado.eq("error")]
    if not errores.empty:
        raise ValueError(f"Controles de predicciones fallaron: {errores.to_dict('records')}")

    metricas = metricas_pronostico(predicciones)
    comparaciones = []
    for modelo in (MODELO_MACRO, NOMBRE_MODELO):
        comparacion = metricas_pareadas_modelos(
            predicciones,
            modelo_base=MODELO_R09,
            modelo_candidato=modelo,
        )
        if not comparacion.empty:
            comparaciones.append(comparacion)
    tabla_comparaciones = (
        pd.concat(comparaciones, ignore_index=True) if comparaciones else pd.DataFrame()
    )

    resumen["calidad"] = calidad.to_dict("records")
    resumen["metricas"] = metricas.to_dict("records")
    resumen["comparaciones"] = tabla_comparaciones.to_dict("records")
    resumen["filas_predicciones"] = int(len(predicciones))
    if dry_run:
        return resumen

    repo = RepositorioAnalytics(dsn)
    snapshot_id = repo.snapshot(datos)
    run_id = repo.crear_run(
        snapshot_id,
        "backtest",
        {
            "campania": str(campania),
            "modelos": [MODELO_R09, MODELO_MACRO, NOMBRE_MODELO],
            "horizonte_semanas": horizonte,
            "max_cortes": max_cortes,
            "replay": "rolling_origin_completo_por_campania",
            "r09": "emision_publicada_referencia_no_algoritmo",
            "fuente": datos.fuente.nombre,
        },
    )
    try:
        repo.guardar_predicciones(run_id, predicciones)
        repo.guardar_metricas(run_id, metricas)
        repo.guardar_metricas_comparacion(run_id, tabla_comparaciones)
        repo.guardar_calidad(snapshot_id, run_id, calidad)
        repo.finalizar_run(run_id, "succeeded")
    except Exception as exc:
        repo.finalizar_run(run_id, "failed", str(exc))
        raise
    resumen["run_id"] = run_id
    resumen["snapshot_id"] = snapshot_id
    return resumen


def resumir_salida_cli(resultado: dict) -> dict:
    """Conserva la salida compacta histórica de la interfaz de consola."""

    salida = dict(resultado)
    for clave in ("metricas", "comparaciones", "calidad"):
        valores = salida.pop(clave, [])
        salida[f"n_{clave}"] = len(valores)
        if clave == "comparaciones":
            salida["comparacion_resumen"] = [
                {
                    "modelo_base": fila.get("modelo_base"),
                    "modelo": fila.get("modelo"),
                    "banda": fila.get("banda_horizonte"),
                    "n": fila.get("n"),
                    "wape": fila.get("wape"),
                    "sesgo_pct": fila.get("sesgo_pct"),
                }
                for fila in valores
                if fila.get("modelo") != MODELO_R09
            ]
    return salida

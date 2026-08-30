"""Servicio de negocio para el screening prospectivo de deltas de parámetros.

El servicio contiene la orquestación del micro-replay y conserva como aliases
las utilidades históricas compartidas con los demás screenings de parámetros.
No depende de los módulos ejecutables para que la fachada CLI pueda permanecer
delgada y compatible.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from analitica.aplicacion.parametros import CandidateParamDelta
from analitica.aplicacion.servicios import parametros_replay as _parametros_replay

# Defaults y constantes históricas: se conservan por identidad con el
# servicio común que ya consumen los otros scripts de parámetros.
ACCESS_DEFAULT = _parametros_replay.ACCESS_DEFAULT
PARAMETROS_CALENDARIO = _parametros_replay.PARAMETROS_CALENDARIO
PARAMETROS_CURVA = _parametros_replay.PARAMETROS_CURVA
ROOT_DEFAULT = _parametros_replay.ROOT_DEFAULT
TRANSITIONS_DEFAULT = _parametros_replay.TRANSITIONS_DEFAULT

# Aliases privados históricos del script original.
_conexion_access = _parametros_replay.conexion_access
_columna_campania = _parametros_replay.columna_campania
_libros_semana = _parametros_replay.libros_semana
_normalizar_clave = _parametros_replay.normalizar_clave
_columna = _parametros_replay.columna
_preparar_lote = _parametros_replay.preparar_lote
_aplicar_modelo = _parametros_replay.aplicar_modelo
_proyectar_emision_detallada = _parametros_replay.proyectar_emision_detallada
_proyectar_emision = _parametros_replay.proyectar_emision

# Nombres públicos que quedaron expuestos por la fachada durante la extracción
# inicial de utilidades. También son aliases para no bifurcar implementaciones.
conexion_access = _conexion_access
columna_campania = _columna_campania
libros_semana = _libros_semana
normalizar_clave = _normalizar_clave
columna = _columna
preparar_lote = _preparar_lote
aplicar_modelo = _aplicar_modelo
proyectar_emision_detallada = _proyectar_emision_detallada
proyectar_emision = _proyectar_emision
cargar_reales_y_r09 = _parametros_replay.cargar_reales_y_r09
ejecutar_proyeccion_semanal_dataframe = _parametros_replay.ejecutar_proyeccion_semanal_dataframe
seleccionar_libros_parametros = _parametros_replay.seleccionar_libros_parametros
leer_libro_operativo = _parametros_replay.leer_libro_operativo


def _metricas(tabla: pd.DataFrame, columna: str) -> dict[str, float | int]:
    """Calcula las métricas semanales del candidato o de R09."""

    error = tabla[columna] - tabla.real_kg
    denominador = float(tabla.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / denominador),
        "sesgo": float(error.sum() / denominador),
        "mae_kg": float(error.abs().mean()),
        "n_semanas": int(len(tabla)),
    }


def ejecutar(
    *,
    root: Path = ROOT_DEFAULT,
    transitions: Path = TRANSITIONS_DEFAULT,
    access: Path = ACCESS_DEFAULT,
    campania: str = "C2026",
    emisiones: tuple[int, ...] = (28, 29, 32, 33),
) -> dict[str, object]:
    """Ejecuta el micro-replay prospectivo de deltas de parámetros."""

    transiciones = pd.read_parquet(transitions)
    transiciones = transiciones.loc[transiciones.fila_asof_utilizable.fillna(False)].copy()
    reales, r09 = cargar_reales_y_r09(access, campania)
    # Ablación inicial deliberadamente pequeña. La expansión de hiperparámetros
    # solo se ejecuta para el bloque ganador; así el micro-replay no se convierte
    # otra vez en una corrida de horas.
    configuraciones = [
        {"regularizacion": 8.0, "cuantiles": (0.15, 0.85), "bloque": bloque}
        for bloque in ("ninguno", "parametros")
    ]
    filas: list[dict[str, object]] = []
    cache_libros: dict[int, dict[str, tuple[pd.DataFrame, pd.DataFrame]]] = {}
    for configuracion_id, configuracion in enumerate(configuraciones, start=1):
        for emision in emisiones:
            entrenamiento = transiciones.loc[transiciones.semana_emision_actual.lt(emision)].copy()
            if entrenamiento.empty or (emision + 1) not in reales:
                continue
            modelo = CandidateParamDelta(
                regularizacion=configuracion["regularizacion"],
                cuantiles=configuracion["cuantiles"],
            ).fit(entrenamiento)
            prediccion, niveles = _proyectar_emision(
                root,
                modelo,
                semana_emision=emision,
                campania=campania,
                bloque=configuracion["bloque"],
                cache_libros=cache_libros,
            )
            filas.append(
                {
                    "configuracion_id": configuracion_id,
                    **configuracion,
                    "semana_emision": emision,
                    "semana_objetivo": emision + 1,
                    "real_kg": reales[emision + 1],
                    "candidato_kg": prediccion,
                    "r09_kg": r09.get((emision, emision + 1), np.nan),
                    "n_transiciones_entrenamiento": int(len(entrenamiento)),
                    "niveles": niveles,
                }
            )
    tabla = pd.DataFrame(filas)
    ranking: list[dict[str, object]] = []
    for configuracion_id, grupo in tabla.groupby("configuracion_id"):
        fila = grupo.iloc[0]
        metricas = _metricas(grupo, "candidato_kg")
        metricas_r09 = _metricas(grupo.dropna(subset=["r09_kg"]), "r09_kg")
        ranking.append(
            {
                "configuracion_id": int(configuracion_id),
                "bloque": fila.bloque,
                "regularizacion": float(fila.regularizacion),
                "cuantiles": list(fila.cuantiles),
                "candidato": metricas,
                "r09": metricas_r09,
                "gana_r09": bool(metricas["wape"] < metricas_r09["wape"]),
            }
        )
    ranking.sort(key=lambda item: item["candidato"]["wape"])
    return {
        "schema": "screening-parameter-delta-replay-v1",
        "descripcion": "Candidate-only; usa Sxx-1 y transiciones anteriores a Sxx.",
        "campania": campania,
        "emisiones": list(emisiones),
        "ranking": ranking,
        "detalle": tabla.to_dict("records"),
        "publicable": False,
    }


__all__ = [
    "ACCESS_DEFAULT",
    "CandidateParamDelta",
    "PARAMETROS_CALENDARIO",
    "PARAMETROS_CURVA",
    "ROOT_DEFAULT",
    "TRANSITIONS_DEFAULT",
    "aplicar_modelo",
    "cargar_reales_y_r09",
    "columna",
    "columna_campania",
    "conexion_access",
    "ejecutar",
    "ejecutar_proyeccion_semanal_dataframe",
    "leer_libro_operativo",
    "libros_semana",
    "normalizar_clave",
    "np",
    "pd",
    "preparar_lote",
    "proyectar_emision",
    "proyectar_emision_detallada",
    "seleccionar_libros_parametros",
]

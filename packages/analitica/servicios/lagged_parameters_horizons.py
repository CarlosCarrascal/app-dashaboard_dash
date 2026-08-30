"""Servicio de negocio para el screening de parámetros rezagados por horizonte.

La implementación vive aquí para que el script ejecutable conserve únicamente
la fachada CLI. Los aliases de las utilidades compartidas mantienen la
compatibilidad con los nombres históricos del screening.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analitica.proyeccion.candidatos import escribir_json_reproducible
from analitica.proyeccion.motor_proyeccion_semanal import ejecutar_proyeccion_semanal_dataframe
from analitica.proyeccion.operativo import leer_libro_operativo
from analitica.proyeccion.parametros_excel import seleccionar_libros_parametros
from analitica.servicios import parametros_replay as _parametros_replay

ACCESS_DEFAULT = _parametros_replay.ACCESS_DEFAULT
ROOT_DEFAULT = _parametros_replay.ROOT_DEFAULT
cargar_reales_y_r09 = _parametros_replay.cargar_reales_y_r09


def _libros(root: Path, semana: int) -> dict[str, Path]:
    seleccionados, _ = seleccionar_libros_parametros(root, semanas=(semana,))
    return {
        str(fila.fundo_operativo): Path(str(fila.ruta_fuente))
        for fila in seleccionados.itertuples()
    }


def ejecutar(
    *,
    root: Path = ROOT_DEFAULT,
    access: Path = ACCESS_DEFAULT,
    campania: str = "C2026",
    emisiones: tuple[int, ...] = (26, 27, 28, 29, 32, 33),
    ultima_semana_cerrada: int = 34,
) -> dict[str, object]:
    reales, r09 = cargar_reales_y_r09(access, campania)
    filas: list[dict[str, object]] = []
    for emision in emisiones:
        partes = []
        for fundo, ruta in _libros(root, emision - 1).items():
            parametros, panel, _ = leer_libro_operativo(ruta)
            motor = ejecutar_proyeccion_semanal_dataframe(
                parametros,
                panel,
                campana=campania,
                fundo_nombre=fundo,
            )
            motor = motor.copy()
            motor["semana_objetivo"] = pd.to_datetime(motor.FeCos).dt.isocalendar().week.astype(int)
            motor["fundo_operativo"] = fundo
            partes.append(motor)
        predicciones = pd.concat(partes, ignore_index=True)
        agregada = predicciones.groupby("semana_objetivo", as_index=False).Kg.sum()
        for fila in agregada.itertuples():
            objetivo = int(fila.semana_objetivo)
            horizonte = objetivo - emision
            if horizonte < 1 or horizonte > 6 or objetivo > ultima_semana_cerrada:
                continue
            if objetivo not in reales:
                continue
            filas.append(
                {
                    "campania": campania,
                    "semana_emision": emision,
                    "semana_parametros": emision - 1,
                    "semana_objetivo": objetivo,
                    "horizonte": horizonte,
                    "real_kg": reales[objetivo],
                    "lagged_kg": float(fila.Kg),
                    "r09_kg": r09.get((emision, objetivo)),
                }
            )
    tabla = pd.DataFrame(filas)
    resumen = []
    for horizonte, grupo in tabla.groupby("horizonte"):
        fila = {"horizonte": int(horizonte), "n": int(len(grupo))}
        for nombre, columna in (("lagged", "lagged_kg"), ("r09", "r09_kg")):
            parte = grupo.dropna(subset=[columna])
            error = parte[columna] - parte.real_kg
            denom = float(parte.real_kg.abs().sum())
            fila[nombre] = {
                "wape": float(error.abs().sum() / denom),
                "sesgo": float(error.sum() / denom),
                "mae_kg": float(error.abs().mean()),
                "n": int(len(parte)),
            }
        resumen.append(fila)
    for etiqueta, filtro in (
        ("h1_2", tabla.horizonte.le(2)),
        ("h3_6", tabla.horizonte.between(3, 6)),
        ("todos", pd.Series(True, index=tabla.index)),
    ):
        grupo = tabla.loc[filtro]
        fila = {"horizonte": etiqueta, "n": int(len(grupo))}
        for nombre, columna in (("lagged", "lagged_kg"), ("r09", "r09_kg")):
            parte = grupo.dropna(subset=[columna])
            error = parte[columna] - parte.real_kg
            denom = float(parte.real_kg.abs().sum())
            fila[nombre] = {
                "wape": float(error.abs().sum() / denom),
                "sesgo": float(error.sum() / denom),
                "mae_kg": float(error.abs().mean()),
                "n": int(len(parte)),
            }
        resumen.append(fila)
    return {
        "schema": "screening-lagged-parameters-horizons-v1",
        "descripcion": "Sxx-1 predice destinos posteriores de Sxx; candidate-only.",
        "ultima_semana_cerrada": ultima_semana_cerrada,
        "resumen": resumen,
        "detalle": tabla.to_dict("records"),
        "publicable": False,
    }


__all__ = [
    "ACCESS_DEFAULT",
    "ROOT_DEFAULT",
    "cargar_reales_y_r09",
    "ejecutar",
    "ejecutar_proyeccion_semanal_dataframe",
    "escribir_json_reproducible",
    "leer_libro_operativo",
    "pd",
    "seleccionar_libros_parametros",
]

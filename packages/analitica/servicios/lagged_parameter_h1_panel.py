"""Servicio de negocio para construir la caché lagged de parámetros H1.

Cada emisión ``S`` usa exclusivamente el libro canónico ``S-1``. La salida no
contiene cosecha real ni R09: esos datos se incorporan después de proyectar, en
el evaluador. De este modo la caché puede reutilizarse sin contaminar el
modelo.

La lectura de los libros Excel se mantiene delegada al lector operativo, que
resuelve ``python-calamine`` únicamente cuando se necesita abrir un libro.
Importar este servicio no requiere ``python-calamine`` ni ``pyodbc``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analitica.proyeccion.motor_proyeccion_semanal import (
    ejecutar_proyeccion_semanal_dataframe,
)
from analitica.proyeccion.parametros_excel import seleccionar_libros_parametros
from analitica.proyeccion.validacion_operativa import leer_libro_operativo

ROOT_DEFAULT = Path(r"C:\Users\CCARRASCAL\Downloads\Proyecciones")


def construir(
    *,
    root: Path = ROOT_DEFAULT,
    campania: str = "C2026",
    semanas_fuente: tuple[int, ...] = tuple(range(1, 34)),
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Construye el panel candidate-only con parámetros de ``S-1`` para H1."""

    manifiesto, faltantes = seleccionar_libros_parametros(root, semanas=semanas_fuente)
    filas: list[dict[str, object]] = []
    errores: list[dict[str, object]] = []

    for fuente in manifiesto.sort_values(["semana_emision", "fundo_operativo"]).itertuples():
        semana_parametros = int(fuente.semana_emision)
        semana_emision = semana_parametros + 1
        semana_objetivo = semana_emision + 1
        try:
            parametros, panel, _ = leer_libro_operativo(Path(str(fuente.ruta_fuente)))
            motor = ejecutar_proyeccion_semanal_dataframe(
                df_parametros=parametros,
                df_panel=panel,
                campana=campania,
                fundo_nombre=str(fuente.fundo_operativo),
            ).copy()
            semanas = pd.to_datetime(motor["FeCos"]).dt.isocalendar().week.astype(int)
            bloque = motor.loc[semanas.eq(semana_objetivo)].copy()
            filas.append(
                {
                    "campania": campania,
                    "semana_parametros": semana_parametros,
                    "semana_emision": semana_emision,
                    "semana_objetivo": semana_objetivo,
                    "horizonte": 1,
                    "fundo_operativo": str(fuente.fundo_operativo),
                    "lagged_kg": float(bloque["Kg"].sum()),
                    "n_filas_motor": int(len(bloque)),
                    "archivo_fuente": str(fuente.archivo_fuente),
                    "ruta_fuente": str(fuente.ruta_fuente),
                    "sha256_fuente": str(fuente.sha256_fuente),
                    "variante": str(fuente.variante),
                }
            )
        except Exception as exc:  # pragma: no cover - diagnóstico de archivos reales
            errores.append(
                {
                    "semana_parametros": semana_parametros,
                    "fundo_operativo": str(fuente.fundo_operativo),
                    "archivo_fuente": str(fuente.archivo_fuente),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    tabla = pd.DataFrame(filas).sort_values(["semana_objetivo", "fundo_operativo"], kind="stable")
    if tabla.duplicated(["campania", "semana_emision", "semana_objetivo", "fundo_operativo"]).any():
        raise ValueError("La caché lagged contiene llaves emisión-objetivo-fundo duplicadas")
    metadatos = {
        "schema": "lagged-parameter-h1-cache-v1",
        "campania": campania,
        "descripcion": "S-1 parámetros canónicos -> emisión S -> objetivo S+1",
        "n_filas": int(len(tabla)),
        "semanas_parametros": sorted(map(int, tabla.semana_parametros.unique()))
        if len(tabla)
        else [],
        "faltantes": faltantes.to_dict("records"),
        "errores": errores,
        "publicable": False,
    }
    return tabla, metadatos


__all__ = [
    "ROOT_DEFAULT",
    "construir",
    "ejecutar_proyeccion_semanal_dataframe",
    "leer_libro_operativo",
    "pd",
    "seleccionar_libros_parametros",
]

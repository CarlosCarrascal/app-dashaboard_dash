"""Servicio de negocio para construir la caché de parámetros expertos H1.

Una carpeta ``S`` representa la corrida editada/publicada durante la semana S.
Por tanto, sus parámetros son temporalmente elegibles para pronosticar S+1,
siempre que el manifiesto haya certificado la fecha de esa corrida. La caché no
contiene cosecha real ni R09 y nunca publica resultados.

La lectura de los libros operativos conserva sus dependencias opcionales: la
función que usa ``python-calamine`` se importa, pero solo intenta cargar esa
dependencia al leer un libro.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analitica.proyeccion.motor_proyeccion_semanal import ejecutar_proyeccion_semanal_dataframe
from analitica.proyeccion.operativo import leer_libro_operativo
from analitica.proyeccion.parametros_excel import seleccionar_libros_parametros

ROOT_DEFAULT = Path(r"C:\Users\CCARRASCAL\Downloads\Proyecciones")
SEMANAS_CERTIFICADAS = (24, 25, 26, 27, 28, 29, 31, 32, 33, 34)


def construir(
    *,
    root: Path = ROOT_DEFAULT,
    campania: str = "C2026",
    semanas_fuente: tuple[int, ...] = SEMANAS_CERTIFICADAS,
) -> tuple[pd.DataFrame, dict[str, object]]:
    manifiesto, faltantes = seleccionar_libros_parametros(root, semanas=semanas_fuente)
    filas: list[dict[str, object]] = []
    errores: list[dict[str, object]] = []
    for fuente in manifiesto.sort_values(["semana_emision", "fundo_operativo"]).itertuples():
        semana_emision = int(fuente.semana_emision)
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
            bloque = motor.loc[semanas.eq(semana_objetivo)]
            filas.append(
                {
                    "campania": campania,
                    "semana_parametros": semana_emision,
                    "semana_emision": semana_emision,
                    "semana_objetivo": semana_objetivo,
                    "horizonte": 1,
                    "fundo_operativo": str(fuente.fundo_operativo),
                    "expert_kg": float(bloque["Kg"].sum()),
                    "n_filas_motor": int(len(bloque)),
                    "archivo_fuente": str(fuente.archivo_fuente),
                    "ruta_fuente": str(fuente.ruta_fuente),
                    "sha256_fuente": str(fuente.sha256_fuente),
                    "variante": str(fuente.variante),
                }
            )
        except Exception as exc:  # pragma: no cover - diagnóstico de fuentes reales
            errores.append(
                {
                    "semana_emision": semana_emision,
                    "fundo_operativo": str(fuente.fundo_operativo),
                    "archivo_fuente": str(fuente.archivo_fuente),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    tabla = pd.DataFrame(filas).sort_values(["semana_objetivo", "fundo_operativo"], kind="stable")
    clave = ["campania", "semana_emision", "semana_objetivo", "fundo_operativo"]
    if tabla.duplicated(clave).any():
        raise ValueError("El panel experto contiene llaves emisión-objetivo-fundo duplicadas")
    metadatos = {
        "schema": "expert-parameter-h1-cache-v1",
        "campania": campania,
        "descripcion": "parámetros canónicos S disponibles en S -> objetivo S+1",
        "semanas_certificadas": list(semanas_fuente),
        "n_filas": int(len(tabla)),
        "faltantes": faltantes.to_dict("records"),
        "errores": errores,
        "publicable": False,
    }
    return tabla, metadatos


__all__ = [
    "ROOT_DEFAULT",
    "SEMANAS_CERTIFICADAS",
    "construir",
    "ejecutar_proyeccion_semanal_dataframe",
    "leer_libro_operativo",
    "pd",
    "seleccionar_libros_parametros",
]

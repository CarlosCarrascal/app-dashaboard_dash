"""Comparación auditable entre el motor y las salidas del libro operativo."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from ..compartido import sha256_archivo
from ..motor_proyeccion_semanal import ejecutar_proyeccion_semanal_dataframe
from .excel import (
    CAMPOS_NUMERICOS,
    CLAVES_CORRIDA,
    ResultadoValidacionOperativa,
    _campana_unica,
    _normalizar_claves,
    leer_libro_operativo,
)


def validar_libro_operativo(
    ruta: Path,
    *,
    fundo_nombre: str,
    tolerancia_absoluta: float = 0.01,
    tolerancia_relativa: float = 1e-6,
) -> ResultadoValidacionOperativa:
    """Valida un libro y clasifica las inconsistencias de fuente explícitamente."""
    ruta = Path(ruta)
    resultado = ResultadoValidacionOperativa(
        archivo=str(ruta),
        sha256=sha256_archivo(ruta),
    )

    parametros, panel, fuente = leer_libro_operativo(ruta)
    resultado.filas_fuente = len(fuente)
    resultado.metadatos.update(
        {
            "hoja_panel_filas": len(panel),
            "hoja_parametros_filas": len(parametros),
            "campana_fuente": _campana_unica(fuente),
            "panel_columnas_fepas": sorted(
                str(c) for c in panel.columns if str(c).strip().casefold().startswith("fepas")
            ),
        }
    )

    campana = _campana_unica(fuente)
    if campana is None:
        resultado.estado = "fuente_inconsistente"
        resultado.advertencias.append("BDProy no tiene una única campaña identificable")
        return resultado

    motor = ejecutar_proyeccion_semanal_dataframe(
        df_parametros=parametros,
        df_panel=panel,
        campana=campana,
        fundo_nombre=fundo_nombre,
    )
    resultado.filas_motor = len(motor)

    claves = [columna for columna in CLAVES_CORRIDA if columna in fuente and columna in motor]
    if len(claves) != len(CLAVES_CORRIDA):
        resultado.estado = "no_evaluable"
        resultado.advertencias.append("Faltan columnas de identidad para comparar la corrida")
        return resultado

    fuente_norm = _normalizar_claves(fuente)
    motor_norm = _normalizar_claves(motor)
    claves_fuente = set(map(tuple, fuente_norm[claves].itertuples(index=False, name=None)))
    claves_motor = set(map(tuple, motor_norm[claves].itertuples(index=False, name=None)))
    faltan_motor = claves_fuente - claves_motor
    sobran_motor = claves_motor - claves_fuente
    if faltan_motor or sobran_motor:
        resultado.estado = "fuente_inconsistente"
        resultado.advertencias.append(
            "Panel y BDProy no pertenecen a la misma corrida: "
            f"faltan {len(faltan_motor)} claves y sobran {len(sobran_motor)}"
        )
        resultado.metadatos.update(
            {
                "claves_faltantes_motor": len(faltan_motor),
                "claves_sobrantes_motor": len(sobran_motor),
            }
        )
        return resultado

    izquierda = fuente_norm[claves + CAMPOS_NUMERICOS].copy()
    derecha = motor_norm[claves + CAMPOS_NUMERICOS].copy()
    comparacion = izquierda.merge(
        derecha,
        on=claves,
        how="outer",
        suffixes=("_fuente", "_motor"),
        validate="one_to_one",
    )
    diferencias = []
    for campo in CAMPOS_NUMERICOS:
        a = pd.to_numeric(comparacion[f"{campo}_fuente"], errors="coerce")
        b = pd.to_numeric(comparacion[f"{campo}_motor"], errors="coerce")
        delta = (a - b).abs()
        resultado.max_diferencia[campo] = float(delta.max(skipna=True) or 0.0)
        escala = a.abs().clip(lower=1.0)
        diferencias.append((delta > tolerancia_absoluta) & ((delta / escala) > tolerancia_relativa))
    mascara = pd.concat(diferencias, axis=1).any(axis=1)
    resultado.diferencias_filas = int(mascara.sum())
    if resultado.diferencias_filas:
        resultado.estado = "mismatch"
        resultado.advertencias.append(
            f"{resultado.diferencias_filas} filas superan las tolerancias numéricas"
        )
    else:
        resultado.estado = "validado"
    return resultado


def validar_libros_semana(
    configuracion: Iterable[tuple[str, str]],
) -> pd.DataFrame:
    """Ejecuta validaciones y devuelve un reporte serializable para auditoría."""
    filas = []
    for archivo, fundo in configuracion:
        resultado = validar_libro_operativo(Path(archivo), fundo_nombre=fundo)
        filas.append(
            {
                "archivo": resultado.archivo,
                "modelo": resultado.modelo,
                "estado": resultado.estado,
                "sha256": resultado.sha256,
                "filas_fuente": resultado.filas_fuente,
                "filas_motor": resultado.filas_motor,
                "diferencias_filas": resultado.diferencias_filas,
                "max_diferencia": resultado.max_diferencia,
                "advertencias": resultado.advertencias,
                "metadatos": resultado.metadatos,
            }
        )
    return pd.DataFrame(filas)


__all__ = ["validar_libro_operativo", "validar_libros_semana"]

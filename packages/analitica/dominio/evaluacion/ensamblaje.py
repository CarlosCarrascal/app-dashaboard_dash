"""Auditoría de uniones y granularidad para paneles analíticos.

Este módulo no conoce hipótesis, modelos ni persistencia. Su única responsabilidad es
dejar evidencia de cada unión y fallar antes de que una duplicación infle una relación.
Las responsabilidades de relaciones se consumen desde ``relaciones_partes``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

AUDITORIA_ENSAMBLADO_COLUMNAS = (
    "paso",
    "unidad_salida",
    "claves_union",
    "tipo_union",
    "validacion_union",
    "filas_izquierda",
    "filas_derecha",
    "filas_salida",
    "filas_emparejadas",
    "filas_solo_izquierda",
    "filas_solo_derecha",
    "claves_izquierda_duplicadas",
    "claves_derecha_duplicadas",
    "filas_salida_duplicadas",
    "factor_expansion",
    "estado",
    "detalle",
)


def _filas_duplicadas(tabla: pd.DataFrame, claves: list[str]) -> int:
    if tabla.empty or not set(claves) <= set(tabla.columns):
        return 0
    return int(tabla.duplicated(claves, keep=False).sum())


def _claves_no_emparejadas(
    izquierda: pd.DataFrame, derecha: pd.DataFrame, claves: list[str]
) -> tuple[int, int]:
    """Cuenta claves distintas que no tienen correspondencia en el otro lado."""
    if not set(claves) <= set(izquierda.columns) or not set(claves) <= set(derecha.columns):
        return 0, 0
    izq = izquierda[claves].drop_duplicates()
    der = derecha[claves].drop_duplicates()
    comparacion = izq.merge(der, on=claves, how="outer", indicator=True)
    return (
        int((comparacion["_merge"] == "left_only").sum()),
        int((comparacion["_merge"] == "right_only").sum()),
    )


def _registrar_base(
    tabla: pd.DataFrame,
    *,
    auditoria: list[dict],
    nombre: str,
    unidad: str,
    grano: list[str],
) -> None:
    duplicadas = _filas_duplicadas(tabla, grano)
    auditoria.append(
        {
            "paso": nombre,
            "unidad_salida": unidad,
            "claves_union": ", ".join(grano),
            "tipo_union": "base",
            "validacion_union": "unique",
            "filas_izquierda": len(tabla),
            "filas_derecha": 0,
            "filas_salida": len(tabla),
            "filas_emparejadas": len(tabla),
            "filas_solo_izquierda": 0,
            "filas_solo_derecha": 0,
            "claves_izquierda_duplicadas": duplicadas,
            "claves_derecha_duplicadas": 0,
            "filas_salida_duplicadas": duplicadas,
            "factor_expansion": 1.0,
            "estado": "error" if duplicadas else "ok",
            "detalle": (
                f"La granularidad esperada es {unidad}; se detectaron "
                f"{duplicadas} filas duplicadas."
                if duplicadas
                else ""
            ),
        }
    )
    if duplicadas:
        raise ValueError(
            f"El paso {nombre} no es único en {unidad}: {duplicadas} filas duplicadas para {grano}."
        )


def _merge_auditado(
    izquierda: pd.DataFrame,
    derecha: pd.DataFrame,
    *,
    auditoria: list[dict],
    nombre: str,
    unidad: str,
    on: list[str],
    how: str,
    validate: str,
    grano_salida: list[str],
    suffixes: tuple[str, str] = ("_x", "_y"),
) -> pd.DataFrame:
    """Une dos paneles y deja evidencia de que la unión conservó su granularidad.

    ``validate`` convierte una unión muchos-a-muchos accidental en un error explícito antes
    de que una correlación vea filas infladas. La auditoría queda disponible para el
    dashboard como tabla de negocio.
    """
    filas_izquierda = len(izquierda)
    filas_derecha = len(derecha)
    duplicadas_izquierda = _filas_duplicadas(izquierda, on)
    duplicadas_derecha = _filas_duplicadas(derecha, on)
    solo_izquierda, solo_derecha = _claves_no_emparejadas(izquierda, derecha, on)
    marcador = f"__auditoria_merge_{len(auditoria)}"
    try:
        salida = izquierda.merge(
            derecha,
            on=on,
            how=how,
            validate=validate,
            indicator=marcador,
            sort=False,
            suffixes=suffixes,
        )
    except Exception as exc:
        auditoria.append(
            {
                "paso": nombre,
                "unidad_salida": unidad,
                "claves_union": ", ".join(on),
                "tipo_union": how,
                "validacion_union": validate,
                "filas_izquierda": filas_izquierda,
                "filas_derecha": filas_derecha,
                "filas_salida": 0,
                "filas_emparejadas": 0,
                "filas_solo_izquierda": solo_izquierda,
                "filas_solo_derecha": solo_derecha,
                "claves_izquierda_duplicadas": duplicadas_izquierda,
                "claves_derecha_duplicadas": duplicadas_derecha,
                "filas_salida_duplicadas": 0,
                "factor_expansion": np.nan,
                "estado": "error",
                "detalle": f"{type(exc).__name__}: {exc}",
            }
        )
        raise ValueError(f"La unión {nombre} no cumple {validate}: {exc}") from exc

    filas_emparejadas = int((salida[marcador] == "both").sum())
    filas_solo_izquierda = int((salida[marcador] == "left_only").sum())
    filas_solo_derecha = int((salida[marcador] == "right_only").sum())
    salida = salida.drop(columns=marcador)
    duplicadas_salida = _filas_duplicadas(salida, grano_salida)
    factor = len(salida) / filas_izquierda if filas_izquierda else np.nan
    estado = "error" if duplicadas_salida else "ok"
    detalle = (
        f"La granularidad {unidad} quedó duplicada en {duplicadas_salida} filas."
        if duplicadas_salida
        else ""
    )
    auditoria.append(
        {
            "paso": nombre,
            "unidad_salida": unidad,
            "claves_union": ", ".join(on),
            "tipo_union": how,
            "validacion_union": validate,
            "filas_izquierda": filas_izquierda,
            "filas_derecha": filas_derecha,
            "filas_salida": len(salida),
            "filas_emparejadas": filas_emparejadas,
            "filas_solo_izquierda": filas_solo_izquierda,
            "filas_solo_derecha": filas_solo_derecha,
            "claves_izquierda_duplicadas": duplicadas_izquierda,
            "claves_derecha_duplicadas": duplicadas_derecha,
            "filas_salida_duplicadas": duplicadas_salida,
            "factor_expansion": factor,
            "estado": estado,
            "detalle": detalle,
        }
    )
    if duplicadas_salida:
        raise ValueError(
            f"La unión {nombre} rompió la granularidad {unidad}: "
            f"{duplicadas_salida} filas duplicadas."
        )
    return salida


def _auditoria_dataframe(auditoria: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(auditoria, columns=AUDITORIA_ENSAMBLADO_COLUMNAS)


__all__ = [
    "AUDITORIA_ENSAMBLADO_COLUMNAS",
    "_auditoria_dataframe",
    "_claves_no_emparejadas",
    "_filas_duplicadas",
    "_merge_auditado",
    "_registrar_base",
]

"""Corrector online v2 con cobertura completa sobre ``MacroLegacy_v1``.

La versión 1 descartaba las semanas de calentamiento y se persistía sobre la
intersección con R09. Eso mezclaba precisión con falta de cobertura. Esta versión
mantiene una predicción para cada fila elegible de la curva biológica: durante el
calentamiento conserva la MacroLegacy y, después, aplica el corrector de ocurrencia
entrenado exclusivamente con semanas anteriores.

R09 no interviene en el cálculo. Solo se incorpora posteriormente como referencia
publicada sobre el mismo universo de evaluación.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from .hibrido_ocurrencia import (
    ConfiguracionHibridoOcurrencia,
    ejecutar_replay_hibrido_ocurrencia,
)

NOMBRE_MODELO = "HibridoOcurrenciaOnline_v2"
VERSION_MODELO = "macro_hurdle_online_full_coverage_v2"


def _clave(tabla: pd.DataFrame) -> pd.Series:
    return (
        tabla["campania"].astype(str)
        + "|"
        + tabla["lote_id"].astype(str)
        + "|"
        + pd.to_datetime(tabla["fecha_objetivo"]).dt.strftime("%Y-%m-%d")
    )


def _componentes_base(fila: pd.Series, estado: str) -> dict:
    existentes = fila.get("componentes")
    componentes = dict(existentes) if isinstance(existentes, dict) else {}
    componentes.update(
        {
            "modelo_base": "MacroLegacy_v1",
            "kg_legacy": float(fila["p50_kg"]),
            "estado_correccion": estado,
            "peso_legacy": 1.0,
            "semanas_entrenamiento": 0,
            "emitio_prediccion": True,
            "etiqueta_causal": False,
        }
    )
    return componentes


def ejecutar_replay_hibrido_ocurrencia_v2(
    curva_legacy: pd.DataFrame,
    config: ConfiguracionHibridoOcurrencia | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ejecuta el replay sin perder filas durante el calentamiento.

    El contrato de entrada debe representar una sola campaña y una fila única por
    lote-semana. La función rechaza duplicados para que la cobertura no se infle.
    """

    if curva_legacy.empty:
        return pd.DataFrame(), pd.DataFrame()
    config = config or ConfiguracionHibridoOcurrencia()
    config = replace(config, peso_curva_legacy=0.5)
    base = curva_legacy.copy()
    base["fecha_objetivo"] = pd.to_datetime(base["fecha_objetivo"], errors="raise")
    base["fecha_emision"] = pd.to_datetime(base["fecha_emision"], errors="raise")
    claves = ["campania", "lote_id", "fecha_objetivo"]
    if base.duplicated(claves).any():
        raise ValueError("La curva legacy repite campaña, lote y semana objetivo")
    if base["campania"].astype(str).nunique() != 1:
        raise ValueError("El replay v2 debe ejecutarse por campaña para conservar el as-of")

    corregido, _ = ejecutar_replay_hibrido_ocurrencia(base, config)
    claves_corregidas = set(_clave(corregido)) if not corregido.empty else set()
    calentamiento = base.loc[~_clave(base).isin(claves_corregidas)].copy()
    calentamiento["modelo"] = NOMBRE_MODELO
    calentamiento["version_modelo"] = VERSION_MODELO
    calentamiento["tipo_prediccion"] = "replay"
    calentamiento["es_replay_ciego"] = True
    calentamiento["es_curva_stitched"] = True
    calentamiento["estado_evaluacion"] = "evaluada"
    calentamiento["origen_emision"] = calentamiento["fecha_emision"]
    calentamiento["p10_kg"] = np.nan
    calentamiento["p90_kg"] = np.nan
    calentamiento["confianza"] = "baja"
    calentamiento["componentes"] = calentamiento.apply(
        lambda fila: _componentes_base(fila, "calentamiento_base"), axis=1
    )

    if not corregido.empty:
        corregido = corregido.copy()
        corregido["modelo"] = NOMBRE_MODELO
        corregido["version_modelo"] = VERSION_MODELO
        corregido["componentes"] = corregido["componentes"].map(
            lambda valor: {
                **(valor if isinstance(valor, dict) else {}),
                "estado_correccion": "ocurrencia_online",
                "emitio_prediccion": True,
            }
        )

    detalle = pd.concat([calentamiento, corregido], ignore_index=True, sort=False)
    detalle = detalle.sort_values(["fecha_objetivo", "lote_id"]).reset_index(drop=True)
    if len(detalle) != len(base) or detalle.duplicated(claves).any():
        raise AssertionError("El v2 no conservó exactamente el universo de MacroLegacy")
    detalle["emitio_prediccion"] = True
    detalle["nivel_calibracion"] = detalle.apply(
        lambda fila: (
            fila.get("nivel_calibracion")
            or (
                fila.get("componentes", {}).get("nivel_calibracion")
                if isinstance(fila.get("componentes"), dict)
                else None
            )
            or "no_informado"
        ),
        axis=1,
    )
    resumen = detalle.groupby("fecha_objetivo", as_index=False).agg(
        # Un real que todavía no cerró debe permanecer desconocido. Si se
        # reduce a cero, el resumen confunde "sin dato" con "cosecha cero".
        real_kg=("real_kg", lambda valores: valores.sum(min_count=1)),
        p50_kg=("p50_kg", "sum"),
        n_lotes=("lote_id", "nunique"),
    )
    return detalle, resumen


__all__ = [
    "NOMBRE_MODELO",
    "VERSION_MODELO",
    "ejecutar_replay_hibrido_ocurrencia_v2",
]

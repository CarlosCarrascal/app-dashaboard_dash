"""Configuración candidata y demostración del no-op H1 de run76."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from analitica.aplicacion.procesos.candidatos import (
    ConfiguracionTurnoTemporal,
    aplicar_turno_reingreso_candidate,
)


def _rejilla_configuraciones() -> list[ConfiguracionTurnoTemporal]:
    return [
        ConfiguracionTurnoTemporal(
            peso_calendario=peso,
            dispersion_semanas=dispersion,
            desplazamiento_max_semanas=0,
        )
        for peso in (0.25, 0.50, 0.75, 1.00)
        for dispersion in (0.50, 0.85, 1.25)
    ]


def demostrar_noop_h1(
    tabla: pd.DataFrame,
    cosecha_diaria: pd.DataFrame,
) -> dict[str, Any]:
    """Ejecuta la función pura y cuantifica que la rejilla no puede mover h1."""

    columnas = [
        "evaluation_contract_id",
        "campania",
        "modelo",
        "version_modelo",
        "fecha_emision",
        "fecha_objetivo",
        "horizonte_semanas",
        "lote_id",
        "fundo",
        "turno",
        "dias_reingreso",
        "p50_kg",
        "real_kg",
    ]
    # La ausencia de grados de libertad se audita sobre todo el contrato en
    # ``auditar_aplicabilidad_h1``. Ejecutar 12 veces 17.157 grupos para probar
    # la identidad sería costo sin información: aquí se conservan casos
    # representativos por fundo, split y disponibilidad de reingreso.
    muestra = tabla.copy()
    muestra["feature_disponible"] = muestra.turno.notna() & muestra.dias_reingreso.notna()
    columnas_muestra = ["fundo", "split", "feature_disponible"]
    muestra = muestra.sort_values(["fecha_emision", "lote_id"], kind="stable").drop_duplicates(
        columnas_muestra
    )
    curva = muestra[columnas].copy()
    resultados: list[dict[str, Any]] = []
    for config in _rejilla_configuraciones():
        candidato = aplicar_turno_reingreso_candidate(
            curva,
            cosecha_diaria,
            config=config,
        )
        diferencia = candidato.p50_kg.to_numpy(float) - curva.p50_kg.to_numpy(float)
        resultados.append(
            {
                "configuracion": asdict(config),
                "cambio_max_abs_kg": float(np.abs(diferencia).max(initial=0.0)),
                "cambio_total_kg": float(diferencia.sum()),
            }
        )
    return {
        "n_configuraciones": len(resultados),
        "n_filas_demostracion": int(len(curva)),
        "criterio_muestra": "fundo × split × disponibilidad de Turno/reingreso",
        "todas_identicas_a_macro": all(fila["cambio_max_abs_kg"] <= 1e-12 for fila in resultados),
        "cambio_max_abs_kg": max((fila["cambio_max_abs_kg"] for fila in resultados), default=0.0),
        "configuraciones": resultados,
    }

"""Intervalos, sensibilidades y escenarios del modelo fenológico."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from analitica.dominio.modelos.fenologico.contratos import EscenarioFenologico
from analitica.dominio.modelos.fenologico.metricas import (
    calibrar_factor_volumen,
    intervalos_validacion,
    intervalos_volumen_directo,
    sensibilidades,
)
from analitica.dominio.versiones import banda_horizonte


def aplicar_escenario_fenologico(
    predicciones: pd.DataFrame,
    escenario: EscenarioFenologico,
) -> tuple[pd.DataFrame, list[str]]:
    """Aplica sensibilidades locales guardadas por el modelo, nunca coeficientes causales."""

    salida = predicciones.copy()
    advertencias: set[str] = set()
    for indice, fila in salida.iterrows():
        componentes = fila.get("componentes") or {}
        if isinstance(componentes, str):
            try:
                componentes = json.loads(componentes)
            except json.JSONDecodeError:
                componentes = {}
        if isinstance(componentes, dict) and isinstance(componentes.get("componentes"), dict):
            anidado = componentes["componentes"]
            componentes = {
                **anidado,
                **{clave: valor for clave, valor in componentes.items() if clave != "componentes"},
            }
        sensibilidades = (
            componentes.get("sensibilidades", {}) if isinstance(componentes, dict) else {}
        )
        factores = {"probabilidad": 1.0, "frutos": 1.0, "peso": 1.0}
        cambios = {
            "cuajado_pct": escenario.cuajado_pct,
            "riego_pct": escenario.riego_pct,
            "temp_delta_c": escenario.temp_delta_c,
            "dpv_delta_kpa": escenario.dpv_delta_kpa,
            "poda_delta_dias": escenario.poda_delta_dias,
        }
        for control, valor in cambios.items():
            if not valor:
                continue
            sensibilidad = sensibilidades.get(control)
            if not sensibilidad:
                advertencias.add(
                    f"{control}: sin sensibilidad local disponible; no se alteró la predicción."
                )
                continue
            unidad = float(sensibilidad.get("unidad_cambio") or 0)
            if unidad == 0:
                continue
            pasos = float(valor) / unidad
            for pieza, clave in (
                ("probabilidad", "probabilidad_pct"),
                ("frutos", "frutos_pct"),
                ("peso", "peso_pct"),
            ):
                factores[pieza] *= max(0.0, 1 + pasos * float(sensibilidad.get(clave, 0)) / 100)

        factor_plantas = 1 + escenario.plantas_pct / 100
        factor_caida = 1 - escenario.caida_frutos_pct / 100
        if "plantas" in salida:
            salida.at[indice, "plantas"] = float(fila.plantas) * factor_plantas
        if "probabilidad_cosecha" in salida and pd.notna(fila.get("probabilidad_cosecha")):
            salida.at[indice, "probabilidad_cosecha"] = np.clip(
                float(fila.probabilidad_cosecha) * factores["probabilidad"], 0, 1
            )
        if "frutos_por_planta" in salida:
            salida.at[indice, "frutos_por_planta"] = (
                float(fila.frutos_por_planta) * factores["frutos"] * factor_caida
            )
        if "peso_baya_g" in salida:
            salida.at[indice, "peso_baya_g"] = float(fila.peso_baya_g) * factores["peso"]
        factor_total = factor_plantas * factor_caida * np.prod(list(factores.values()))
        for columna in ("p10_kg", "p50_kg", "p90_kg", "kg_condicional"):
            if columna in salida and pd.notna(fila.get(columna)):
                salida.at[indice, columna] = max(0, float(fila[columna]) * factor_total)

    if escenario.desplazamiento_semanas and "fecha_objetivo" in salida:
        delta = pd.Timedelta(weeks=escenario.desplazamiento_semanas)
        salida["fecha_objetivo"] = pd.to_datetime(salida.fecha_objetivo) + delta
        salida["horizonte_semanas"] = (
            (salida.fecha_objetivo - pd.to_datetime(salida.fecha_emision)).dt.days // 7
        ).astype(int)
        salida["banda_horizonte"] = salida.horizonte_semanas.map(banda_horizonte)
    salida["escenario_nombre"] = escenario.nombre
    salida["escenario_etiqueta"] = "sensibilidad_predictiva_no_causal"
    return salida, sorted(advertencias)

__all__ = [
    "aplicar_escenario_fenologico",
    "calibrar_factor_volumen",
    "intervalos_validacion",
    "intervalos_volumen_directo",
    "sensibilidades",
]

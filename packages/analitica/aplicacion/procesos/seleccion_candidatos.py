"""Búsqueda rápida y sin persistencia de mezclas residuales as-of.

Este módulo trabaja exclusivamente con releases aprobadas. No entrena ni modifica los
baselines persistidos: descompone el híbrido v2 congelado para evaluar pesos nuevos y
elige configuraciones con C2025 antes de comprobarlas en C2026. El resultado es un
informe de screening; nunca una autorización de publicación.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from math import ceil
from typing import Any

import numpy as np
import pandas as pd

CLAVES = [
    "evaluation_contract_id",
    "campania",
    "fecha_emision",
    "fecha_objetivo",
    "lote_id",
]


@dataclass(frozen=True)
class CandidatoMezcla:
    nombre: str
    modo: str
    peso_fijo: float = 0.5
    ventana: int = 4
    regularizacion: float = 8.0
    peso_min: float = 0.20
    peso_max: float = 0.80

    def __post_init__(self) -> None:
        if self.modo not in {"fijo", "online"}:
            raise ValueError("modo debe ser fijo u online")
        if not 0 <= self.peso_min <= self.peso_max <= 1:
            raise ValueError("los límites del peso deben estar entre cero y uno")
        if not self.peso_min <= self.peso_fijo <= self.peso_max:
            raise ValueError("peso_fijo está fuera de los límites")
        if self.ventana < 2:
            raise ValueError("ventana debe ser al menos dos semanas")
        if self.regularizacion < 0:
            raise ValueError("regularizacion no puede ser negativa")


def candidatos_por_defecto() -> list[CandidatoMezcla]:
    """Espacio pequeño y explícito; queda muy por debajo del límite de 30."""

    candidatos = [
        CandidatoMezcla(f"fijo_{peso:.2f}", "fijo", peso_fijo=float(peso))
        for peso in np.arange(0.25, 0.76, 0.05)
    ]
    candidatos.extend(
        CandidatoMezcla(
            f"online_v{ventana}_r{regularizacion}",
            "online",
            ventana=ventana,
            regularizacion=float(regularizacion),
        )
        for ventana in (3, 4, 6, 8, 12)
        for regularizacion in (4, 8, 16)
    )
    return candidatos


def preparar_panel(tabla: pd.DataFrame) -> pd.DataFrame:
    """Pivota Macro/Ocurrencia y exige un contrato idéntico por fila."""

    requeridas = set(CLAVES + ["modelo", "p50_kg", "real_kg"])
    faltantes = sorted(requeridas.difference(tabla.columns))
    if faltantes:
        raise ValueError(f"Faltan columnas del panel certificado: {faltantes}")
    t = tabla.copy()
    t["fecha_emision"] = pd.to_datetime(t.fecha_emision, errors="raise")
    t["fecha_objetivo"] = pd.to_datetime(t.fecha_objetivo, errors="raise")
    if (t.fecha_emision >= t.fecha_objetivo).any():
        raise ValueError("El panel contiene una emisión contemporánea o futura")
    if t.duplicated(CLAVES + ["modelo"]).any():
        raise ValueError("El panel repite modelo dentro de una clave contractual")

    pred = t.pivot(index=CLAVES, columns="modelo", values="p50_kg").reset_index()
    nombres = {"MacroLegacy_v1", "HibridoOcurrenciaOnline_v2"}
    ausentes = sorted(nombres.difference(pred.columns))
    if ausentes:
        raise ValueError(f"Faltan baselines congelados: {ausentes}")
    reales = t.groupby(CLAVES, as_index=False, dropna=False).real_kg.first()
    panel = pred.merge(reales, on=CLAVES, how="inner", validate="one_to_one")
    panel = panel.rename(
        columns={
            "MacroLegacy_v1": "macro_kg",
            "HibridoOcurrenciaOnline_v2": "ocurrencia_v2_kg",
        }
    )
    panel["hurdle_kg"] = (2 * panel.ocurrencia_v2_kg - panel.macro_kg).clip(lower=0)
    return panel.sort_values(["campania", "fecha_objetivo", "lote_id"]).reset_index(drop=True)


def _peso_online(historial: pd.DataFrame, candidato: CandidatoMezcla) -> float:
    if historial.fecha_objetivo.nunique() < 2:
        return 0.5
    semanal = (
        historial.groupby("fecha_objetivo", as_index=False)
        .agg(
            macro_kg=("macro_kg", "sum"),
            hurdle_kg=("hurdle_kg", "sum"),
            real_kg=("real_kg", "sum"),
        )
        .tail(candidato.ventana)
    )
    pesos = np.linspace(candidato.peso_min, candidato.peso_max, 13)
    denominador = float(semanal.real_kg.abs().sum())
    if denominador <= 0:
        return 0.5
    perdidas = []
    for peso in pesos:
        pred = peso * semanal.macro_kg + (1 - peso) * semanal.hurdle_kg
        perdida = float((pred - semanal.real_kg).abs().sum() / denominador)
        perdidas.append((perdida, float(peso)))
    peso_crudo = min(perdidas)[1]
    n = semanal.fecha_objetivo.nunique()
    shrink = n / (n + candidato.regularizacion)
    return float(np.clip(0.5 + shrink * (peso_crudo - 0.5), 0, 1))


def aplicar_candidato(panel: pd.DataFrame, candidato: CandidatoMezcla) -> pd.DataFrame:
    """Aplica un peso semanal calculado solo con semanas cerradas anteriores."""

    salidas: list[pd.DataFrame] = []
    for _, campania in panel.groupby("campania", sort=False):
        campania = campania.sort_values(["fecha_objetivo", "lote_id"]).copy()
        for fecha, semana in campania.groupby("fecha_objetivo", sort=True):
            emision = pd.Timestamp(semana.fecha_emision.iloc[0])
            if semana.fecha_emision.nunique() != 1:
                raise ValueError("Una semana contractual contiene más de una emisión")
            if candidato.modo == "fijo":
                peso = candidato.peso_fijo
            else:
                historial = campania[
                    (campania.fecha_objetivo < emision)
                    & (campania.fecha_objetivo < pd.Timestamp(fecha))
                ]
                peso = _peso_online(historial, candidato)
            semana = semana.copy()
            semana["peso_macro"] = peso
            semana["pred_kg"] = (peso * semana.macro_kg + (1 - peso) * semana.hurdle_kg).clip(
                lower=0
            )
            salidas.append(semana)
    return pd.concat(salidas, ignore_index=True) if salidas else panel.iloc[0:0].copy()


def metricas(tabla: pd.DataFrame, columna: str) -> dict[str, float | int]:
    semanal = tabla.groupby(["campania", "fecha_objetivo"], as_index=False).agg(
        pred_kg=(columna, "sum"), real_kg=("real_kg", "sum")
    )
    error = semanal.pred_kg - semanal.real_kg
    denominador = float(semanal.real_kg.abs().sum())
    cambios = semanal.sort_values(["campania", "fecha_objetivo"]).groupby("campania").real_kg.diff()
    escala_mase = float(cambios.abs().dropna().mean())
    return {
        "wape": float(error.abs().sum() / denominador) if denominador else np.nan,
        "sesgo_pct": float(error.sum() / denominador) if denominador else np.nan,
        "mae_kg": float(error.abs().mean()) if len(error) else np.nan,
        "mase": float(error.abs().mean() / escala_mase) if escala_mase > 0 else np.nan,
        "wape_lote_semana": float(
            (tabla[columna] - tabla.real_kg).abs().sum() / tabla.real_kg.abs().sum()
        )
        if tabla.real_kg.abs().sum()
        else np.nan,
        "n_semanas": int(len(semanal)),
        "n_lotes_semana": int(len(tabla)),
    }


def _submuestra_semanas(tabla: pd.DataFrame, fraccion: float) -> pd.DataFrame:
    fechas = sorted(tabla.fecha_objetivo.unique())
    n = max(3, min(len(fechas), ceil(len(fechas) * fraccion)))
    posiciones = np.linspace(0, len(fechas) - 1, n).round().astype(int)
    elegidas = {fechas[i] for i in sorted(set(posiciones))}
    return tabla[tabla.fecha_objetivo.isin(elegidas)].copy()


def successive_halving(
    panel: pd.DataFrame,
    candidatos: Iterable[CandidatoMezcla] | None = None,
    campania_desarrollo: str = "C2025",
    campania_validacion: str = "C2026",
) -> dict[str, Any]:
    """Selecciona en C2025 y audita finalistas en C2026, sin persistir."""

    candidatos_vivos = list(candidatos or candidatos_por_defecto())
    desarrollo = panel[panel.campania.eq(campania_desarrollo)].copy()
    validacion = panel[panel.campania.eq(campania_validacion)].copy()
    if desarrollo.empty or validacion.empty:
        raise ValueError("Se requieren campañas distintas para desarrollo y validación")
    rondas = []
    for fraccion in (0.35, 0.65, 1.0):
        recurso = _submuestra_semanas(desarrollo, fraccion)
        resultados = []
        for candidato in candidatos_vivos:
            predicho = aplicar_candidato(recurso, candidato)
            metrica = metricas(predicho, "pred_kg")
            penalizacion = max(0.0, abs(float(metrica["sesgo_pct"])) - 0.10)
            resultados.append(
                {
                    "candidato": candidato,
                    "score": float(metrica["wape"]) + penalizacion,
                    "metricas": metrica,
                }
            )
        resultados.sort(key=lambda fila: (fila["score"], fila["candidato"].nombre))
        conservar = max(1, ceil(len(resultados) / 2))
        rondas.append(
            {
                "fraccion": fraccion,
                "n_candidatos": len(resultados),
                "n_semanas": int(recurso.fecha_objetivo.nunique()),
                "ranking": [
                    {
                        "configuracion": asdict(f["candidato"]),
                        "score": f["score"],
                        "metricas": f["metricas"],
                    }
                    for f in resultados
                ],
            }
        )
        candidatos_vivos = [fila["candidato"] for fila in resultados[:conservar]]

    finalistas = []
    base_validacion = {
        "MacroLegacy_v1": metricas(validacion, "macro_kg"),
        "HibridoOcurrenciaOnline_v2": metricas(validacion, "ocurrencia_v2_kg"),
    }
    for candidato in candidatos_vivos:
        pred_desarrollo = aplicar_candidato(desarrollo, candidato)
        pred_validacion = aplicar_candidato(validacion, candidato)
        finalistas.append(
            {
                "configuracion": asdict(candidato),
                "desarrollo": metricas(pred_desarrollo, "pred_kg"),
                "validacion_externa": metricas(pred_validacion, "pred_kg"),
            }
        )
    finalistas.sort(key=lambda f: f["validacion_externa"]["wape"])
    mejor = finalistas[0]
    mv = mejor["validacion_externa"]
    macro = base_validacion["MacroLegacy_v1"]
    ocurrencia = base_validacion["HibridoOcurrenciaOnline_v2"]
    mejora_macro_wape = (macro["wape"] - mv["wape"]) / macro["wape"]
    mejora_macro_mase = (macro["mase"] - mv["mase"]) / macro["mase"]
    mejora_ocurrencia = (ocurrencia["wape"] - mv["wape"]) / ocurrencia["wape"]
    decision = {
        "mejora_frente_macro": bool(
            mejora_macro_wape >= 0.05 and mejora_macro_mase >= 0.05 and abs(mv["sesgo_pct"]) <= 0.10
        ),
        "mejora_sustancial_frente_ocurrencia_v2": bool(mejora_ocurrencia >= 0.05),
        "mejora_macro_wape_relativa": float(mejora_macro_wape),
        "mejora_macro_mase_relativa": float(mejora_macro_mase),
        "mejora_ocurrencia_wape_relativa": float(mejora_ocurrencia),
        "publicable": False,
        "motivo": "screening sin persistencia; requiere replay completo y revisión por fundo",
    }
    return {
        "campania_desarrollo": campania_desarrollo,
        "campania_validacion": campania_validacion,
        "rondas": rondas,
        "baselines_validacion": base_validacion,
        "finalistas": finalistas,
        "mejor": mejor,
        "decision": decision,
    }


__all__ = [
    "CandidatoMezcla",
    "aplicar_candidato",
    "candidatos_por_defecto",
    "metricas",
    "preparar_panel",
    "successive_halving",
]

"""Corrector conservador de ocurrencia sobre ``MacroLegacy_v1``.

La v3 no vuelve a entrenar una curva paralela ni aplica multiplicadores
arbitrarios. Reutiliza la ocurrencia rolling-origin de v1, separa la señal
``hurdle`` de la mezcla publicada y aprende, con semanas OOS anteriores, cuánto
debe pesar esa señal. Así puede bajar el peso de ocurrencia cuando está
castigando una curva que ya venía siguiendo bien al real.

La calibración continua de residuos y el desplazamiento temporal se conservan
como experimentos aislados; no se activan en producción hasta demostrar mejora.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from analitica.dominio.modelos.ocurrencia_v1 import (
    ConfiguracionHibridoOcurrencia,
    ejecutar_replay_hibrido_ocurrencia,
)

NOMBRE_MODELO = "HibridoOcurrenciaOnline_v3"
VERSION_MODELO = "macro_hurdle_adaptive_weighted_v3"


@dataclass(frozen=True)
class ConfiguracionHibridoOcurrenciaV3:
    semanas_calentamiento: int = 5
    pesos_ocurrencia: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
    minimo_calibracion_peso: int = 4


def _peso_ocurrencia(
    historial: pd.DataFrame,
    config: ConfiguracionHibridoOcurrenciaV3,
) -> float:
    """Elige el peso del hurdle minimizando error semanal OOS anterior."""

    if historial.empty or historial.fecha_objetivo.nunique() < config.minimo_calibracion_peso:
        # Mientras no hay cuatro semanas OOS, se conserva la mezcla validada de
        # v2; no se toman decisiones adaptativas con una muestra mínima.
        return 0.5
    semanal = historial.groupby("fecha_objetivo", as_index=False).agg(
        real=("real_kg", "sum"),
        macro=("macro_kg", "sum"),
        hurdle=("hurdle_kg", "sum"),
    )
    denominador = float(np.abs(semanal.real).sum())
    if denominador <= 0:
        return 0.0
    mejor = (float("inf"), 0.0)
    for peso in config.pesos_ocurrencia:
        prediccion = (1.0 - peso) * semanal.macro + peso * semanal.hurdle
        perdida = float(np.abs(prediccion - semanal.real).sum() / denominador)
        if perdida < mejor[0] - 1e-12:
            mejor = (perdida, float(peso))
    return mejor[1]


def _extraer_componentes(valor: object) -> dict:
    return dict(valor) if isinstance(valor, dict) else {}


def ejecutar_replay_hibrido_ocurrencia_v3(
    curva_legacy: pd.DataFrame,
    config: ConfiguracionHibridoOcurrenciaV3 | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ejecuta la ocurrencia v1 y sustituye su mezcla fija por una adaptativa.

    El modelo base y la señal hurdle de cada semana se calculan rolling-origin
    por ``ejecutar_replay_hibrido_ocurrencia``. La v3 solo decide el peso usando
    predicciones OOS ya observadas; nunca usa el ``real_kg`` de la semana actual.
    """

    if curva_legacy.empty:
        return pd.DataFrame(), pd.DataFrame()
    config = config or ConfiguracionHibridoOcurrenciaV3()
    base = curva_legacy.copy()
    base["fecha_objetivo"] = pd.to_datetime(base["fecha_objetivo"], errors="raise")
    base["fecha_emision"] = pd.to_datetime(base["fecha_emision"], errors="raise")
    claves = ["campania", "lote_id", "fecha_objetivo"]
    if base.duplicated(claves).any():
        raise ValueError("La curva v3 repite campaña, lote y semana objetivo")
    if base["campania"].astype(str).nunique() != 1:
        raise ValueError("El replay v3 debe ejecutarse por campaña")

    fechas = sorted(base["fecha_objetivo"].dropna().unique())
    if len(fechas) <= config.semanas_calentamiento:
        return pd.DataFrame(), pd.DataFrame()

    # La señal hurdle viene de una predicción OOS independiente. Como v1 mezcla
    # 50/50, se despeja su componente para no volver a entrenar el mismo modelo.
    v1, _ = ejecutar_replay_hibrido_ocurrencia(
        base,
        ConfiguracionHibridoOcurrencia(
            semanas_calentamiento=config.semanas_calentamiento,
            peso_curva_legacy=0.5,
        ),
    )
    mapa_v1 = v1.set_index(claves) if not v1.empty else pd.DataFrame()
    historial: pd.DataFrame | None = None
    salidas: list[pd.DataFrame] = []

    for fecha in fechas:
        prueba = base[base.fecha_objetivo.eq(fecha)].copy()
        peso = _peso_ocurrencia(historial if historial is not None else pd.DataFrame(), config)
        filas = []
        for _, fila in prueba.iterrows():
            clave = (fila.campania, fila.lote_id, fila.fecha_objetivo)
            macro_kg = float(fila.p50_kg)
            existe_v1 = not v1.empty and clave in mapa_v1.index
            if existe_v1:
                v1_fila = mapa_v1.loc[clave]
                if isinstance(v1_fila, pd.DataFrame):
                    raise ValueError("Ocurrencia v1 repite una clave de lote-semana")
                v1_kg = float(v1_fila.p50_kg)
                hurdle_kg = max(0.0, 2.0 * v1_kg - macro_kg)
                prediccion = (1.0 - peso) * macro_kg + peso * hurdle_kg
                componentes = _extraer_componentes(v1_fila.get("componentes"))
                estado = "ocurrencia_adaptativa"
            else:
                hurdle_kg = np.nan
                prediccion = macro_kg
                componentes = {}
                estado = "calentamiento_base"
            fila = fila.copy()
            fila["p50_kg"] = max(0.0, float(prediccion))
            fila["macro_kg_v3"] = macro_kg
            fila["hurdle_kg_v3"] = hurdle_kg
            fila["peso_ocurrencia_v3"] = peso if existe_v1 else 0.0
            fila["estado_correccion_v3"] = estado
            fila["componentes_v1"] = componentes
            filas.append(fila)
        salida_semana = pd.DataFrame(filas)
        salidas.append(salida_semana)

        # La semana entra al historial solo después de generar su predicción.
        ocurridas = salida_semana[~salida_semana.hurdle_kg_v3.isna()]
        if not ocurridas.empty:
            nuevo_historial = ocurridas[
                ["fecha_objetivo", "real_kg", "macro_kg_v3", "hurdle_kg_v3"]
            ].rename(columns={"macro_kg_v3": "macro_kg", "hurdle_kg_v3": "hurdle_kg"})
            historial = (
                nuevo_historial
                if historial is None
                else pd.concat([historial, nuevo_historial], ignore_index=True)
            )

    detalle = pd.concat(salidas, ignore_index=True, sort=False)
    detalle["modelo"] = NOMBRE_MODELO
    detalle["version_modelo"] = VERSION_MODELO
    detalle["p10_kg"] = np.nan
    detalle["p90_kg"] = np.nan
    detalle["confianza"] = "baja"
    detalle["tipo_prediccion"] = "replay"
    detalle["es_replay_ciego"] = True
    detalle["es_curva_stitched"] = True
    detalle["estado_evaluacion"] = "evaluada"
    detalle["origen_emision"] = detalle["fecha_emision"]
    detalle["emitio_prediccion"] = True
    detalle["componentes"] = detalle.apply(
        lambda fila: {
            **fila.componentes_v1,
            "modelo_base": "MacroLegacy_v1",
            "kg_legacy": float(fila.macro_kg_v3),
            "kg_hurdle": (float(fila.hurdle_kg_v3) if pd.notna(fila.hurdle_kg_v3) else None),
            "peso_ocurrencia": float(fila.peso_ocurrencia_v3),
            "estado_correccion": str(fila.estado_correccion_v3),
            "etiqueta_causal": False,
        },
        axis=1,
    )
    detalle = detalle.drop(columns=["componentes_v1"], errors="ignore")
    resumen = detalle.groupby("fecha_objetivo", as_index=False).agg(
        real_kg=("real_kg", "sum"), p50_kg=("p50_kg", "sum"), n_lotes=("lote_id", "nunique")
    )
    return detalle, resumen


__all__ = [
    "ConfiguracionHibridoOcurrenciaV3",
    "NOMBRE_MODELO",
    "VERSION_MODELO",
    "ejecutar_replay_hibrido_ocurrencia_v3",
]

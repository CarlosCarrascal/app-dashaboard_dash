"""Calibracion residual *candidate-only* para forecasts de cosecha.

La calibracion corrige la amplitud de una curva biologica congelada usando solo
errores cuyo resultado ya estaba cerrado antes de cada emision. No persiste ni
publica resultados y no usa R09 como predictor.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from analitica.dominio.compartido import normalizar_panel


@dataclass(frozen=True)
class ConfiguracionResidualAsOf:
    """Espacio pequeno y auditable de calibracion de volumen."""

    nivel: str = "fundo"
    ventana: int = 8
    regularizacion: float = 4.0
    factor_min: float = 0.70
    factor_max: float = 1.50
    por_horizonte: bool = True
    recencia: float = 0.85
    usar_campanias_previas: bool = False

    def __post_init__(self) -> None:
        if self.nivel not in {"global", "fundo", "modulo"}:
            raise ValueError("nivel debe ser global, fundo o modulo")
        if self.ventana < 2:
            raise ValueError("ventana debe ser al menos dos")
        if self.regularizacion < 0:
            raise ValueError("regularizacion no puede ser negativa")
        if not 0 < self.factor_min <= 1 <= self.factor_max:
            raise ValueError("los limites deben contener el factor uno")
        if not 0 < self.recencia <= 1:
            raise ValueError("recencia debe estar entre cero y uno")


def _media_robusta_reciente(valores: pd.Series, recencia: float) -> float:
    x = pd.to_numeric(valores, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if x.empty:
        return 0.0
    x = x.clip(lower=np.log(0.35), upper=np.log(2.50))
    pesos = recencia ** np.arange(len(x) - 1, -1, -1, dtype=float)
    centro = float(np.average(x.to_numpy(float), weights=pesos))
    mediana = float(x.median())
    return 0.5 * centro + 0.5 * mediana


def _historial_agregado(panel: pd.DataFrame, config: ConfiguracionResidualAsOf) -> pd.DataFrame:
    dimensiones = ["campania", "fecha_emision", "fecha_objetivo", "horizonte_semanas"]
    if config.nivel != "global":
        dimensiones.append(config.nivel)
    agregado = panel.groupby(dimensiones, dropna=False, as_index=False).agg(
        pred_base_kg=("p50_kg", "sum"), real_kg=("real_kg", "sum")
    )
    agregado["semana_fin"] = agregado.fecha_objetivo + pd.to_timedelta(6, unit="D")
    valido = agregado.real_kg.gt(0) & agregado.pred_base_kg.gt(0)
    agregado["residuo_log"] = np.nan
    agregado.loc[valido, "residuo_log"] = np.log(
        agregado.loc[valido, "real_kg"] / agregado.loc[valido, "pred_base_kg"]
    )
    return agregado


def _factor_asof(
    historial: pd.DataFrame,
    fila: pd.Series,
    config: ConfiguracionResidualAsOf,
) -> tuple[float, int, str]:
    # Campanas anteriores son priors legitimos; dentro de la campana solo entran
    # semanas cerradas antes de la emision evaluada.
    campania = str(fila.campania)
    anterior = historial.campania.astype(str).lt(campania)
    misma_cerrada = historial.campania.astype(str).eq(campania) & historial.semana_fin.lt(
        fila.fecha_emision
    )
    h = historial[(anterior if config.usar_campanias_previas else False) | misma_cerrada].copy()
    if config.por_horizonte:
        exacto = h[h.horizonte_semanas.eq(int(fila.horizonte_semanas))]
        if not exacto.empty:
            h = exacto
    if config.nivel != "global":
        especifico = h[h[config.nivel].astype(str).eq(str(fila[config.nivel]))]
        nivel_usado = config.nivel
        if len(especifico) >= 2:
            h = especifico
        else:
            nivel_usado = "global_shrinkage"
    else:
        nivel_usado = "global"
    h = h.sort_values(["fecha_objetivo", "fecha_emision"]).tail(config.ventana)
    residuos = h.residuo_log.dropna()
    n = int(len(residuos))
    if n == 0:
        return 1.0, 0, "prior_sin_historia"
    log_factor = _media_robusta_reciente(residuos, config.recencia)
    shrink = n / (n + config.regularizacion) if config.regularizacion else 1.0
    factor = float(np.exp(shrink * log_factor))
    factor = float(np.clip(factor, config.factor_min, config.factor_max))
    return factor, n, nivel_usado


def aplicar_calibracion_residual_asof(
    panel: pd.DataFrame,
    config: ConfiguracionResidualAsOf | None = None,
) -> pd.DataFrame:
    """Aplica un factor por grupo-emision-horizonte usando solo pasado cerrado."""

    config = config or ConfiguracionResidualAsOf()
    base = normalizar_panel(panel)
    historial = _historial_agregado(base, config)
    dimensiones = ["campania", "fecha_emision", "horizonte_semanas"]
    if config.nivel != "global":
        dimensiones.append(config.nivel)
    factores: list[dict[str, Any]] = []
    for clave, bloque in base.groupby(dimensiones, sort=False, dropna=False):
        fila = bloque.iloc[0]
        factor, n, nivel = _factor_asof(historial, fila, config)
        valores = clave if isinstance(clave, tuple) else (clave,)
        registro = dict(zip(dimensiones, valores, strict=True))
        factores.append(
            {
                **registro,
                "factor_residual_asof": factor,
                "n_residuos_asof": n,
                "nivel_residual": nivel,
            }
        )
    salida = base.merge(pd.DataFrame(factores), on=dimensiones, how="left", validate="many_to_one")
    salida["p50_base_kg"] = salida.p50_kg
    salida["p50_kg"] = (salida.p50_base_kg * salida.factor_residual_asof).clip(lower=0.0)
    salida["modelo"] = "CandidateResidualAsOf_v1"
    salida["version_modelo"] = "candidate_only_no_persistir_v1"
    salida["configuracion_candidate"] = [asdict(config)] * len(salida)
    return salida


def metricas_empresa(tabla: pd.DataFrame, columna: str = "p50_kg") -> dict[str, Any]:
    t = normalizar_panel(
        tabla.rename(columns={columna: "p50_kg"}) if columna != "p50_kg" else tabla
    )
    semanal = t.groupby(
        ["campania", "fecha_emision", "fecha_objetivo", "horizonte_semanas"],
        as_index=False,
    ).agg(pred_kg=("p50_kg", "sum"), real_kg=("real_kg", "sum"))
    error = semanal.pred_kg - semanal.real_kg
    denom = float(semanal.real_kg.abs().sum())
    por_horizonte: dict[str, dict[str, float]] = {}
    for horizonte, grupo in semanal.groupby("horizonte_semanas"):
        d = float(grupo.real_kg.abs().sum())
        e = grupo.pred_kg - grupo.real_kg
        por_horizonte[str(int(horizonte))] = {
            "wape": float(e.abs().sum() / d) if d else np.nan,
            "sesgo": float(e.sum() / d) if d else np.nan,
            "n": int(len(grupo)),
        }
    return {
        "wape": float(error.abs().sum() / denom) if denom else np.nan,
        "sesgo": float(error.sum() / denom) if denom else np.nan,
        "mae_kg": float(error.abs().mean()) if len(error) else np.nan,
        "n": int(len(semanal)),
        "por_horizonte": por_horizonte,
    }


__all__ = [
    "ConfiguracionResidualAsOf",
    "aplicar_calibracion_residual_asof",
    "metricas_empresa",
    "normalizar_panel",
]

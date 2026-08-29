"""Candidato por horizonte basado en parámetros operativos rezagados.

El modelo separa dos problemas que no deben compartir la misma corrección:

* horizonte 1: usa la curva calculada con los parámetros y el calendario que ya
  estaban disponibles en la emisión anterior. La escala total se estabiliza con
  una fracción pequeña del último cierre real conocido;
* horizontes 2 a 6: conserva sin cambios la proyección ``MacroLegacy`` congelada.

La implementación es deliberadamente pura: no lee Excel, Access, PostgreSQL ni
R09 y no persiste resultados. Esas responsabilidades pertenecen al proceso de
replay y publicación. Así puede probarse que el candidato no aprende del futuro
ni convierte la referencia R09 en predictor.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

MODELO = "HibridoParametrosLagged_v1"

CLAVES = (
    "campania",
    "fecha_emision",
    "fecha_objetivo",
    "horizonte_semanas",
    "lote_id",
)


@dataclass(frozen=True)
class ConfiguracionHibridoParametrosLagged:
    """Configuración congelable y auditable del candidato."""

    peso_parametros_h1: float = 0.95
    penalizacion_alejamiento_lagged: float = 0.10
    paso_busqueda_peso: float = 0.05
    horizonte_minimo_macro: int = 2
    horizonte_maximo_macro: int = 6

    def __post_init__(self) -> None:
        if not 0.0 <= self.peso_parametros_h1 <= 1.0:
            raise ValueError("peso_parametros_h1 debe estar entre 0 y 1")
        if self.penalizacion_alejamiento_lagged < 0:
            raise ValueError("penalizacion_alejamiento_lagged no puede ser negativa")
        if not 0 < self.paso_busqueda_peso <= 1:
            raise ValueError("paso_busqueda_peso debe estar entre 0 y 1")
        if self.horizonte_minimo_macro < 2:
            raise ValueError("horizonte_minimo_macro debe ser al menos 2")
        if self.horizonte_maximo_macro < self.horizonte_minimo_macro:
            raise ValueError("El rango de horizontes Macro no es válido")


def seleccionar_peso_parametros_asof(
    historial: pd.DataFrame,
    *,
    fecha_emision: object,
    config: ConfiguracionHibridoParametrosLagged | None = None,
) -> float:
    """Selecciona el peso h1 usando solo cierres anteriores a la emisión.

    La función minimiza WAPE histórico y regulariza el resultado hacia la curva
    de parámetros (peso 1). Ese prior evita reaccionar de forma extrema cuando
    solo existe uno o dos cierres. El historial requerido contiene
    ``lagged_total_kg``, ``naive_total_kg``, ``real_kg`` y ``fecha_cierre_real``.
    """

    cfg = config or ConfiguracionHibridoParametrosLagged()
    requeridas = {
        "lagged_total_kg",
        "naive_total_kg",
        "real_kg",
        "fecha_cierre_real",
    }
    faltantes = sorted(requeridas - set(historial.columns))
    if faltantes:
        raise ValueError(f"historial no contiene columnas requeridas: {faltantes}")
    corte = pd.Timestamp(fecha_emision).normalize()
    h = historial.copy()
    h["fecha_cierre_real"] = pd.to_datetime(h.fecha_cierre_real, errors="raise").dt.normalize()
    h = h.loc[h.fecha_cierre_real.lt(corte)].copy()
    if h.empty:
        return 1.0
    for columna in ("lagged_total_kg", "naive_total_kg", "real_kg"):
        h[columna] = pd.to_numeric(h[columna], errors="raise").astype(float)
    if (~np.isfinite(h[["lagged_total_kg", "naive_total_kg", "real_kg"]])).any().any():
        raise ValueError("historial contiene valores no finitos")
    denominador = float(h.real_kg.abs().sum())
    if denominador <= 0:
        return 1.0
    pesos = np.arange(0.0, 1.0 + cfg.paso_busqueda_peso / 2, cfg.paso_busqueda_peso)

    def objetivo(peso: float) -> float:
        prediccion = peso * h.lagged_total_kg + (1.0 - peso) * h.naive_total_kg
        wape = float((prediccion - h.real_kg).abs().sum() / denominador)
        return wape + cfg.penalizacion_alejamiento_lagged * (1.0 - peso) ** 2

    return float(min(pesos, key=objetivo))


def _normalizar_forecast(tabla: pd.DataFrame, *, nombre: str) -> pd.DataFrame:
    faltantes = sorted(set(CLAVES + ("p50_kg",)) - set(tabla.columns))
    if faltantes:
        raise ValueError(f"{nombre} no contiene columnas requeridas: {faltantes}")
    t = tabla.copy()
    t["fecha_emision"] = pd.to_datetime(t.fecha_emision, errors="raise").dt.normalize()
    t["fecha_objetivo"] = pd.to_datetime(t.fecha_objetivo, errors="raise").dt.normalize()
    t["horizonte_semanas"] = pd.to_numeric(t.horizonte_semanas, errors="raise").astype(int)
    t["p50_kg"] = pd.to_numeric(t.p50_kg, errors="raise").astype(float)
    if (~np.isfinite(t.p50_kg) | t.p50_kg.lt(0)).any():
        raise ValueError(f"{nombre} contiene kilos inválidos")
    if t.duplicated(list(CLAVES)).any():
        raise ValueError(f"{nombre} contiene claves lote-emisión duplicadas")
    if t.fecha_emision.ge(t.fecha_objetivo).any():
        raise ValueError(f"{nombre} contiene una emisión contemporánea o posterior")
    horizonte_calculado = ((t.fecha_objetivo - t.fecha_emision).dt.days // 7).astype(int)
    if horizonte_calculado.ne(t.horizonte_semanas).any():
        raise ValueError(f"{nombre} contiene horizontes inconsistentes")
    return t


def _normalizar_naive(tabla: pd.DataFrame) -> pd.DataFrame:
    requeridas = {
        "campania",
        "fecha_emision",
        "fecha_real_referencia",
        "naive_total_kg",
    }
    faltantes = sorted(requeridas - set(tabla.columns))
    if faltantes:
        raise ValueError(f"referencia_naive no contiene columnas requeridas: {faltantes}")
    t = tabla.copy()
    t["fecha_emision"] = pd.to_datetime(t.fecha_emision, errors="raise").dt.normalize()
    t["fecha_real_referencia"] = pd.to_datetime(
        t.fecha_real_referencia, errors="raise"
    ).dt.normalize()
    t["naive_total_kg"] = pd.to_numeric(t.naive_total_kg, errors="raise").astype(float)
    if (~np.isfinite(t.naive_total_kg) | t.naive_total_kg.lt(0)).any():
        raise ValueError("referencia_naive contiene kilos inválidos")
    if t.fecha_real_referencia.ge(t.fecha_emision).any():
        raise ValueError(
            "La referencia naive debe pertenecer a una semana cerrada antes de la emisión"
        )
    claves = ["campania", "fecha_emision"]
    if t.duplicated(claves).any():
        raise ValueError("referencia_naive contiene más de un cierre por emisión")
    return t.loc[:, [*claves, "fecha_real_referencia", "naive_total_kg"]]


def construir_hibrido_parametros_lagged(
    parametros_lagged: pd.DataFrame,
    macro_congelada: pd.DataFrame,
    referencia_naive: pd.DataFrame,
    *,
    config: ConfiguracionHibridoParametrosLagged | None = None,
) -> pd.DataFrame:
    """Construye el candidato sin I/O ni acceso a resultados futuros.

    ``parametros_lagged`` debe ser el forecast generado con el snapshot de
    parámetros/calendario de la emisión anterior. ``referencia_naive`` contiene
    solamente el total real de la última semana ya cerrada antes de cada emisión.
    La mezcla se aplica al total h1 y luego se distribuye proporcionalmente entre
    lotes, conservando la forma espacial de la curva de parámetros.
    """

    cfg = config or ConfiguracionHibridoParametrosLagged()
    lagged = _normalizar_forecast(parametros_lagged, nombre="parametros_lagged")
    macro = _normalizar_forecast(macro_congelada, nombre="macro_congelada")
    naive = _normalizar_naive(referencia_naive)

    h1 = lagged.loc[lagged.horizonte_semanas.eq(1)].copy()
    if h1.empty:
        raise ValueError("parametros_lagged no contiene horizonte 1")

    grupos = ["campania", "fecha_emision", "fecha_objetivo"]
    total = (
        h1.groupby(grupos, as_index=False)
        .p50_kg.sum()
        .rename(columns={"p50_kg": "lagged_total_kg"})
    )
    total = total.merge(
        naive,
        on=["campania", "fecha_emision"],
        how="left",
        validate="many_to_one",
    )
    if total.naive_total_kg.isna().any():
        raise ValueError("Falta el último cierre real para una emisión h1")
    total["mezcla_total_kg"] = (
        cfg.peso_parametros_h1 * total.lagged_total_kg
        + (1.0 - cfg.peso_parametros_h1) * total.naive_total_kg
    )
    total["factor_escala"] = np.where(
        total.lagged_total_kg.gt(0),
        total.mezcla_total_kg / total.lagged_total_kg,
        np.nan,
    )
    if (~np.isfinite(total.factor_escala)).any():
        raise ValueError("No se puede distribuir una mezcla sobre un total lagged igual a cero")

    h1 = h1.merge(total, on=grupos, how="left", validate="many_to_one")
    h1["p50_kg"] = h1.p50_kg * h1.factor_escala
    h1["modelo"] = MODELO
    h1["ruta_modelo"] = "parametros_lagged_h1"
    h1["peso_parametros"] = cfg.peso_parametros_h1
    h1["peso_ultimo_real"] = 1.0 - cfg.peso_parametros_h1

    macro = macro.loc[
        macro.horizonte_semanas.between(cfg.horizonte_minimo_macro, cfg.horizonte_maximo_macro)
    ].copy()
    macro["modelo"] = MODELO
    macro["ruta_modelo"] = "macro_congelada_h2_h6"
    macro["peso_parametros"] = 0.0
    macro["peso_ultimo_real"] = 0.0
    macro["fecha_real_referencia"] = pd.NaT
    macro["naive_total_kg"] = np.nan
    macro["lagged_total_kg"] = np.nan
    macro["mezcla_total_kg"] = np.nan
    macro["factor_escala"] = 1.0

    columnas = list(dict.fromkeys([*h1.columns, *macro.columns]))
    salida = pd.concat(
        [h1.reindex(columns=columnas), macro.reindex(columns=columnas)],
        ignore_index=True,
    )
    if salida.duplicated(list(CLAVES)).any():
        raise ValueError("Las rutas h1 y Macro se superponen")
    return salida.sort_values(list(CLAVES), kind="stable").reset_index(drop=True)

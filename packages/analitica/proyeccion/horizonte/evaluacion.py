"""Agregación, métricas y loops candidate-only por horizonte."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from .contratos import CLAVES, ConfiguracionCorreccionHorizonte
from .correccion import (
    _aplicar_normalizado,
    _historial_canonico,
    normalizar_panel,
)


def agregar_semanal(tabla: pd.DataFrame, columna: str = "pred_kg") -> pd.DataFrame:
    """Agrega sin mezclar emisiones ni horizontes."""

    requeridas = set(CLAVES[:-1]) | {"real_kg", columna}
    faltantes = sorted(requeridas.difference(tabla.columns))
    if faltantes:
        raise ValueError(f"Faltan columnas para evaluación semanal: {faltantes}")
    return tabla.groupby(
        ["campania", "fecha_emision", "fecha_objetivo", "horizonte_semanas"],
        as_index=False,
    ).agg(
        pred_kg=(columna, "sum"),
        # Un grupo de reales todos desconocidos debe seguir siendo NaN. Si
        # pandas lo reduce a cero, el evaluador interpreta "aún no observado"
        # como "cosecha cero" y castiga artificialmente los horizontes largos.
        real_kg=("real_kg", lambda valores: valores.sum(min_count=1)),
    )


def seleccionar_vintage_coherente(tabla: pd.DataFrame) -> pd.DataFrame:
    """Conserva una sola emisión previa por semana objetivo y horizonte.

    Una evaluación histórica no puede sumar S31, S32 y S33 para la misma semana:
    son versiones alternativas de la misma predicción. Se conserva la emisión
    más reciente estrictamente anterior al lunes objetivo y se mantienen todas
    las filas de esa emisión (por ejemplo, los cuatro fundos).
    """

    base = normalizar_panel(tabla)
    elegibles = base.loc[base["fecha_emision"].lt(base["fecha_objetivo"])].copy()
    if elegibles.empty:
        return elegibles
    claves = ["campania", "fecha_objetivo", "horizonte_semanas"]
    elegida = (
        elegibles.groupby(claves, as_index=False)["fecha_emision"]
        .max()
        .rename(columns={"fecha_emision": "_emision_elegida"})
    )
    return (
        elegibles.merge(elegida, on=claves, how="inner", validate="many_to_one")
        .loc[lambda frame: frame["fecha_emision"].eq(frame["_emision_elegida"])]
        .drop(columns="_emision_elegida")
        .sort_values(["campania", "fecha_objetivo", "horizonte_semanas", "lote_id"])
    )


def metricas_horizonte(tabla: pd.DataFrame, columna: str = "pred_kg") -> pd.DataFrame:
    """Métricas de volumen por horizonte, con denominador común."""

    semanal = agregar_semanal(tabla, columna)
    filas: list[dict[str, Any]] = []
    for horizonte, grupo in semanal.groupby("horizonte_semanas", sort=True):
        grupo = grupo.dropna(subset=["real_kg"])
        if grupo.empty:
            continue
        error = grupo["pred_kg"] - grupo["real_kg"]
        denom = float(grupo["real_kg"].abs().sum())
        filas.append(
            {
                "horizonte": int(horizonte),
                "n_emision_objetivo": int(len(grupo)),
                "real_kg": float(grupo["real_kg"].sum()),
                "pred_kg": float(grupo["pred_kg"].sum()),
                "wape": float(error.abs().sum() / denom) if denom else np.nan,
                "mae_kg": float(error.abs().mean()),
                "rmse_kg": float(np.sqrt(np.mean(np.square(error)))),
                "bias_pct": float(error.sum() / denom) if denom else np.nan,
            }
        )
    return pd.DataFrame(filas)


def evaluar_mismo_universo(
    baseline: pd.DataFrame,
    candidato: pd.DataFrame,
    *,
    clave_agregada: tuple[str, ...] = (
        "campania",
        "fecha_emision",
        "fecha_objetivo",
        "horizonte_semanas",
    ),
) -> pd.DataFrame:
    """Compara baseline y candidato sobre idénticas emisiones y objetivos."""

    base = agregar_semanal(baseline, "p50_kg").rename(columns={"pred_kg": "baseline_kg"})
    cand = agregar_semanal(candidato, "pred_kg").rename(columns={"pred_kg": "candidato_kg"})
    claves = list(clave_agregada)
    diferencias = base[claves].merge(cand[claves], on=claves, how="outer", indicator=True)
    if diferencias["_merge"].ne("both").any():
        faltan_baseline = int(diferencias["_merge"].eq("right_only").sum())
        faltan_candidato = int(diferencias["_merge"].eq("left_only").sum())
        raise ValueError(
            "baseline y candidato no comparten el mismo universo: "
            f"faltan en baseline={faltan_baseline}, faltan en candidato={faltan_candidato}"
        )
    comunes = base.merge(cand, on=claves, how="inner", validate="one_to_one")
    if comunes.empty:
        return pd.DataFrame()
    # La verdad pertenece al objetivo, no a la ejecución del modelo.
    comunes["real_kg"] = comunes["real_kg_x"].combine_first(comunes["real_kg_y"])
    comunes["error_baseline"] = comunes["baseline_kg"] - comunes["real_kg"]
    comunes["error_candidato"] = comunes["candidato_kg"] - comunes["real_kg"]
    return comunes


def _resumen_comparacion(comunes: pd.DataFrame, columna_error: str) -> dict[str, float]:
    denom = float(comunes["real_kg"].abs().sum())
    error = comunes[columna_error]
    return {
        "wape": float(error.abs().sum() / denom) if denom else np.nan,
        "mae_kg": float(error.abs().mean()) if len(error) else np.nan,
        "bias_pct": float(error.sum() / denom) if denom else np.nan,
        "n": int(len(comunes)),
    }


def configuraciones_loop() -> list[ConfiguracionCorreccionHorizonte]:
    """Espacio corto, incluyendo una corrección agnóstica al horizonte.

    ``por_horizonte=False`` permite que H2--H6 compartan evidencia de volumen
    ya cerrada. Es la hipótesis que se quiere probar cuando cada horizonte por
    separado tiene muy pocas semanas para aprender.
    """

    # El primer candidato debe ser una copia exacta de la curva base. El valor
    # por defecto ``peso_correccion=1`` representa una corrección completa, no
    # una ausencia de corrección.
    salida = [ConfiguracionCorreccionHorizonte(peso_correccion=0.0)]
    # El módulo se deja disponible en la API, pero no entra al loop por defecto:
    # con pocas semanas y clima compartido produce configuraciones frágiles.
    for por_horizonte in (True, False):
        for nivel in ("global", "fundo"):
            for ventana in (4, 8, 12):
                for regularizacion in (2.0, 6.0, 12.0):
                    for peso in (0.50, 0.75, 1.0):
                        salida.append(
                            ConfiguracionCorreccionHorizonte(
                                nivel=nivel,
                                ventana=ventana,
                                regularizacion=regularizacion,
                                peso_correccion=peso,
                                por_horizonte=por_horizonte,
                            )
                        )
    return salida


def ejecutar_loop_horizonte(
    panel: pd.DataFrame,
    *,
    fecha_desarrollo_hasta: pd.Timestamp | str | None = None,
    configuraciones: list[ConfiguracionCorreccionHorizonte] | None = None,
    panel_historial: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Screening candidate-only con separación desarrollo/holdout temporal."""

    base = normalizar_panel(panel)
    historial_base = normalizar_panel(panel_historial) if panel_historial is not None else base
    # Para seleccionar configuraciones sólo importa el volumen por fundo y
    # horizonte. La salida final puede volver a aplicarse al detalle por lote.
    # Agregar aquí evita repetir 180 mil filas en cada candidato del screening.
    columnas_agregacion = [
        "campania",
        "fecha_emision",
        "fecha_objetivo",
        "horizonte_semanas",
        "fundo",
    ]
    reducido = base.groupby(columnas_agregacion, as_index=False, dropna=False).agg(
        p50_kg=("p50_kg", "sum"),
        real_kg=("real_kg", lambda valores: valores.sum(min_count=1)),
        modulo=("modulo", "first"),
    )
    reducido["lote_id"] = "__AGREGADO_FUNDO__"
    reducido_historial = historial_base.groupby(
        columnas_agregacion, as_index=False, dropna=False
    ).agg(
        p50_kg=("p50_kg", "sum"),
        real_kg=("real_kg", lambda valores: valores.sum(min_count=1)),
        modulo=("modulo", "first"),
    )
    reducido_historial["lote_id"] = "__AGREGADO_FUNDO__"
    fecha_max = base["fecha_objetivo"].max()
    corte = (
        pd.Timestamp(fecha_desarrollo_hasta)
        if fecha_desarrollo_hasta is not None
        else fecha_max - pd.Timedelta(days=42)
    )
    candidatos = configuraciones or configuraciones_loop()
    filas: list[dict[str, Any]] = []
    cache: dict[str, pd.DataFrame] = {}
    historial_por_nivel: dict[str, pd.DataFrame] = {}
    for config in candidatos:
        clave = repr(asdict(config))
        if config.nivel not in historial_por_nivel:
            historial_por_nivel[config.nivel] = _historial_canonico(reducido_historial, config)
        candidato = cache.setdefault(
            clave,
            _aplicar_normalizado(
                reducido,
                config,
                historico=historial_por_nivel[config.nivel],
            ),
        )
        # La selección se hace sobre una curva vintage coherente. Sin esto, el
        # mismo objetivo aparece varias veces con emisiones distintas y el
        # resultado depende de cuántas versiones históricas tenga cada semana.
        vintage = _seleccionar_vintage_normalizado(candidato)
        desarrollo = vintage.loc[vintage["fecha_objetivo"].le(corte)]
        holdout = vintage.loc[vintage["fecha_objetivo"].gt(corte)]
        m_dev = metricas_horizonte(desarrollo)
        m_hold = metricas_horizonte(holdout)
        fila: dict[str, Any] = {
            "configuracion": asdict(config),
            "corte_desarrollo": str(corte.date()),
        }
        for nombre, met in (("desarrollo", m_dev), ("holdout", m_hold)):
            fila[f"{nombre}_wape"] = (
                float(np.average(met["wape"], weights=met["real_kg"].abs()))
                if not met.empty
                else np.nan
            )
            fila[f"{nombre}_bias_abs"] = (
                float(np.average(met["bias_pct"].abs(), weights=met["real_kg"].abs()))
                if not met.empty
                else np.nan
            )
            fila[f"{nombre}_n"] = int(met["n_emision_objetivo"].sum()) if not met.empty else 0
        filas.append(fila)
    ranking = (
        pd.DataFrame(filas)
        .sort_values(["desarrollo_wape", "desarrollo_bias_abs"], na_position="last")
        .reset_index(drop=True)
    )
    mejor = ranking.iloc[0].to_dict() if not ranking.empty else {}
    return {
        "schema": "screening-pronostico-horizonte-v1",
        "corte_desarrollo": str(corte.date()),
        "fecha_maxima_objetivo": str(fecha_max.date()),
        "n_configuraciones": len(candidatos),
        "ranking": ranking.to_dict("records"),
        "mejor_por_desarrollo": mejor,
        "persistible": False,
        "motivo": "screening candidate-only; requiere contrato, bootstrap y aprobación",
    }


def _seleccionar_vintage_normalizado(tabla: pd.DataFrame) -> pd.DataFrame:
    """Versión interna para no repetir validación dentro del loop."""

    elegibles = tabla.loc[tabla["fecha_emision"].lt(tabla["fecha_objetivo"])].copy()
    if elegibles.empty:
        return elegibles
    claves = ["campania", "fecha_objetivo", "horizonte_semanas"]
    elegida = (
        elegibles.groupby(claves, as_index=False)["fecha_emision"]
        .max()
        .rename(columns={"fecha_emision": "_emision_elegida"})
    )
    return (
        elegibles.merge(elegida, on=claves, how="inner", validate="many_to_one")
        .loc[lambda frame: frame["fecha_emision"].eq(frame["_emision_elegida"])]
        .drop(columns="_emision_elegida")
    )


def ejecutar_loop_por_horizonte(
    panel: pd.DataFrame,
    *,
    horizontes: tuple[int, ...] = (1, 2, 3, 4, 5, 6),
    fecha_desarrollo_hasta: pd.Timestamp | str | None = None,
    configuraciones: list[ConfiguracionCorreccionHorizonte] | None = None,
) -> dict[str, Any]:
    """Selecciona una configuración independiente para cada horizonte.

    La corrección que funciona a una semana no se impone a seis semanas. Cada
    horizonte mantiene su propio desarrollo/holdout y el resultado es siempre
    candidate-only: no escribe en PostgreSQL ni cambia releases.
    """

    base = normalizar_panel(panel)
    resultados: dict[str, Any] = {}
    for horizonte in horizontes:
        h = int(horizonte)
        sub = base.loc[base["horizonte_semanas"].eq(h)].copy()
        if sub.empty:
            resultados[str(h)] = {
                "schema": "screening-pronostico-horizonte-v1",
                "horizonte": h,
                "n_filas": 0,
                "persistible": False,
                "motivo": "sin observaciones para el horizonte",
            }
            continue
        resultado = ejecutar_loop_horizonte(
            sub,
            fecha_desarrollo_hasta=fecha_desarrollo_hasta,
            configuraciones=configuraciones,
            panel_historial=base,
        )
        resultado["horizonte"] = h
        resultados[str(h)] = resultado
    return {
        "schema": "screening-pronostico-por-horizonte-v1",
        "horizontes": list(map(int, horizontes)),
        "resultados": resultados,
        "mejor_por_horizonte": {
            h: resultado.get("mejor_por_desarrollo", {})
            for h, resultado in resultados.items()
            if resultado.get("mejor_por_desarrollo")
        },
        "persistible": False,
        "motivo": "screening candidate-only; cada horizonte se selecciona por separado",
    }

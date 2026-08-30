"""Coherencia lote → módulo → fundo → empresa y comparación de reconciliadores."""

from __future__ import annotations

import numpy as np
import pandas as pd

NIVELES = ["empresa", "fundo", "modulo", "lote"]
CUANTILES = ["p10_kg", "p50_kg", "p90_kg"]


def mint_shrink_no_negativo(
    pronosticos: pd.DataFrame,
    matriz_s: pd.DataFrame,
    etiquetas: dict[str, np.ndarray],
    historico: pd.DataFrame,
) -> pd.DataFrame:
    """Ejecuta MinT-shrink no negativo con el contrato oficial de HierarchicalForecast.

    ``pronosticos`` debe estar en formato ``unique_id, ds, <modelo>`` y ``historico`` en
    ``unique_id, ds, y``. La promoción del resultado sigue dependiendo del desempeño
    rolling-origin; esta función no declara a MinT ganador por construcción.
    """
    try:
        from hierarchicalforecast.core import HierarchicalReconciliation
        from hierarchicalforecast.methods import MinTrace
    except ImportError as exc:  # pragma: no cover - depende del extra de producción
        raise RuntimeError("Instale HierarchicalForecast para habilitar MinT-shrink.") from exc

    reconciliador = HierarchicalReconciliation(
        reconcilers=[MinTrace(method="mint_shrink", nonnegative=True, num_threads=-1)]
    )
    return reconciliador.reconcile(
        Y_hat_df=pronosticos,
        Y_df=historico,
        S_df=matriz_s,
        tags=etiquetas,
    )


def bottom_up(lotes: pd.DataFrame) -> pd.DataFrame:
    """Agrega cuantiles marginales; P10/P90 agregados no representan un cuantil conjunto."""
    filas = []
    base = lotes.copy()
    comunes = ["modelo", "fecha_emision", "fecha_objetivo", "horizonte_semanas", "banda_horizonte"]
    for i, nivel in enumerate(NIVELES):
        dims = NIVELES[: i + 1]
        grupo = [*comunes, *dims]
        agregado = base.groupby(grupo, dropna=False, as_index=False)[CUANTILES].sum()
        agregado["nivel"] = nivel
        agregado["metodo_reconciliacion"] = "BottomUp"
        filas.append(agregado)
    return pd.concat(filas, ignore_index=True, sort=False)


def verificar_coherencia(reconciliado: pd.DataFrame, tolerancia: float = 1e-8) -> pd.DataFrame:
    """Comprueba P50 en cada salto de la jerarquía."""
    claves_tiempo = ["modelo", "fecha_emision", "fecha_objetivo"]
    pruebas = []
    for padre, hijo in zip(NIVELES[:-1], NIVELES[1:], strict=True):
        dims_padre = NIVELES[: NIVELES.index(padre) + 1]
        p = (
            reconciliado[reconciliado.nivel == padre]
            .groupby([*claves_tiempo, *dims_padre], dropna=False)
            .p50_kg.sum()
        )
        h = (
            reconciliado[reconciliado.nivel == hijo]
            .groupby([*claves_tiempo, *dims_padre], dropna=False)
            .p50_kg.sum()
        )
        diferencia = p.subtract(h, fill_value=0).abs()
        pruebas.append(
            {
                "regla": f"suma_{hijo}_igual_{padre}",
                "observados": len(diferencia),
                "afectados": int((diferencia > tolerancia).sum()),
                "max_diferencia_kg": float(diferencia.max()) if len(diferencia) else 0,
                "estado": "ok" if (diferencia <= tolerancia).all() else "error",
            }
        )
    return pd.DataFrame(pruebas)


def seleccionar_reconciliador(
    metricas_bottom_up: pd.DataFrame, metricas_mint: pd.DataFrame | None = None
) -> dict[str, object]:
    """MinT-shrink no negativo solo gana por desempeño fuera de muestra."""
    if metricas_mint is None or metricas_mint.empty:
        return {"metodo": "BottomUp", "razon": "MinT aún no tiene evaluación comparable."}
    bu = metricas_bottom_up.set_index("banda_horizonte").wape
    mt = metricas_mint.set_index("banda_horizonte").wape
    comunes = bu.index.intersection(mt.index)
    mejora = 1 - mt.loc[comunes] / bu.loc[comunes]
    if len(comunes) and np.isfinite(mejora).all() and (mejora > 0).all():
        return {"metodo": "MinT_shrink_nonnegative", "mejora_wape": mejora.to_dict()}
    return {"metodo": "BottomUp", "razon": "MinT no mejora todos los horizontes fuera de muestra."}

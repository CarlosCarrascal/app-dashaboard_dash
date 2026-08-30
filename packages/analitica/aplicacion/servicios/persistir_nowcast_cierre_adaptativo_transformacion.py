"""Transformacion y evaluacion del panel del nowcast de cierre adaptativo."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd


def metric(table: pd.DataFrame, column: str) -> dict[str, float | int]:
    paired = table.loc[table[column].notna()].copy()
    company = paired.groupby("fecha_objetivo", as_index=False)[["real_kg", column]].sum()
    error = company[column] - company.real_kg
    denominator = float(company.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / denominator),
        "bias": float(error.sum() / denominator),
        "mae_kg": float(error.abs().mean()),
        "n_weeks": int(len(company)),
        "real_kg": denominator,
    }


def bootstrap(table: pd.DataFrame, reference: str) -> dict[str, Any]:
    paired = table.loc[table[reference].notna()].copy()
    company = paired.groupby("fecha_objetivo", as_index=False)[
        ["real_kg", "candidate_kg", reference]
    ].sum()
    candidate_error = (company.candidate_kg - company.real_kg).abs().to_numpy(float)
    reference_error = (company[reference] - company.real_kg).abs().to_numpy(float)
    real = company.real_kg.abs().to_numpy(float)
    rng = np.random.default_rng(20260826)
    differences: list[float] = []
    for _ in range(20_000):
        indices = rng.integers(0, len(company), len(company))
        denominator = float(real[indices].sum())
        if denominator:
            differences.append(
                float(
                    (candidate_error[indices].sum() - reference_error[indices].sum()) / denominator
                )
            )
    interval = np.quantile(differences, [0.025, 0.975])
    point = float((candidate_error.sum() - reference_error.sum()) / real.sum())
    return {
        "reference": reference,
        "n_weeks": int(len(company)),
        "difference_wape_pp": 100.0 * point,
        "ci95_difference_wape_pp": [100.0 * float(interval[0]), 100.0 * float(interval[1])],
        "weeks_won": int((candidate_error < reference_error).sum()),
    }


def build_candidate(
    *,
    artifact,
    real_access,
    r09_access,
    normalizar_detalle_artifact: Callable[..., pd.DataFrame],
    append_latest_closed_week: Callable[..., pd.DataFrame],
    calcular_nowcast_cierre_adaptativo: Callable[..., Any],
    metric: Callable[..., dict[str, float | int]],
    bootstrap: Callable[..., dict[str, Any]],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    base = normalizar_detalle_artifact(artifact)
    panel = append_latest_closed_week(base, real_access=real_access, r09_access=r09_access)
    contract = panel[
        [
            "campania",
            "fecha_objetivo",
            "fecha_corte_asof",
            "fundo_operativo",
            "macro_kg",
            "montue_kg",
            "dias_montue_observados",
            "real_kg",
        ]
    ].copy()
    result = calcular_nowcast_cierre_adaptativo(contract)
    # El artefacto de screening conserva columnas derivadas de una corrida previa
    # (candidate_kg, coeficientes, estado, etc.).  Nunca deben prevalecer sobre la
    # salida recalculada por el modulo puro que se pretende publicar.
    claves_modelo = {
        "campania",
        "fecha_objetivo",
        "fecha_corte_asof",
        "fundo_operativo",
        "macro_kg",
        "montue_kg",
        "dias_montue_observados",
        "real_kg",
    }
    derivadas_modelo = set(result.predicciones.columns).difference(claves_modelo)
    panel_fuente = panel.drop(
        columns=sorted(derivadas_modelo.intersection(panel.columns)),
        errors="ignore",
    )
    output = panel_fuente.merge(
        result.predicciones,
        on=[
            "campania",
            "fecha_objetivo",
            "fecha_corte_asof",
            "fundo_operativo",
            "macro_kg",
            "montue_kg",
            "dias_montue_observados",
            "real_kg",
        ],
        how="inner",
        validate="one_to_one",
    )
    if len(output) != len(panel):
        raise RuntimeError("El motor no devolvio el mismo universo de entrada")
    if not output.estado_nowcast.eq("calculado").all() or output.candidate_kg.isna().any():
        raise RuntimeError("Existen semanas sin nowcast calculado")
    reconciliation = output.groupby("fecha_objetivo").apply(
        lambda x: abs(float(x.candidate_kg.sum()) - float(x.recon_total_empresa_kg.iloc[0])),
        include_groups=False,
    )
    if float(reconciliation.max()) > 1e-6:
        raise RuntimeError("La reconciliacion empresa-fundos no cierra")

    metrics = {
        "candidate": metric(output, "candidate_kg"),
        "macro": metric(output, "macro_kg"),
        "r09_preweek": metric(output, "r09_presemana_kg"),
        "r09_sameweek": metric(output, "r09_misma_semana_kg"),
        "bootstrap_vs_macro": bootstrap(output, "macro_kg"),
        "bootstrap_vs_r09_sameweek": bootstrap(output, "r09_misma_semana_kg"),
        "configuration_id": result.configuracion_id,
        "configuration": result.configuracion,
        "max_reconciliation_error_kg": float(reconciliation.max()),
    }
    if metrics["candidate"]["wape"] > 0.15:
        raise RuntimeError("El candidato no cumple la meta WAPE <= 15 %")
    if abs(metrics["candidate"]["bias"]) > 0.10:
        raise RuntimeError("El candidato no cumple |bias| <= 10 %")
    if metrics["candidate"]["wape"] >= metrics["macro"]["wape"]:
        raise RuntimeError("El candidato no mejora a Macro")
    return output, metrics


__all__ = ["bootstrap", "build_candidate", "metric"]

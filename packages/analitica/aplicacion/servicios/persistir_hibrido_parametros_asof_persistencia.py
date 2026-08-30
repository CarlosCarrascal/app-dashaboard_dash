"""Persistencia candidate-only con orden de efectos histórico."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd


def persistir_candidato(
    dsn: str,
    datos: Any,
    full: pd.DataFrame,
    calidad_pred: pd.DataFrame,
    snapshots: pd.DataFrame,
    reporte_full: Mapping[str, Any],
    contrato_baselines: Any,
    solicitud: Any,
    *,
    metricas: Callable[[pd.DataFrame], pd.DataFrame],
    repositorio: Callable[..., Any],
    calidad_preflight: Callable[[Mapping[str, Any]], pd.DataFrame],
    nombre_modelo: str,
    version_modelo: str,
) -> tuple[int, int, pd.DataFrame]:
    """Persiste solo el challenger tras superar ambos preflight.

    El bloque ``try`` empieza después de crear el run, igual que en la ruta
    histórica, para conservar tanto el orden como el cierre en estado ``failed``.
    """

    tabla_metricas = metricas(full)
    repo = repositorio(dsn)
    snapshot_id = repo.snapshot(datos)
    run_id = repo.crear_run(
        snapshot_id,
        "backtest",
        {
            "candidate_only": True,
            "modelo": nombre_modelo,
            "version_modelo": version_modelo,
            "campania": str(solicitud.campania),
            "horizonte_semanas": int(solicitud.horizonte),
            "max_cortes": int(solicitud.max_cortes),
            "baseline_run_ids": {
                clave: int(valor) for clave, valor in sorted(solicitud.referencias.items())
            },
            "evaluation_contract_id": contrato_baselines.evaluation_contract_id,
            "evaluation_contract_keyset_sha256": contrato_baselines.keyset_sha256,
            "evaluation_contract_closed_calendar_sha256": (
                contrato_baselines.closed_calendar_sha256
            ),
            "baseline_hashes": reporte_full.get("baseline_hashes", {}),
            "keyset_sha256": reporte_full.get("keyset_sha256"),
            "closed_calendar_sha256": reporte_full.get("closed_calendar_sha256"),
            "evaluation_passed": True,
            "published": False,
            "replay": "rolling_origin_candidate_only",
        },
    )
    try:
        repo.guardar_predicciones(run_id, full)
        repo.guardar_metricas(run_id, tabla_metricas)
        repo.guardar_calidad(
            snapshot_id,
            run_id,
            pd.concat(
                [calidad_pred, calidad_preflight(reporte_full)],
                ignore_index=True,
            ),
        )
        if not snapshots.empty:
            repo.guardar_parametros_legacy(run_id, snapshots)
        repo.finalizar_run(run_id, "succeeded")
    except Exception as exc:
        repo.finalizar_run(run_id, "failed", str(exc))
        raise
    return run_id, snapshot_id, tabla_metricas


__all__ = ["persistir_candidato"]

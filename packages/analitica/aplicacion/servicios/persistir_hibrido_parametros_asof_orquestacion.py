"""Orquestación del flujo candidate-only sin conocer implementaciones concretas."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .persistir_hibrido_parametros_asof_configuracion import SolicitudEjecucion


def ejecutar(
    *,
    campania: str,
    referencias: Mapping[str, int],
    hashes_esperados: Mapping[str, str] | None,
    expected_keyset_hash: str | None,
    horizonte: int,
    max_cortes: int,
    excel_root: str | None,
    preflight_only: bool,
    dry_run: bool,
    cache_dir: str | None,
    validar_referencias: Callable[[Mapping[str, int]], None],
    postgres_dsn: Callable[[], str | None],
    consultar_contrato: Callable[[str, Mapping[str, int], str], Any],
    hash_json: Callable[[Any], str],
    consultar_snapshot: Callable[[str], Any],
    emisiones_desde_forecast: Callable[[Any, str], Any],
    seleccionar_micro: Callable[..., Any],
    consultar_baselines: Callable[..., Any],
    cache_factory: Callable[[str | None], Any],
    candidate_cache: Callable[..., Any],
    evaluar_preflight: Callable[..., Any],
    controles_predicciones: Callable[..., Any],
    persistir_candidato: Callable[..., Any],
    exit_ok: int,
    exit_contract_rejected: int,
    nombre_modelo: str,
    version_modelo: str,
) -> dict[str, Any]:
    """Ejecuta micro-replay, replay completo y persistencia en ese orden."""

    solicitud = SolicitudEjecucion(
        campania=campania,
        referencias=referencias,
        hashes_esperados=hashes_esperados,
        expected_keyset_hash=expected_keyset_hash,
        horizonte=int(horizonte),
        max_cortes=int(max_cortes),
        excel_root=excel_root,
        preflight_only=bool(preflight_only),
        dry_run=bool(dry_run),
        cache_dir=cache_dir,
    )
    validar_referencias(solicitud.referencias)
    dsn = postgres_dsn()
    if not dsn:
        raise RuntimeError("No hay DSN de PostgreSQL configurado.")
    contrato_baselines = consultar_contrato(
        dsn,
        solicitud.referencias,
        str(solicitud.campania),
    )
    fuente_clave = hash_json(
        {
            "schema": "screening-source-v1",
            "campania": solicitud.campania,
            "evaluation_contract_id": contrato_baselines.evaluation_contract_id,
            "keyset_sha256": contrato_baselines.keyset_sha256,
            "closed_calendar_sha256": contrato_baselines.closed_calendar_sha256,
            "source_hashes": contrato_baselines.source_hashes,
        }
    )
    datos, meta_fuente = consultar_snapshot(fuente_clave)
    emisiones_todas = emisiones_desde_forecast(datos, solicitud.campania)
    emisiones_micro = seleccionar_micro(
        emisiones_todas,
        datos.cosecha,
        solicitud.campania,
        cerrado_hasta=contrato_baselines.cerrado_hasta,
    )
    if emisiones_micro.empty:
        return {
            "schema_version": "hpa-runner-v1",
            "estado": "contract_rejected",
            "exit_code": exit_contract_rejected,
            "contratos": [{"regla": "emisiones_micro_disponibles", "afectados": 0}],
        }
    baselines_micro = consultar_baselines(
        dsn,
        solicitud.referencias,
        solicitud.campania,
        cerrado_hasta=contrato_baselines.cerrado_hasta,
        fechas_emision=emisiones_micro.fecha_emision,
    )
    cache = cache_factory(solicitud.cache_dir)
    micro, _, meta_micro = candidate_cache(
        datos,
        emisiones_micro,
        campania=solicitud.campania,
        horizonte=6,
        max_cortes=None,
        excel_root=solicitud.excel_root,
        cache=cache,
        fase="micro",
    )
    reporte_micro = evaluar_preflight(
        micro,
        baselines_micro,
        campania=solicitud.campania,
        cosecha=datos.cosecha,
        baseline_run_ids=solicitud.referencias,
        hashes_esperados=solicitud.hashes_esperados,
        expected_keyset_sha256=solicitud.expected_keyset_hash,
        cerrado_hasta=contrato_baselines.cerrado_hasta,
    )
    resultado: dict[str, Any] = {
        "schema_version": "hpa-runner-v1",
        "modelo": nombre_modelo,
        "version_modelo": version_modelo,
        "campania": solicitud.campania,
        "candidate_only": True,
        "baseline_run_ids": {
            clave: int(valor) for clave, valor in sorted(solicitud.referencias.items())
        },
        "evaluation_contract_id": contrato_baselines.evaluation_contract_id,
        "evaluation_contract_keyset_sha256": contrato_baselines.keyset_sha256,
        "evaluation_contract_closed_calendar_sha256": (
            contrato_baselines.closed_calendar_sha256
        ),
        "evaluation_contract_cerrado_hasta": contrato_baselines.cerrado_hasta,
        "baseline_release_source_hashes": contrato_baselines.source_hashes,
        "source_snapshot": meta_fuente,
        "micro_replay": reporte_micro,
        "micro_meta": meta_micro,
        "persistido": False,
    }
    if reporte_micro["exit_code"] != exit_ok or solicitud.preflight_only:
        resultado.update(
            {"estado": reporte_micro["estado"], "exit_code": int(reporte_micro["exit_code"])}
        )
        return resultado

    limite = None if solicitud.max_cortes == 0 else solicitud.max_cortes
    full, snapshots, meta_full = candidate_cache(
        datos,
        emisiones_todas,
        campania=solicitud.campania,
        horizonte=solicitud.horizonte,
        max_cortes=limite,
        excel_root=solicitud.excel_root,
        cache=cache,
        fase="full",
    )
    reporte_full = evaluar_preflight(
        full,
        consultar_baselines(
            dsn,
            solicitud.referencias,
            solicitud.campania,
            cerrado_hasta=contrato_baselines.cerrado_hasta,
        ),
        campania=solicitud.campania,
        cosecha=datos.cosecha,
        baseline_run_ids=solicitud.referencias,
        hashes_esperados=solicitud.hashes_esperados,
        expected_keyset_sha256=solicitud.expected_keyset_hash,
        cerrado_hasta=contrato_baselines.cerrado_hasta,
    )
    resultado.update({"replay_completo": reporte_full, "full_meta": meta_full})
    if reporte_full["exit_code"] != exit_ok or solicitud.dry_run:
        resultado.update(
            {"estado": reporte_full["estado"], "exit_code": int(reporte_full["exit_code"])}
        )
        return resultado

    calidad_pred = controles_predicciones(full)
    if calidad_pred.estado.eq("error").any():
        resultado.update(
            {
                "estado": "contract_rejected",
                "exit_code": exit_contract_rejected,
                "calidad_predicciones": calidad_pred.to_dict("records"),
            }
        )
        return resultado
    run_id, snapshot_id, tabla_metricas = persistir_candidato(
        dsn,
        datos,
        full,
        calidad_pred,
        snapshots,
        reporte_full,
        contrato_baselines,
        solicitud,
    )
    resultado.update(
        {
            "estado": "persisted_candidate",
            "exit_code": exit_ok,
            "persistido": True,
            "run_id": run_id,
            "snapshot_id": snapshot_id,
            "n_predicciones": int(len(full)),
            "n_metricas": int(len(tabla_metricas)),
            "n_snapshots_parametros": int(len(snapshots)),
        }
    )
    return resultado


__all__ = ["ejecutar"]

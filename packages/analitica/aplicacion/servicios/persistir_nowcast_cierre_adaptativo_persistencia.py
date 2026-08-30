"""Persistencia transaccional del release historico del nowcast de cierre."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pandas as pd


def baseline_release_hashes(connection: Any, *, modelo: str) -> dict[str, str]:
    query = """
        SELECT campania, modelo, uso, source_hash
        FROM analytics.model_series_release
        WHERE activo AND modelo <> %s
        ORDER BY campania, modelo, uso
    """
    with connection.cursor() as cursor:
        cursor.execute(query, (modelo,))
        return {"|".join(map(str, row[:3])): str(row[3]) for row in cursor.fetchall()}


def persist(
    output: pd.DataFrame,
    metrics: dict[str, Any],
    *,
    artifact,
    real_access,
    r09_access,
    apply: bool,
    serialized: tuple[pd.DataFrame, dict[str, Any]],
    baseline_release_hashes: Callable[..., dict[str, str]],
    settings_module: Any,
    psycopg_module: Any,
    repository_factory: Callable[..., Any],
    modelo: str,
    version: str,
    campaign: str,
    records_hash: Callable[..., str],
    json_hash: Callable[[Any], str],
    fundos: tuple[str, ...],
) -> dict[str, Any]:
    rows, serialized_values = serialized
    report = serialized_values["report"]
    source_hash = serialized_values["source_hash"]
    prediction_hash = serialized_values["prediction_hash"]
    if not apply:
        return report

    dsn = settings_module.postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL no esta configurado")
    repo = repository_factory(dsn)
    run_id: int | None = None
    with psycopg_module.connect(dsn) as connection:
        before = baseline_release_hashes(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT release_id, run_id
                FROM analytics.model_series_release
                WHERE campania=%s AND modelo=%s AND uso='historico'
                  AND activo AND source_hash=%s
                """,
                (campaign, modelo, source_hash),
            )
            existing = cursor.fetchone()
            if existing:
                report.update(
                    {
                        "status": "already_published",
                        "release_id": existing[0],
                        "run_id": existing[1],
                    }
                )
                return report

            snapshot_signature = json_hash(
                {"schema": "nowcast-source-snapshot-v1", **report["source"]}
            )
            cursor.execute(
                """
                INSERT INTO analytics.dataset_snapshot
                    (fuente, firma, corte_datos, esquema_version, tablas, cobertura, advertencias)
                VALUES ('postgres', %s, TIMESTAMPTZ '2026-08-21 23:59:59-05',
                        'nowcast-source-v1', %s::jsonb, %s::jsonb, '[]'::jsonb)
                ON CONFLICT (firma) DO UPDATE SET firma=EXCLUDED.firma
                RETURNING snapshot_id
                """,
                (
                    snapshot_signature,
                    json.dumps(report["source"]),
                    json.dumps(
                        {
                            "campania": campaign,
                            "fundos": list(fundos),
                            "semanas": int(output.fecha_objetivo.nunique()),
                        }
                    ),
                ),
            )
            snapshot_id = int(cursor.fetchone()[0])
            cursor.execute(
                """
                INSERT INTO analytics.forecast_run
                    (snapshot_id, tipo, estado, codigo_commit, configuracion, inicio)
                VALUES (%s, 'backtest', 'running', NULL, %s::jsonb, now())
                RETURNING run_id
                """,
                (
                    snapshot_id,
                    json.dumps(
                        {
                            "candidate_only": True,
                            "modelo": modelo,
                            "version_modelo": version,
                            "producto": "cierre_intra_semanal_miercoles",
                            "horizonte_semanas": 0,
                            "configuration_id": metrics["configuration_id"],
                            "r09_predictor": False,
                            "evaluation_passed": True,
                            "published_forecast": False,
                        }
                    ),
                ),
            )
            run_id = int(cursor.fetchone()[0])

    try:
        repo.guardar_nowcast_semanal(run_id, rows)
        metric_rows = []
        for label, values in metrics.items():
            if not isinstance(values, dict) or "wape" not in values:
                continue
            metric_rows.append(
                {
                    "modelo": f"{modelo}:{label}",
                    "campania": campaign,
                    "fundo": None,
                    "horizonte_semanas": 0,
                    "banda_horizonte": "operativo",
                    "n": int(values["n_weeks"]),
                    "wape": values["wape"],
                    "sesgo_pct": values["bias"],
                    "mae_kg": values["mae_kg"],
                    "volumen_real_kg": values["real_kg"],
                }
            )
        repo.guardar_metricas(run_id, pd.DataFrame(metric_rows))

        key_columns = ["campania", "semana_inicio", "fundo"]
        fund_rows = rows.loc[rows.fundo.ne("Empresa")].copy()
        keyset = records_hash(fund_rows, key_columns)
        weeks = sorted(pd.to_datetime(fund_rows.semana_inicio).dt.date.unique())
        calendar_hash = json_hash([week.isoformat() for week in weeks])
        contract_signature = json_hash(
            {
                "schema": "nowcast-evaluation-contract-v1",
                "campania": campaign,
                "snapshot_id": snapshot_id,
                "keyset": keyset,
                "calendar": calendar_hash,
                "horizonte": 0,
            }
        )
        with psycopg_module.connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO analytics.evaluation_contract (
                    firma, campania, snapshot_id, granularidad,
                    fecha_inicio_objetivo, fecha_fin_objetivo, cerrado_hasta,
                    horizontes_semanas, emisiones_elegibles, semanas_cerradas,
                    keyset_sha256, closed_calendar_sha256, volumen_real_kg,
                    n_unidades, n_emisiones, estado, metadatos,
                    creado_por, aprobado_en, aprobado_por
                ) VALUES (
                    %s,%s,%s,'fundo_semana',%s,%s,%s,ARRAY[0]::smallint[],
                    %s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,'approved',%s::jsonb,
                    'persistir_nowcast_cierre_adaptativo.py',now(),'loop_agentico_2026_08_26'
                )
                ON CONFLICT (firma) DO UPDATE SET
                    metadatos=EXCLUDED.metadatos,
                    aprobado_en=EXCLUDED.aprobado_en,
                    aprobado_por=EXCLUDED.aprobado_por
                RETURNING evaluation_contract_id
                """,
                (
                    contract_signature,
                    campaign,
                    snapshot_id,
                    weeks[0],
                    weeks[-1],
                    weeks[-1] + pd.Timedelta(days=6),
                    json.dumps(
                        [
                            (pd.Timestamp(week) + pd.Timedelta(days=2)).date().isoformat()
                            for week in weeks
                        ]
                    ),
                    json.dumps([week.isoformat() for week in weeks]),
                    keyset,
                    calendar_hash,
                    float(fund_rows.real_kg.sum()),
                    int(len(fund_rows)),
                    int(len(weeks)),
                    json.dumps(
                        {
                            "producto": "nowcast_cierre_semanal",
                            "comparacion": "mismo universo empresa-semana",
                            "resultado": "mejora_macro_equivalente_estadisticamente_r09_sameweek",
                            "metrics": metrics,
                        }
                    ),
                ),
            )
            contract_id = int(cursor.fetchone()[0])
            cursor.execute(
                """
                UPDATE analytics.model_series_release
                SET activo=false, estado='withdrawn', retirado_en=now()
                WHERE campania=%s AND modelo=%s AND uso='historico' AND activo
                """,
                (campaign, modelo),
            )
            cursor.execute(
                """
                INSERT INTO analytics.model_series_release (
                    evaluation_contract_id, run_id, snapshot_id, campania,
                    modelo, version_modelo, uso, estado, estado_evaluacion,
                    activo, source_hash, predicciones_sha256, metadatos,
                    creado_por, aprobado_en, aprobado_por
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,'historico','approved','passed',true,
                    %s,%s,%s::jsonb,'persistir_nowcast_cierre_adaptativo.py',
                    now(),'loop_agentico_2026_08_26'
                ) RETURNING release_id
                """,
                (
                    contract_id,
                    run_id,
                    snapshot_id,
                    campaign,
                    modelo,
                    version,
                    source_hash,
                    prediction_hash,
                    json.dumps(
                        {
                            "uso_autorizado": "cierre_de_semana_desde_miercoles",
                            "no_es": "forecast_presemana_1_6",
                            "estado_frente_macro": "mejora_comprobada",
                            "estado_frente_r09_sameweek": (
                                "equivalencia_estadistica_no_superioridad"
                            ),
                            "metrics": metrics,
                        }
                    ),
                ),
            )
            release_id = int(cursor.fetchone()[0])
            cursor.execute(
                "UPDATE analytics.forecast_run SET estado='succeeded', fin=now() WHERE run_id=%s",
                (run_id,),
            )
            after = baseline_release_hashes(connection)
            if before != after:
                raise RuntimeError("La persistencia altero hashes de releases baseline")
        report.update(
            {
                "status": "published_historical_nowcast",
                "snapshot_id": snapshot_id,
                "run_id": run_id,
                "evaluation_contract_id": contract_id,
                "release_id": release_id,
                "baseline_release_hashes_unchanged": True,
            }
        )
        return report
    except Exception as exc:
        if run_id is not None:
            repo.finalizar_run(run_id, "failed", str(exc))
        raise


__all__ = ["baseline_release_hashes", "persist"]

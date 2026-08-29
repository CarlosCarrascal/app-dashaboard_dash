"""Efectos de escritura para contratos y releases de replay."""

from __future__ import annotations

import json
from typing import Any

from .certificar_releases_replay_contratos import (
    RELEASE_OPERATIVA,
    RUNS_RECHAZADOS,
    Certificacion,
)
from .certificar_releases_replay_lectura import (
    _SQL_OPERATIVA_PREDICCIONES,
    _SQL_SERIES_RECHAZADAS,
    _filas,
    _snapshot,
)
from .certificar_releases_replay_serializacion import _sha256


def _registrar_release_operativa(cursor) -> dict[str, Any]:
    run_id = int(RELEASE_OPERATIVA["run_id"])
    campania = str(RELEASE_OPERATIVA["campania"])
    modelo = str(RELEASE_OPERATIVA["modelo"])
    version = str(RELEASE_OPERATIVA["version"])
    snapshot_id = _snapshot(cursor, run_id)
    filas = _filas(
        cursor,
        _SQL_OPERATIVA_PREDICCIONES,
        (run_id, campania, modelo, version),
    )
    if not filas:
        raise ValueError(f"{campania}/{modelo}: corrida operativa vacía")
    claves = [(fila[0], fila[1], fila[2], fila[4]) for fila in filas]
    if len(claves) != len(set(claves)):
        raise ValueError(f"{campania}/{modelo}: claves operativas duplicadas")
    pred_hash = _sha256(
        [
            (
                int(fila[0]),
                fila[1].isoformat(),
                fila[2].isoformat(),
                int(fila[3]),
                str(fila[4]),
                round(float(fila[5]), 6),
                None if fila[6] is None else round(float(fila[6]), 6),
                None if fila[7] is None else round(float(fila[7]), 6),
                None if fila[8] is None else round(float(fila[8]), 6),
                None if fila[9] is None else round(float(fila[9]), 6),
                None if fila[10] is None else round(float(fila[10]), 6),
                str(fila[11]),
            )
            for fila in filas
        ]
    )
    source_hash = _sha256(
        {
            "run_id": run_id,
            "snapshot_id": snapshot_id,
            "campania": campania,
            "modelo": modelo,
            "version": version,
            "prediction_hash": pred_hash,
        }
    )
    cursor.execute(
        """
        UPDATE analytics.model_series_release
        SET activo=false, estado='withdrawn', retirado_en=now()
        WHERE campania=%s AND modelo=%s AND uso='operativo' AND activo
        """,
        (campania, modelo),
    )
    cursor.execute(
        """
        INSERT INTO analytics.model_series_release (
            evaluation_contract_id, run_id, snapshot_id, campania,
            modelo, version_modelo, uso, estado, estado_evaluacion,
            activo, source_hash, predicciones_sha256, metadatos,
            creado_por, aprobado_en, aprobado_por
        ) VALUES (
            NULL, %s, %s, %s, %s, %s, 'operativo', 'approved',
            'not_applicable', true, %s, %s, %s::jsonb,
            'certificar_releases_replay.py', now(), 'operacion_2026_08_25'
        )
        ON CONFLICT (run_id, campania, modelo, version_modelo, uso)
            WHERE uso='operativo'
        DO UPDATE SET
            estado='approved', estado_evaluacion='not_applicable', activo=true,
            source_hash=EXCLUDED.source_hash,
            predicciones_sha256=EXCLUDED.predicciones_sha256,
            metadatos=EXCLUDED.metadatos,
            aprobado_en=EXCLUDED.aprobado_en,
            aprobado_por=EXCLUDED.aprobado_por,
            retirado_en=NULL
        """,
        (
            run_id,
            snapshot_id,
            campania,
            modelo,
            version,
            source_hash,
            pred_hash,
            json.dumps(
                {
                    "nota": RELEASE_OPERATIVA["nota"],
                    "evaluacion_predictiva": "no_aplica_proyeccion_futura",
                    "seleccion": "release_operativa_explicita",
                }
            ),
        ),
    )
    return {
        "campania": campania,
        "run_id": run_id,
        "modelo": modelo,
        "uso": "operativo",
        "filas": len(filas),
        "predicciones_sha256": pred_hash,
    }


def _registrar_contrato(cursor, cert: Certificacion, universo: dict[str, Any]) -> int:
    snapshot_id = _snapshot(cursor, cert.run_id)
    firma = _sha256(
        {
            "schema": "evaluation-contract-v1",
            "campania": cert.campania,
            "snapshot_id": snapshot_id,
            "fecha_inicio": universo["fecha_inicio"].isoformat(),
            "fecha_fin": universo["fecha_fin"].isoformat(),
            "horizontes": list(cert.horizontes),
            "granularidad": cert.granularidad,
            "keyset": universo["keyset_sha256"],
            "calendario": universo["closed_calendar_sha256"],
        }
    )
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
            %s, %s, %s, %s, %s, %s, %s,
            %s::smallint[], %s::jsonb, %s::jsonb,
            %s, %s, %s, %s, %s, 'approved', %s::jsonb,
            'certificar_releases_replay.py', now(), 'auditoria_2026_08_25'
        )
        ON CONFLICT (firma) DO UPDATE SET
            metadatos = EXCLUDED.metadatos,
            aprobado_en = EXCLUDED.aprobado_en,
            aprobado_por = EXCLUDED.aprobado_por
        RETURNING evaluation_contract_id
        """,
        (
            firma,
            cert.campania,
            snapshot_id,
            cert.granularidad,
            universo["fecha_inicio"],
            universo["fecha_fin"],
            universo["cerrado_hasta"],
            list(cert.horizontes),
            json.dumps([fecha.isoformat() for fecha in universo["emisiones"]]),
            json.dumps([fecha.isoformat() for fecha in universo["semanas"]]),
            universo["keyset_sha256"],
            universo["closed_calendar_sha256"],
            universo["volumen_real_kg"],
            universo["n_unidades"],
            universo["n_emisiones"],
            json.dumps(
                {
                    "nota": cert.nota,
                    "run_id": cert.run_id,
                    "uso": "screening" if not cert.curva_stitched else "dashboard",
                }
            ),
        ),
    )
    return int(cursor.fetchone()[0])


def _registrar_releases(
    cursor, cert: Certificacion, contrato_id: int, universo: dict[str, Any]
) -> None:
    snapshot_id = _snapshot(cursor, cert.run_id)
    for serie in cert.series:
        pred_hash = universo["predicciones_sha256"][serie.modelo]
        source_hash = _sha256(
            {
                "run_id": cert.run_id,
                "snapshot_id": snapshot_id,
                "modelo": serie.modelo,
                "version": serie.version,
                "prediction_hash": pred_hash,
            }
        )
        cursor.execute(
            """
            UPDATE analytics.model_series_release
            SET activo=false, estado='withdrawn', retirado_en=now()
            WHERE campania=%s AND modelo=%s AND uso=%s AND activo
            """,
            (cert.campania, serie.modelo, serie.uso),
        )
        cursor.execute(
            """
            INSERT INTO analytics.model_series_release (
                evaluation_contract_id, run_id, snapshot_id, campania,
                modelo, version_modelo, uso, estado, estado_evaluacion,
                activo, source_hash, predicciones_sha256, metadatos,
                creado_por, aprobado_en, aprobado_por
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                'approved', 'passed', true, %s, %s, %s::jsonb,
                'certificar_releases_replay.py', now(), 'auditoria_2026_08_25'
            )
            ON CONFLICT (
                evaluation_contract_id, run_id, campania, modelo, version_modelo, uso
            ) DO UPDATE SET
                estado='approved', estado_evaluacion='passed', activo=true,
                source_hash=EXCLUDED.source_hash,
                predicciones_sha256=EXCLUDED.predicciones_sha256,
                metadatos=EXCLUDED.metadatos,
                aprobado_en=EXCLUDED.aprobado_en,
                aprobado_por=EXCLUDED.aprobado_por,
                retirado_en=NULL
            """,
            (
                contrato_id,
                cert.run_id,
                snapshot_id,
                cert.campania,
                serie.modelo,
                serie.version,
                serie.uso,
                source_hash,
                pred_hash,
                json.dumps({"nota": cert.nota, "certificado_sin_recalculo": True}),
            ),
        )


def _registrar_rechazos(cursor) -> None:
    for run_id in RUNS_RECHAZADOS:
        snapshot_id = _snapshot(cursor, run_id)
        cursor.execute(_SQL_SERIES_RECHAZADAS, (run_id,))
        series = cursor.fetchall()
        for campania, modelo, version in series:
            firma = _sha256(
                {"schema": "rejected-contract-v1", "run_id": run_id, "campania": campania}
            )
            cursor.execute(
                """
                INSERT INTO analytics.evaluation_contract (
                    firma, campania, snapshot_id, granularidad, estado,
                    metadatos, creado_por
                ) VALUES (%s,%s,%s,'lote_semana','rejected',%s::jsonb,%s)
                ON CONFLICT (firma) DO UPDATE SET estado='rejected', metadatos=EXCLUDED.metadatos
                RETURNING evaluation_contract_id
                """,
                (
                    firma,
                    campania,
                    snapshot_id,
                    json.dumps(
                        {
                            "run_id": run_id,
                            "motivo": (
                                "Recalculó baselines con parámetros experimentales; no comparable."
                            ),
                        }
                    ),
                    "certificar_releases_replay.py",
                ),
            )
            contrato_id = int(cursor.fetchone()[0])
            pred_hash = _sha256(
                {"run_id": run_id, "campania": campania, "modelo": modelo, "rechazado": True}
            )
            cursor.execute(
                """
                INSERT INTO analytics.model_series_release (
                    evaluation_contract_id, run_id, snapshot_id, campania,
                    modelo, version_modelo, uso, estado, estado_evaluacion,
                    activo, source_hash, metadatos, creado_por
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,'historico','rejected','rejected',false,%s,%s::jsonb,%s
                )
                ON CONFLICT (
                    evaluation_contract_id, run_id, campania, modelo, version_modelo, uso
                ) DO UPDATE SET estado='rejected', estado_evaluacion='rejected', activo=false,
                    metadatos=EXCLUDED.metadatos
                """,
                (
                    contrato_id,
                    run_id,
                    snapshot_id,
                    campania,
                    modelo,
                    version,
                    pred_hash,
                    json.dumps({"motivo": "Corrida experimental no comparable"}),
                    "certificar_releases_replay.py",
                ),
            )


__all__ = [
    "_registrar_contrato",
    "_registrar_rechazos",
    "_registrar_release_operativa",
    "_registrar_releases",
]

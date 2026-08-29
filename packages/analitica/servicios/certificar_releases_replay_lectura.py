"""Consultas y lectura de datos para certificar releases de replay."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .certificar_releases_replay_contratos import Certificacion

_SQL_UNIVERSO = """
            SELECT lote_id, fecha_objetivo, fecha_emision,
                   COALESCE(real_kg, 0)::double precision,
                   COALESCE(p50_kg, 0)::double precision,
                   horizonte_semanas, COALESCE(version_fuente, ''),
                   p10_kg, p90_kg, plantas, frutos_por_planta, peso_baya_g,
                   componentes::text
            FROM analytics.prediction
            WHERE run_id = %s AND campania = %s AND modelo = %s
              AND COALESCE(version_modelo, 'sin_version') = %s
              AND lote_id IS NOT NULL AND real_kg IS NOT NULL
              AND fecha_emision < fecha_objetivo
              AND horizonte_semanas = ANY(%s)
              AND (%s::date IS NULL OR fecha_objetivo + 6 <= %s::date)
            ORDER BY fecha_objetivo, lote_id, fecha_emision
            """

_SQL_OPERATIVA_PREDICCIONES = """
        SELECT lote_id, fecha_emision, fecha_objetivo, horizonte_semanas,
               COALESCE(version_fuente, ''), COALESCE(p50_kg, 0)::double precision,
               p10_kg, p90_kg, plantas, frutos_por_planta, peso_baya_g,
               componentes::text
        FROM analytics.prediction
        WHERE run_id=%s AND campania=%s AND modelo=%s
          AND COALESCE(NULLIF(version_modelo, ''), 'sin_version')=%s
          AND lote_id IS NOT NULL
        ORDER BY fecha_objetivo, lote_id, fecha_emision, prediction_id
        """

_SQL_SNAPSHOT = """
        SELECT snapshot_id
        FROM analytics.forecast_run
        WHERE run_id=%s AND estado IN ('succeeded','published')
        """

_SQL_SERIES_RECHAZADAS = """
            SELECT DISTINCT campania, modelo, COALESCE(version_modelo, 'sin_version')
            FROM analytics.prediction
            WHERE run_id=%s
            ORDER BY campania, modelo
            """


def _filas(cursor, consulta: str, parametros: Iterable[Any]) -> list[tuple[Any, ...]]:
    cursor.execute(consulta, tuple(parametros))
    return list(cursor.fetchall())


def _consultar_series(
    cursor,
    cert: Certificacion,
    filas_fn: Callable[..., list[tuple[Any, ...]]] | None = None,
) -> dict[str, list[tuple[Any, ...]]]:
    """Lee las filas crudas de cada serie sin certificar ni escribir."""

    if filas_fn is None:
        filas_fn = _filas
    filas_por_modelo: dict[str, list[tuple[Any, ...]]] = {}
    for serie in cert.series:
        filas_por_modelo[serie.modelo] = filas_fn(
            cursor,
            _SQL_UNIVERSO,
            (
                cert.run_id,
                cert.campania,
                serie.modelo,
                serie.version,
                list(cert.horizontes),
                cert.cerrado_hasta_override,
                cert.cerrado_hasta_override,
            ),
        )
    return filas_por_modelo


def _snapshot(cursor, run_id: int) -> int:
    cursor.execute(_SQL_SNAPSHOT, (run_id,))
    fila = cursor.fetchone()
    if not fila:
        raise ValueError(f"Corrida {run_id} no existe o no terminó correctamente")
    return int(fila[0])


__all__ = [
    "_SQL_OPERATIVA_PREDICCIONES",
    "_SQL_SERIES_RECHAZADAS",
    "_SQL_SNAPSHOT",
    "_SQL_UNIVERSO",
    "_consultar_series",
    "_filas",
    "_snapshot",
]

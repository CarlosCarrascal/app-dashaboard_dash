"""Fachada compatible del servicio de certificación de releases de replay.

La implementación está separada por responsabilidad en módulos hermanos. Esta ruta
conserva los nombres históricos, las firmas y la única orquestación transaccional.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from analitica import settings

from . import certificar_releases_replay_certificacion as _certificacion
from . import certificar_releases_replay_lectura as _lectura
from . import certificar_releases_replay_persistencia as _persistencia
from . import certificar_releases_replay_serializacion as _serializacion
from .certificar_releases_replay_contratos import (
    CERTIFICACIONES,
    RELEASE_OPERATIVA,
    RUNS_RECHAZADOS,
    Certificacion,
    Serie,
)

# Contratos

# Serialización
hashlib = _serializacion.hashlib
json = _serializacion.json
_sha256 = _serializacion._sha256

# Consultas
_SQL_OPERATIVA_PREDICCIONES = _lectura._SQL_OPERATIVA_PREDICCIONES
_SQL_SERIES_RECHAZADAS = _lectura._SQL_SERIES_RECHAZADAS
_SQL_SNAPSHOT = _lectura._SQL_SNAPSHOT
_SQL_UNIVERSO = _lectura._SQL_UNIVERSO
_filas = _lectura._filas
_snapshot = _lectura._snapshot


def _consultar_series(
    cursor, cert: Certificacion
) -> dict[str, list[tuple[Any, ...]]]:
    """Conserva el punto de inyección histórico para pruebas y adaptadores."""

    return _lectura._consultar_series(cursor, cert, filas_fn=_filas)


# Certificación
_certificar_universo = _certificacion._certificar_universo
_registrar_contrato = _persistencia._registrar_contrato
_registrar_rechazos = _persistencia._registrar_rechazos
_registrar_release_operativa = _persistencia._registrar_release_operativa
_registrar_releases = _persistencia._registrar_releases


def _universo(cursor, cert: Certificacion) -> dict[str, Any]:
    """Compone la consulta de series y la certificación del universo común."""

    return _certificar_universo(cert, _consultar_series(cursor, cert))


def ejecutar(aplicar: bool) -> list[dict[str, Any]]:
    dsn = settings.postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL no está configurado")
    # Importación deliberadamente local: importar el servicio no requiere psycopg.
    import psycopg

    reportes: list[dict[str, Any]] = []
    with psycopg.connect(dsn) as conexion:
        with conexion.cursor() as cursor:
            for cert in CERTIFICACIONES:
                universo = _universo(cursor, cert)
                reportes.append(
                    {
                        "campania": cert.campania,
                        "run_id": cert.run_id,
                        "modelos": [serie.modelo for serie in cert.series],
                        "semanas": len(universo["semanas"]),
                        "unidades": universo["n_unidades"],
                        "real_kg": round(universo["volumen_real_kg"], 3),
                        "keyset_sha256": universo["keyset_sha256"],
                    }
                )
                if aplicar:
                    contrato_id = _registrar_contrato(cursor, cert, universo)
                    _registrar_releases(cursor, cert, contrato_id, universo)
            # También en dry-run se ejecuta dentro de la transacción para validar
            # constraints; el rollback final garantiza que no publique nada.
            reportes.append(_registrar_release_operativa(cursor))
            if aplicar:
                _registrar_rechazos(cursor)
        if aplicar:
            conexion.commit()
        else:
            conexion.rollback()
    return reportes


__all__ = [
    "Any",
    "Certificacion",
    "CERTIFICACIONES",
    "Iterable",
    "RELEASE_OPERATIVA",
    "RUNS_RECHAZADOS",
    "Serie",
    "_filas",
    "_registrar_contrato",
    "_registrar_rechazos",
    "_registrar_release_operativa",
    "_registrar_releases",
    "_sha256",
    "_snapshot",
    "_universo",
    "argparse",
    "date",
    "dataclass",
    "ejecutar",
    "hashlib",
    "json",
    "settings",
    "timedelta",
]

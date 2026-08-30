"""Fachada compatible del nowcast de cierre semanal validado.

La implementacion esta separada en modulos hermanos por responsabilidad:
lectura, transformacion, serializacion y persistencia. Este modulo conserva la
ruta historica, sus aliases y las firmas que consumen el CLI y otros clientes.
"""

from __future__ import annotations

import hashlib  # noqa: F401 - alias historico consumido por la fachada CLI
import json  # noqa: F401 - alias historico de la ruta legacy
from datetime import date  # noqa: F401 - alias historico de la ruta legacy
from pathlib import Path
from typing import Any

import numpy as np  # noqa: F401 - alias historico consumido por la fachada CLI
import pandas as pd
import psycopg

from analitica import settings
from analitica.aplicacion.procesos.nowcast import (
    calcular_nowcast_cierre_adaptativo,
)
from analitica.aplicacion.servicios import persistir_nowcast_cierre_adaptativo_lectura as _lectura
from analitica.aplicacion.servicios import (
    persistir_nowcast_cierre_adaptativo_persistencia as _persistencia,
)
from analitica.aplicacion.servicios import (
    persistir_nowcast_cierre_adaptativo_serializacion as _serializacion,
)
from analitica.aplicacion.servicios import (
    persistir_nowcast_cierre_adaptativo_transformacion as _transformacion,
)
from analitica.aplicacion.servicios.nowcast import leer_diario, normalizar_fundo_r09
from analitica.aplicacion.servicios.parametros_nowcast import (
    leer_macro_h1,
    leer_reales_r09_fundo,
)
from analitica.infraestructura.persistencia import RepositorioAnalytics

MODELO = "NowcastCierreSemanal_v1"
VERSION = "adaptive_montue_macro_reconciled_v1"
CAMPAIGN = "C2026"
FUNDOS = ("Arena", "Ayllu", "Kawsay", "Quri")
ROOT = Path(__file__).resolve().parents[3]
ARTEFACTO_DEFAULT = ROOT / ".tmp" / "screening_adaptive_nowcast_fund_guard.json"
REAL_ACCESS_DEFAULT = (
    ROOT / ".cache" / "analitica" / "source-snapshots" / "BD_AQUANQA_26_snapshot_2026-08-25.accdb"
)
R09_ACCESS_DEFAULT = Path(r"C:\Users\CCARRASCAL\Downloads\BD_AQUANQA_26_v2.accdb")
MACRO_RUN_HISTORY = 76
MACRO_RUN_S34 = 73


def _sha256_archivo(path: Path) -> str:
    return _serializacion.sha256_archivo(path)


def _json_hash(value: Any) -> str:
    return _serializacion.json_hash(value)


def _records_hash(table: pd.DataFrame, columns: list[str]) -> str:
    return _serializacion.records_hash(table, columns, hash_json=_json_hash)


def _normalizar_detalle_artifact(path: Path) -> pd.DataFrame:
    return _lectura.normalizar_detalle_artifact(path, campaign=CAMPAIGN)


def _append_latest_closed_week(
    base: pd.DataFrame,
    *,
    real_access: Path,
    r09_access: Path,
) -> pd.DataFrame:
    return _lectura.append_latest_closed_week(
        base,
        real_access=real_access,
        r09_access=r09_access,
        campaign=CAMPAIGN,
        fundos=FUNDOS,
        macro_run_s34=MACRO_RUN_S34,
        leer_macro_h1=leer_macro_h1,
        leer_diario=leer_diario,
        leer_reales_r09_fundo=leer_reales_r09_fundo,
        normalizar_fundo_r09=normalizar_fundo_r09,
    )


def _metric(table: pd.DataFrame, column: str) -> dict[str, float | int]:
    return _transformacion.metric(table, column)


def _bootstrap(table: pd.DataFrame, reference: str) -> dict[str, Any]:
    return _transformacion.bootstrap(table, reference)


def build_candidate(
    *, artifact: Path, real_access: Path, r09_access: Path
) -> tuple[pd.DataFrame, dict[str, Any]]:
    return _transformacion.build_candidate(
        artifact=artifact,
        real_access=real_access,
        r09_access=r09_access,
        normalizar_detalle_artifact=_normalizar_detalle_artifact,
        append_latest_closed_week=_append_latest_closed_week,
        calcular_nowcast_cierre_adaptativo=calcular_nowcast_cierre_adaptativo,
        metric=_metric,
        bootstrap=_bootstrap,
    )


def _publication_rows(output: pd.DataFrame) -> pd.DataFrame:
    return _serializacion.publication_rows(
        output,
        modelo=MODELO,
        version=VERSION,
        campaign=CAMPAIGN,
        fundos=FUNDOS,
    )


def _baseline_release_hashes(connection: psycopg.Connection[Any]) -> dict[str, str]:
    return _persistencia.baseline_release_hashes(connection, modelo=MODELO)


def persist(
    output: pd.DataFrame,
    metrics: dict[str, Any],
    *,
    artifact: Path,
    real_access: Path,
    r09_access: Path,
    apply: bool,
) -> dict[str, Any]:
    serialized = _serializacion.serialize_report(
        output,
        metrics,
        artifact=artifact,
        real_access=real_access,
        r09_access=r09_access,
        apply=apply,
        modelo=MODELO,
        version=VERSION,
        campaign=CAMPAIGN,
        macro_run_history=MACRO_RUN_HISTORY,
        macro_run_s34=MACRO_RUN_S34,
        publication_rows=_publication_rows,
        sha256_archivo=_sha256_archivo,
        records_hash=_records_hash,
        json_hash=_json_hash,
    )
    return _persistencia.persist(
        output,
        metrics,
        artifact=artifact,
        real_access=real_access,
        r09_access=r09_access,
        apply=apply,
        serialized=serialized,
        baseline_release_hashes=_baseline_release_hashes,
        settings_module=settings,
        psycopg_module=psycopg,
        repository_factory=RepositorioAnalytics,
        modelo=MODELO,
        version=VERSION,
        campaign=CAMPAIGN,
        records_hash=_records_hash,
        json_hash=_json_hash,
        fundos=FUNDOS,
    )


__all__ = [
    "MODELO",
    "VERSION",
    "CAMPAIGN",
    "FUNDOS",
    "ROOT",
    "ARTEFACTO_DEFAULT",
    "REAL_ACCESS_DEFAULT",
    "R09_ACCESS_DEFAULT",
    "MACRO_RUN_HISTORY",
    "MACRO_RUN_S34",
    "build_candidate",
    "persist",
]

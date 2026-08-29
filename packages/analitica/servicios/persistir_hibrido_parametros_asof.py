"""Preflight y persistencia candidate-only de ``HibridoParametrosAsOf_v1``.

Este runner nunca reconstruye ni persiste MacroLegacy, Ocurrencia o R09. Esos
baselines se cargan por ``run_id`` y se usan solo para evaluar al challenger.
"""

from __future__ import annotations

import argparse
import time  # noqa: F401 - alias histórico reexportado por la fachada CLI
from collections.abc import Mapping
from hashlib import sha256  # noqa: F401 - alias histórico reexportado por la fachada CLI
from pathlib import Path  # noqa: F401 - alias histórico reexportado por la fachada CLI
from typing import Any

import pandas as pd

from analitica import settings
from analitica.proyeccion.asof import lunes_semana
from analitica.proyeccion.backtest import seleccionar_versiones_oficiales
from analitica.proyeccion.calidad import controles_predicciones
from analitica.proyeccion.candidate_preflight import (
    EXIT_CONTRACT_REJECTED,
    EXIT_EXECUTION_ERROR,
    EXIT_OK,
    CacheCandidate,
    cargar_baselines_por_run,
    cargar_contrato_baselines,
    cargar_o_construir_snapshot_datos,
    clave_cache_candidate,
    clonar_datos_proyeccion,
    escribir_json_reproducible,
    evaluar_preflight,
    json_reproducible,
    obtener_o_construir_cache,
    seleccionar_emisiones_micro_desde_fuente,
    sha256_dataframe,
)
from analitica.proyeccion.fuentes import cargar_datos
from analitica.proyeccion.gobernanza import RepositorioAnalytics
from analitica.proyeccion.hibrido_parametros_asof import (
    NOMBRE_MODELO,
    VERSION_MODELO,
    backtest_hibrido_parametros_asof,
)
from analitica.proyeccion.metricas import metricas_pronostico
from analitica.proyeccion.parametros_excel import cargar_parametros_historicos
from analitica.proyeccion.versiones import fecha_emision_desde_objetivo
from analitica.servicios import persistir_hibrido_parametros_asof_candidate as _candidate
from analitica.servicios import (
    persistir_hibrido_parametros_asof_configuracion as _configuracion,
)
from analitica.servicios import persistir_hibrido_parametros_asof_lectura as _lectura
from analitica.servicios import (
    persistir_hibrido_parametros_asof_orquestacion as _orquestacion,
)
from analitica.servicios import (
    persistir_hibrido_parametros_asof_persistencia as _persistencia,
)
from analitica.servicios import (
    persistir_hibrido_parametros_asof_preflight as _preflight,
)

# Contratos: se reexportan para que la ruta histórica siga siendo una fachada.
BASELINES_REQUERIDOS = _configuracion.BASELINES_REQUERIDOS
BASELINES_PERMITIDOS = _configuracion.BASELINES_PERMITIDOS
MODELO_MACRO = _configuracion.MODELO_MACRO
MODELO_OCURRENCIA = _configuracion.MODELO_OCURRENCIA
MODELO_R09 = _configuracion.MODELO_R09
PROJECT_ROOT = _configuracion.PROJECT_ROOT
HORIZONTES_BASELINE = _configuracion.HORIZONTES_BASELINE
SolicitudEjecucion = _configuracion.SolicitudEjecucion


# Contratos
# ---------------------------------------------------------------------------

def _argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    return _configuracion.argumentos(argv, description=__doc__)


def _parsear_mapa(valores: list[str], *, enteros: bool = False) -> dict[str, Any]:
    return _configuracion.parsear_mapa(valores, enteros=enteros)


def _validar_referencias(referencias: Mapping[str, int]) -> None:
    _configuracion.validar_referencias(referencias)


# Serialización
# ---------------------------------------------------------------------------

def _serializar_json(valor: Any) -> str:
    """Punto único para firmas, detalles de calidad y claves de fuente."""

    return _lectura.serializar_json(valor, json_reproducible=json_reproducible)


def _hash_json(valor: Any) -> str:
    return _lectura.hash_json(valor, serializar=_serializar_json)


def _firma_directorio(raiz: str | None) -> str | None:
    return _lectura.firma_directorio(raiz, hash_json_fn=_hash_json)


# Consultas
# ---------------------------------------------------------------------------

def _consultar_contrato_baselines(
    dsn: str,
    referencias: Mapping[str, int],
    campania: str,
):
    """Resuelve el contrato aprobado sin mezclarlo con candidate-only."""

    return _lectura.consultar_contrato_baselines(
        dsn,
        referencias,
        campania,
        loader=cargar_contrato_baselines,
    )


def _consultar_snapshot_fuente(fuente_clave: str):
    fuente_cache = PROJECT_ROOT / ".cache" / "analitica" / "source-snapshots"
    return _lectura.consultar_snapshot_fuente(
        fuente_clave,
        cache_root=fuente_cache,
        snapshot_loader=cargar_o_construir_snapshot_datos,
        data_loader=cargar_datos,
    )


def _consultar_baselines(
    dsn: str,
    referencias: Mapping[str, int],
    campania: str,
    *,
    cerrado_hasta,
    fechas_emision=None,
) -> dict[str, pd.DataFrame]:
    return _lectura.consultar_baselines(
        dsn,
        referencias,
        campania,
        horizontes=HORIZONTES_BASELINE,
        cerrado_hasta=cerrado_hasta,
        fechas_emision=fechas_emision,
        loader=cargar_baselines_por_run,
    )


def _emisiones_desde_forecast(datos, campania: str) -> pd.DataFrame:
    """Extrae cortes de la fuente sin construir predicciones R09."""

    return _lectura.emisiones_desde_forecast(
        datos,
        campania,
        seleccionar_versiones=seleccionar_versiones_oficiales,
        lunes_semana=lunes_semana,
        fecha_emision_desde_objetivo=fecha_emision_desde_objetivo,
    )


# Certificación
# ---------------------------------------------------------------------------

def _cargar_priors_excel(
    datos_candidato,
    emisiones: pd.DataFrame,
    excel_root: str | None,
) -> dict[str, Any]:
    """Adjunta priors únicamente al clon candidate-only."""

    return _candidate.cargar_priors_excel(
        datos_candidato,
        emisiones,
        excel_root,
        loader=cargar_parametros_historicos,
    )


def _completar_candidato(tabla: pd.DataFrame) -> pd.DataFrame:
    return _candidate.completar_candidato(
        tabla,
        nombre_modelo=NOMBRE_MODELO,
        version_modelo=VERSION_MODELO,
    )


def construir_candidato(
    datos,
    emisiones: pd.DataFrame,
    *,
    campania: str,
    horizonte: int,
    max_cortes: int | None,
    excel_root: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Calcula exclusivamente HPA sobre un clon del contrato fuente."""

    return _candidate.construir_candidato(
        datos,
        emisiones,
        campania=campania,
        horizonte=horizonte,
        max_cortes=max_cortes,
        excel_root=excel_root,
        clonar_datos=clonar_datos_proyeccion,
        cargar_priors=_cargar_priors_excel,
        backtest=backtest_hibrido_parametros_asof,
        nombre_modelo=NOMBRE_MODELO,
        version_modelo=VERSION_MODELO,
    )


def _candidate_cache(
    datos,
    emisiones: pd.DataFrame,
    *,
    campania: str,
    horizonte: int,
    max_cortes: int | None,
    excel_root: str | None,
    cache: CacheCandidate,
    fase: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    return _candidate.candidate_cache(
        datos,
        emisiones,
        campania=campania,
        horizonte=horizonte,
        max_cortes=max_cortes,
        excel_root=excel_root,
        cache=cache,
        fase=fase,
        nombre_modelo=NOMBRE_MODELO,
        version_modelo=VERSION_MODELO,
        firma_directorio=_firma_directorio,
        sha256_dataframe=sha256_dataframe,
        clave_cache=clave_cache_candidate,
        obtener_cache=obtener_o_construir_cache,
        construir=construir_candidato,
    )


def _calidad_preflight(reporte: Mapping[str, Any]) -> pd.DataFrame:
    return _preflight.calidad_preflight(reporte, serializar=_serializar_json)


def _persistir_candidato(
    dsn: str,
    datos,
    full: pd.DataFrame,
    calidad_pred: pd.DataFrame,
    snapshots: pd.DataFrame,
    reporte_full: Mapping[str, Any],
    contrato_baselines,
    solicitud: SolicitudEjecucion,
) -> tuple[int, int, pd.DataFrame]:
    """Persiste únicamente el challenger después de superar ambos preflight."""

    return _persistencia.persistir_candidato(
        dsn,
        datos,
        full,
        calidad_pred,
        snapshots,
        reporte_full,
        contrato_baselines,
        solicitud,
        metricas=metricas_pronostico,
        repositorio=RepositorioAnalytics,
        calidad_preflight=_calidad_preflight,
        nombre_modelo=NOMBRE_MODELO,
        version_modelo=VERSION_MODELO,
    )


# Orquestación
# ---------------------------------------------------------------------------

def ejecutar(
    *,
    campania: str,
    referencias: Mapping[str, int],
    hashes_esperados: Mapping[str, str] | None = None,
    expected_keyset_hash: str | None = None,
    horizonte: int = 10,
    max_cortes: int = 0,
    excel_root: str | None = None,
    preflight_only: bool = False,
    dry_run: bool = False,
    cache_dir: str | None = None,
) -> dict[str, Any]:
    return _orquestacion.ejecutar(
        campania=campania,
        referencias=referencias,
        hashes_esperados=hashes_esperados,
        expected_keyset_hash=expected_keyset_hash,
        horizonte=horizonte,
        max_cortes=max_cortes,
        excel_root=excel_root,
        preflight_only=preflight_only,
        dry_run=dry_run,
        cache_dir=cache_dir,
        validar_referencias=_validar_referencias,
        postgres_dsn=settings.postgres_dsn,
        consultar_contrato=_consultar_contrato_baselines,
        hash_json=_hash_json,
        consultar_snapshot=_consultar_snapshot_fuente,
        emisiones_desde_forecast=_emisiones_desde_forecast,
        seleccionar_micro=seleccionar_emisiones_micro_desde_fuente,
        consultar_baselines=_consultar_baselines,
        cache_factory=CacheCandidate,
        candidate_cache=_candidate_cache,
        evaluar_preflight=evaluar_preflight,
        controles_predicciones=controles_predicciones,
        persistir_candidato=_persistir_candidato,
        exit_ok=EXIT_OK,
        exit_contract_rejected=EXIT_CONTRACT_REJECTED,
        nombre_modelo=NOMBRE_MODELO,
        version_modelo=VERSION_MODELO,
    )


__all__ = [
    "BASELINES_PERMITIDOS",
    "BASELINES_REQUERIDOS",
    "EXIT_CONTRACT_REJECTED",
    "EXIT_EXECUTION_ERROR",
    "EXIT_OK",
    "HORIZONTES_BASELINE",
    "MODELO_MACRO",
    "MODELO_OCURRENCIA",
    "MODELO_R09",
    "NOMBRE_MODELO",
    "PROJECT_ROOT",
    "SolicitudEjecucion",
    "VERSION_MODELO",
    "CacheCandidate",
    "backtest_hibrido_parametros_asof",
    "cargar_baselines_por_run",
    "cargar_contrato_baselines",
    "cargar_datos",
    "cargar_parametros_historicos",
    "construir_candidato",
    "ejecutar",
    "escribir_json_reproducible",
    "metricas_pronostico",
    "seleccionar_emisiones_micro_desde_fuente",
]

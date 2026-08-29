"""Fachada compatible para los servicios históricos de nowcast.

La implementación está organizada por responsabilidad en módulos hermanos.
Este módulo conserva los nombres públicos y los aliases privados que forman
parte del contrato de los adaptadores CLI y de consumidores existentes.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analitica.servicios import (
    nowcast_partes_adaptativo as _adaptativo,
)
from analitica.servicios import (
    nowcast_partes_base as _base,
)
from analitica.servicios import (
    nowcast_partes_guardia as _guardia,
)
from analitica.servicios import (
    nowcast_partes_intraweek as _intraweek,
)
from analitica.servicios import (
    parametros_nowcast as _parametros,
)

ACCESS_DEFAULT = _base.ACCESS_DEFAULT
EPS = _base.EPS
FUNDOS = _base.FUNDOS
R09_ACCESS_DEFAULT = _base.R09_ACCESS_DEFAULT
RUNS_CERTIFICADOS = _base.RUNS_CERTIFICADOS
hashlib = _intraweek.hashlib
json = _guardia.json
Iterable = _adaptativo.Iterable
asdict = _guardia.asdict
dataclass = _intraweek.dataclass
np = _adaptativo.np
psycopg = _intraweek.psycopg
nnls = _adaptativo.nnls
settings = _intraweek.settings
_mapear_fundo_h01 = _base._mapear_fundo_h01
leer_diario = _base.leer_diario

Configuracion = _intraweek.Configuracion
_calibrar_residuo_online = _intraweek._calibrar_residuo_online
_cargar_contrato = _intraweek._cargar_contrato
_comparacion_pareada = _intraweek._comparacion_pareada
_keyset = _intraweek._keyset
_leer_macro_s34_run73 = _intraweek._leer_macro_s34_run73
_metricas_intraweek = _intraweek._metricas_intraweek
_predecir = _intraweek._predecir
ejecutar_intraweek = _intraweek.ejecutar_intraweek

BASE_CONGELADA = _adaptativo.BASE_CONGELADA
ConfiguracionAdaptativa = _adaptativo.ConfiguracionAdaptativa
_agregar_empresa = _adaptativo._agregar_empresa
_configuraciones = _adaptativo._configuraciones
_construir_contrato = _adaptativo._construir_contrato
_construir_contrato_adaptativo = _adaptativo._construir_contrato_adaptativo
_diagnostico_shares = _adaptativo._diagnostico_shares
_evaluar_bloque = _adaptativo._evaluar_bloque
_hash_keyset = _adaptativo._hash_keyset
_metricas = _adaptativo._metricas
_metricas_adaptativa = _adaptativo._metricas_adaptativa
_normalizar_fundo_r09 = _adaptativo._normalizar_fundo_r09
_seleccionar_configuracion = _adaptativo._seleccionar_configuracion
_sha256_archivo = _adaptativo._sha256_archivo
agregar_empresa = _adaptativo.agregar_empresa
diagnostico_shares = _adaptativo.diagnostico_shares
ejecutar = _adaptativo.ejecutar
metricas = _adaptativo.metricas
metricas_adaptativa = _adaptativo.metricas_adaptativa
normalizar_fundo_r09 = _adaptativo.normalizar_fundo_r09
predecir_online = _adaptativo.predecir_online
sha256_archivo = _adaptativo.sha256_archivo

ConfiguracionFundGuard = _guardia.ConfiguracionFundGuard
ConfiguracionReconciliacionFundos = _guardia.ConfiguracionReconciliacionFundos
_aplicar_guardia_online = _guardia._aplicar_guardia_online
_configuraciones_guardia = _guardia._configuraciones_guardia
_configuraciones_reconciliacion = _guardia._configuraciones_reconciliacion
_deterioros_por_fundo = _guardia._deterioros_por_fundo
_evaluar = _guardia._evaluar
_evidencia_fundo = _guardia._evidencia_fundo
_hash_configuracion = _guardia._hash_configuracion
_max_deterioro = _guardia._max_deterioro
_reconciliar_total_empresa_online = _guardia._reconciliar_total_empresa_online
_seleccionar_guardia = _guardia._seleccionar_guardia
_seleccionar_reconciliacion = _guardia._seleccionar_reconciliacion
_wape = _guardia._wape
ejecutar_fund_guard = _guardia.ejecutar_fund_guard

columna_campania = _parametros.columna_campania
leer_macro_h1 = _parametros.leer_macro_h1
leer_reales_r09_fundo = _parametros.leer_reales_r09_fundo

_ajustar_coeficientes_impl = _adaptativo._ajustar_coeficientes
_bootstrap_pareado_impl = _adaptativo._bootstrap_pareado
_estimar_pace_online_impl = _adaptativo._estimar_pace_online
_predecir_online_impl = _adaptativo._predecir_online


# Forwards privados conservados porque algunos adaptadores históricos
# inspeccionan estos nombres directamente en la fachada.
def _estimar_pace_online(tabla: pd.DataFrame, cfg: ConfiguracionAdaptativa) -> pd.DataFrame:
    return _estimar_pace_online_impl(tabla, cfg)


def _ajustar_coeficientes(
    historia: pd.DataFrame,
    cfg: ConfiguracionAdaptativa,
) -> tuple[float, float, int]:
    return _ajustar_coeficientes_impl(historia, cfg)


def _predecir_online(tabla: pd.DataFrame, cfg: ConfiguracionAdaptativa) -> pd.DataFrame:
    return _predecir_online_impl(tabla, cfg)


def _bootstrap_pareado(
    tabla: pd.DataFrame,
    referencia: str,
    *,
    repeticiones: int = 5_000,
) -> dict[str, object] | None:
    return _bootstrap_pareado_impl(tabla, referencia, repeticiones=repeticiones)


def bootstrap_pareado(tabla: pd.DataFrame, referencia: str, *, repeticiones: int = 5_000):
    return _bootstrap_pareado_impl(tabla, referencia, repeticiones=repeticiones)


def metricas_intraweek(tabla: pd.DataFrame, columna: str) -> dict[str, float | int]:
    return _metricas_intraweek(tabla, columna)


def comparacion_pareada(tabla: pd.DataFrame, referencia: str, *, repeticiones: int = 5_000):
    return _comparacion_pareada(tabla, referencia, repeticiones=repeticiones)


def cargar_contrato(access: Path, r09_access: Path, campania: str):
    return _cargar_contrato(access, r09_access, campania)


def predecir(tabla: pd.DataFrame, semanal_fundo: pd.DataFrame, cfg: Configuracion):
    return _predecir(tabla, semanal_fundo, cfg)


def calibrar_residuo_online(tabla: pd.DataFrame, *, lookback: int, shrink: float):
    return _calibrar_residuo_online(tabla, lookback=lookback, shrink=shrink)


def construir_contrato(*, campania: str, run_id: int, access: Path, r09_access: Path):
    return _construir_contrato_adaptativo(
        campania=campania,
        run_id=run_id,
        access=access,
        r09_access=r09_access,
    )


__all__ = [
    "ACCESS_DEFAULT",
    "BASE_CONGELADA",
    "Configuracion",
    "ConfiguracionAdaptativa",
    "ConfiguracionFundGuard",
    "ConfiguracionReconciliacionFundos",
    "EPS",
    "FUNDOS",
    "R09_ACCESS_DEFAULT",
    "RUNS_CERTIFICADOS",
    "agregar_empresa",
    "bootstrap_pareado",
    "calibrar_residuo_online",
    "cargar_contrato",
    "comparacion_pareada",
    "construir_contrato",
    "diagnostico_shares",
    "ejecutar_fund_guard",
    "leer_diario",
    "metricas",
    "metricas_adaptativa",
    "metricas_intraweek",
    "normalizar_fundo_r09",
    "predecir",
    "predecir_online",
    "sha256_archivo",
]

"""Fachada CLI compatible para preflight y persistencia candidate-only.

La lógica reusable vive en :mod:`analitica.servicios.persistir_hibrido_parametros_asof`.
Este módulo conserva argumentos, aliases históricos, serialización y la frontera CLI.
"""

from __future__ import annotations

import json
import sys

from analitica.servicios import persistir_hibrido_parametros_asof as _servicio

# Aliases históricos: la implementación única vive en el servicio.
argparse = _servicio.argparse
Any = _servicio.Any
BASELINES_PERMITIDOS = _servicio.BASELINES_PERMITIDOS
BASELINES_REQUERIDOS = _servicio.BASELINES_REQUERIDOS
CacheCandidate = _servicio.CacheCandidate
EXIT_CONTRACT_REJECTED = _servicio.EXIT_CONTRACT_REJECTED
EXIT_EXECUTION_ERROR = _servicio.EXIT_EXECUTION_ERROR
EXIT_OK = _servicio.EXIT_OK
Mapping = _servicio.Mapping
MODELO_MACRO = _servicio.MODELO_MACRO
MODELO_OCURRENCIA = _servicio.MODELO_OCURRENCIA
MODELO_R09 = _servicio.MODELO_R09
NOMBRE_MODELO = _servicio.NOMBRE_MODELO
PROJECT_ROOT = _servicio.PROJECT_ROOT
Path = _servicio.Path
RepositorioAnalytics = _servicio.RepositorioAnalytics
VERSION_MODELO = _servicio.VERSION_MODELO
backtest_hibrido_parametros_asof = _servicio.backtest_hibrido_parametros_asof
cargar_baselines_por_run = _servicio.cargar_baselines_por_run
cargar_contrato_baselines = _servicio.cargar_contrato_baselines
cargar_datos = _servicio.cargar_datos
cargar_o_construir_snapshot_datos = _servicio.cargar_o_construir_snapshot_datos
cargar_parametros_historicos = _servicio.cargar_parametros_historicos
clave_cache_candidate = _servicio.clave_cache_candidate
clonar_datos_proyeccion = _servicio.clonar_datos_proyeccion
controles_predicciones = _servicio.controles_predicciones
escribir_json_reproducible = _servicio.escribir_json_reproducible
evaluar_preflight = _servicio.evaluar_preflight
fecha_emision_desde_objetivo = _servicio.fecha_emision_desde_objetivo
json_reproducible = _servicio.json_reproducible
lunes_semana = _servicio.lunes_semana
metricas_pronostico = _servicio.metricas_pronostico
obtener_o_construir_cache = _servicio.obtener_o_construir_cache
pd = _servicio.pd
seleccionar_emisiones_micro_desde_fuente = _servicio.seleccionar_emisiones_micro_desde_fuente
seleccionar_versiones_oficiales = _servicio.seleccionar_versiones_oficiales
sha256 = _servicio.sha256
sha256_dataframe = _servicio.sha256_dataframe
settings = _servicio.settings
time = _servicio.time

_argumentos = _servicio._argumentos
_parsear_mapa = _servicio._parsear_mapa
_validar_referencias = _servicio._validar_referencias
_firma_directorio = _servicio._firma_directorio
_emisiones_desde_forecast = _servicio._emisiones_desde_forecast
_completar_candidato = _servicio._completar_candidato
construir_candidato = _servicio.construir_candidato
_candidate_cache = _servicio._candidate_cache
_calidad_preflight = _servicio._calidad_preflight
ejecutar = _servicio.ejecutar


def _cargar_priors_excel(
    datos_candidato,
    emisiones: pd.DataFrame,
    excel_root: str | None,
) -> dict[str, Any]:
    """Conserva el punto de monkeypatch histórico del script para el loader Excel."""

    loader_original = _servicio.cargar_parametros_historicos
    _servicio.cargar_parametros_historicos = cargar_parametros_historicos
    try:
        return _servicio._cargar_priors_excel(datos_candidato, emisiones, excel_root)
    finally:
        _servicio.cargar_parametros_historicos = loader_original


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    try:
        referencias = _parsear_mapa(args.baseline_run_id, enteros=True)
        hashes = _parsear_mapa(args.expected_baseline_hash)
        resultado = ejecutar(
            campania=args.campania,
            referencias=referencias,
            hashes_esperados=hashes,
            expected_keyset_hash=args.expected_keyset_hash,
            horizonte=args.horizonte_semanas,
            max_cortes=args.max_cortes,
            excel_root=args.excel_root,
            preflight_only=args.preflight,
            dry_run=args.dry_run,
            cache_dir=None if args.no_cache else args.cache_dir,
        )
    except Exception as exc:  # frontera CLI: siempre devuelve JSON y código estable
        resultado = {
            "schema_version": "hpa-runner-v1",
            "estado": "execution_error",
            "exit_code": EXIT_EXECUTION_ERROR,
            "error": f"{type(exc).__name__}: {exc}",
        }
    if args.output_json:
        escribir_json_reproducible(resultado, args.output_json)
    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str, allow_nan=False))
    return int(resultado.get("exit_code", EXIT_EXECUTION_ERROR))


if __name__ == "__main__":
    sys.exit(main())

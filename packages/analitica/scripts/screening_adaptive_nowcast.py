"""Adaptador CLI y fachada histórica del screening adaptativo nowcast.

La implementación de negocio vive en :mod:`analitica.servicios.nowcast`.
Este módulo conserva el comando, los nombres públicos y los aliases privados
que usan consumidores y artefactos reproducibles antiguos.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.proyeccion.candidate_preflight import escribir_json_reproducible
from analitica.servicios import nowcast as _nowcast

ACCESS_DEFAULT = _nowcast.ACCESS_DEFAULT
EPS = _nowcast.EPS
FUNDOS = _nowcast.FUNDOS
R09_ACCESS_DEFAULT = _nowcast.R09_ACCESS_DEFAULT
RUNS_CERTIFICADOS = _nowcast.RUNS_CERTIFICADOS
ConfiguracionAdaptativa = _nowcast.ConfiguracionAdaptativa
_agregar_empresa = _nowcast._agregar_empresa
_ajustar_coeficientes = _nowcast._ajustar_coeficientes
_bootstrap_pareado = _nowcast._bootstrap_pareado
_configuraciones = _nowcast._configuraciones
_construir_contrato = _nowcast._construir_contrato
_diagnostico_shares = _nowcast._diagnostico_shares
_evaluar_bloque = _nowcast._evaluar_bloque
_estimar_pace_online = _nowcast._estimar_pace_online
_hash_keyset = _nowcast._hash_keyset
_metricas = _nowcast._metricas
_normalizar_fundo_r09 = _nowcast._normalizar_fundo_r09
_predecir_online = _nowcast._predecir_online
_seleccionar_configuracion = _nowcast._seleccionar_configuracion
_sha256_archivo = _nowcast._sha256_archivo
agregar_empresa = _nowcast.agregar_empresa
bootstrap_pareado = _nowcast.bootstrap_pareado
construir_contrato = _nowcast.construir_contrato
diagnostico_shares = _nowcast.diagnostico_shares
ejecutar = _nowcast.ejecutar
metricas = _nowcast.metricas
normalizar_fundo_r09 = _nowcast.normalizar_fundo_r09
predecir_online = _nowcast.predecir_online
sha256_archivo = _nowcast.sha256_archivo

# Todas las funciones de negocio son aliases directos al servicio único.
__all__ = [
    "ACCESS_DEFAULT",
    "ConfiguracionAdaptativa",
    "EPS",
    "FUNDOS",
    "R09_ACCESS_DEFAULT",
    "RUNS_CERTIFICADOS",
    "agregar_empresa",
    "bootstrap_pareado",
    "construir_contrato",
    "diagnostico_shares",
    "ejecutar",
    "metricas",
    "normalizar_fundo_r09",
    "predecir_online",
    "sha256_archivo",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--access", type=Path, default=ACCESS_DEFAULT)
    parser.add_argument("--r09-access", type=Path, default=R09_ACCESS_DEFAULT)
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar(access=args.access, r09_access=args.r09_access)
    if args.salida:
        escribir_json_reproducible(resultado, args.salida)
    resumen = {
        "configuracion_congelada": resultado["configuracion_congelada"],
        "evaluaciones": resultado["evaluaciones"],
        "persistencia_postgresql": False,
    }
    print(json.dumps(resumen, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fachada CLI compatible para la validación externa del nowcast congelado."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.aplicacion.servicios import validate_intraweek_nowcast_external as _servicio

ACCESS_DEFAULT = _servicio.ACCESS_DEFAULT
CALIBRACION_CONGELADA = _servicio.CALIBRACION_CONGELADA
CONFIGURACION_CONGELADA = _servicio.CONFIGURACION_CONGELADA
Configuracion = _servicio.Configuracion
R09_ACCESS_DEFAULT = _servicio.R09_ACCESS_DEFAULT
RUNS_CERTIFICADOS = _servicio.RUNS_CERTIFICADOS
calibrar_residuo_online = _servicio.calibrar_residuo_online
comparacion_pareada = _servicio.comparacion_pareada
ejecutar = _servicio.ejecutar
escribir_json_reproducible = _servicio.escribir_json_reproducible
evaluar_campania = _servicio.evaluar_campania
leer_diario = _servicio.leer_diario
leer_macro_h1 = _servicio.leer_macro_h1
leer_reales_r09_fundo = _servicio.leer_reales_r09_fundo
metricas = _servicio.metricas
pd = _servicio.pd
predecir = _servicio.predecir

# Aliases privados históricos: la implementación única vive en el servicio.
_construir_contrato = _servicio._construir_contrato
_predecir_fundos = _servicio._predecir_fundos
_resumen_fundos = _servicio._resumen_fundos


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--access", type=Path, default=ACCESS_DEFAULT)
    parser.add_argument("--r09-access", type=Path, default=R09_ACCESS_DEFAULT)
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar(access=args.access, r09_access=args.r09_access)
    if args.salida:
        escribir_json_reproducible(resultado, args.salida)
    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Evalua un router candidate-only: ocurrencia h1 y Macro h2-h5."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.aplicacion.procesos.candidatos import escribir_json_reproducible
from analitica.aplicacion.servicios import router_horizonte as _servicio

# Reexportaciones históricas: la fachada conserva nombres y objetos; el cálculo
# y la lectura/agregación viven en el servicio.
CIERRES = _servicio.CIERRES
RUNS_H1 = _servicio.RUNS_H1
RUNS_MULTI = _servicio.RUNS_MULTI
np = _servicio.np
pd = _servicio.pd
agregar = _servicio.agregar
ejecutar = _servicio.ejecutar
evaluar_campania = _servicio.evaluar_campania
leer = _servicio.leer
_agregar = _servicio._agregar
_leer = _servicio._leer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar()
    if args.salida:
        escribir_json_reproducible(resultado, args.salida)
    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

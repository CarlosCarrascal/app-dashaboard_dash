"""Fachada CLI compatible para el screening residual as-of.

La lógica de negocio vive en :mod:`analitica.aplicacion.servicios.residual_asof`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.aplicacion.servicios import residual_asof as _servicio

# Reexportaciones para conservar aliases públicos y privados históricos.
asdict = _servicio.asdict
np = _servicio.np
pd = _servicio.pd
psycopg = _servicio.psycopg
escribir_json_reproducible = _servicio.escribir_json_reproducible
ConfiguracionResidualAsOf = _servicio.ConfiguracionResidualAsOf
aplicar_calibracion_residual_asof = _servicio.aplicar_calibracion_residual_asof
postgres_dsn = _servicio.postgres_dsn
RUNS = _servicio.RUNS
CIERRES = _servicio.CIERRES
configuraciones = _servicio.configuraciones
leer_panel = _servicio.leer_panel
_semanal = _servicio._semanal
comparar_comun = _servicio.comparar_comun
score = _servicio.score
ejecutar = _servicio.ejecutar


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar()
    if args.salida:
        escribir_json_reproducible(resultado, args.salida)
    print(json.dumps(resultado["mejor"], ensure_ascii=False, indent=2, default=str))
    print(json.dumps(resultado["decision"], ensure_ascii=False, indent=2, default=str))
    print(
        json.dumps(
            resultado["protocolo_c2026_temporal"],
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

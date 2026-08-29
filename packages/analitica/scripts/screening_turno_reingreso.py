"""Fachada CLI compatible del screening rápido del calendario de reingreso.

La lógica reutilizable vive en :mod:`analitica.servicios.screening_turno_reingreso`.
Este módulo conserva los nombres y objetos históricos, además de los argumentos
``--micro`` y ``--salida``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.servicios import screening_turno_reingreso as _servicio

# Reexportaciones históricas: los consumidores siguen encontrando las mismas
# funciones, constantes, imports y dataclass en el módulo CLI.
asdict = _servicio.asdict
dataclass = _servicio.dataclass
np = _servicio.np
pd = _servicio.pd
psycopg = _servicio.psycopg
escribir_json_reproducible = _servicio.escribir_json_reproducible
postgres_dsn = _servicio.postgres_dsn

RUNS = _servicio.RUNS
CIERRES = _servicio.CIERRES
Config = _servicio.Config

leer_datos = _servicio.leer_datos
_historia_por_lote = _servicio._historia_por_lote
_share_calendario = _servicio._share_calendario
precomputar_shares = _servicio.precomputar_shares
aplicar_config = _servicio.aplicar_config
_serie_empresa = _servicio._serie_empresa
metricas = _servicio.metricas
comparar = _servicio.comparar
_cortes_micro = _servicio._cortes_micro
ejecutar = _servicio.ejecutar
_COSECHA_GLOBAL = _servicio._COSECHA_GLOBAL


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--salida", type=Path)
    parser.add_argument("--micro", action="store_true")
    args = parser.parse_args()
    resultado = ejecutar(micro=args.micro)
    if args.salida:
        escribir_json_reproducible(resultado, args.salida)
    print(json.dumps(resultado["mejor"], ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

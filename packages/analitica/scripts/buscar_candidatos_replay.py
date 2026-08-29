"""Fachada CLI compatible para buscar candidatos de replay.

La lógica reusable vive en :mod:`analitica.servicios.buscar_candidatos_replay`.
Este módulo conserva aliases públicos/privados, firmas, argumentos, CLI,
serialización y rutas históricas.
"""

from __future__ import annotations

import json

from analitica.servicios import buscar_candidatos_replay as _servicio

# Aliases históricos: la implementación única vive en el servicio.
argparse = _servicio.argparse
Path = _servicio.Path
pd = _servicio.pd
psycopg = _servicio.psycopg
postgres_dsn = _servicio.postgres_dsn
preparar_panel = _servicio.preparar_panel
successive_halving = _servicio.successive_halving
escribir_json_reproducible = _servicio.escribir_json_reproducible
_argumentos = _servicio._argumentos
_leer = _servicio._leer
ejecutar = _servicio.ejecutar


def main() -> int:
    args = _argumentos()
    resultado = ejecutar()
    if args.salida:
        escribir_json_reproducible(resultado, args.salida)
    print(json.dumps(resultado["mejor"], ensure_ascii=False, indent=2, default=str))
    print(json.dumps(resultado["decision"], ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

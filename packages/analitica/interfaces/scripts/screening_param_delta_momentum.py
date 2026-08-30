"""Fachada CLI compatible para el screening de momentum y deltas de parámetros.

La lógica de negocio vive en :mod:`analitica.aplicacion.servicios.param_delta_momentum`.
Este módulo conserva aliases históricos, firmas, argumentos, serialización y rutas.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.aplicacion.procesos.candidatos import escribir_json_reproducible
from analitica.aplicacion.servicios import param_delta_momentum as _servicio

# Compatibilidad histórica: todos los símbolos de negocio apuntan al servicio único.
MAPEO_FUNDO = _servicio.MAPEO_FUNDO
_fundo = _servicio._fundo
_leer_macro_h1 = _servicio._leer_macro_h1
_columna_campania = _servicio._columna_campania
_leer_reales_r09_fundo = _servicio._leer_reales_r09_fundo
_metricas = _servicio._metricas
_cobertura = _servicio._cobertura
_hash_keyset = _servicio._hash_keyset
ejecutar = _servicio.ejecutar

normalizar_fundo = _servicio.normalizar_fundo
leer_macro_h1 = _servicio.leer_macro_h1
columna_campania = _servicio.columna_campania
leer_reales_r09_fundo = _servicio.leer_reales_r09_fundo

# Nombres importados que formaban parte del módulo histórico.
hashlib = _servicio.hashlib
np = _servicio.np
pd = _servicio.pd
psycopg = _servicio.psycopg
CandidateParamDelta = _servicio.CandidateParamDelta
ACCESS_DEFAULT = _servicio.ACCESS_DEFAULT
ROOT_DEFAULT = _servicio.ROOT_DEFAULT
TRANSITIONS_DEFAULT = _servicio.TRANSITIONS_DEFAULT
postgres_dsn = _servicio.postgres_dsn
proyectar_emision_detallada = _servicio.proyectar_emision_detallada


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--transitions", type=Path, default=TRANSITIONS_DEFAULT)
    parser.add_argument("--access", type=Path, default=ACCESS_DEFAULT)
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar(root=args.root, transitions=args.transitions, access=args.access)
    if args.salida:
        escribir_json_reproducible(resultado, args.salida)
    print(
        json.dumps(
            {
                "empresa": resultado["resumen_empresa_semana"],
                "fundo_semana": resultado["resumen_fundo_semana"],
                "por_fundo": resultado["por_fundo"],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

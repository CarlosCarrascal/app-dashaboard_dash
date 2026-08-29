"""Fachada CLI compatible para el screening de desplazamiento temporal online.

La lógica de negocio vive en :mod:`analitica.servicios.temporal_shift`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.servicios import temporal_shift as _servicio

# Reexportaciones para conservar todos los nombres históricos, incluidos los
# privados usados por notebooks y pruebas de compatibilidad.
hashlib = _servicio.hashlib
dataclass = _servicio.dataclass
np = _servicio.np
pd = _servicio.pd
escribir_json_reproducible = _servicio.escribir_json_reproducible
ACCESS_DEFAULT = _servicio.ACCESS_DEFAULT
leer_reales_r09_fundo = _servicio.leer_reales_r09_fundo
agregar = _servicio.agregar
leer = _servicio.leer

Configuracion = _servicio.Configuracion
_metricas = _servicio._metricas
_keyset_sha256 = _servicio._keyset_sha256
_cargar_contrato = _servicio._cargar_contrato
_ponderaciones = _servicio._ponderaciones
_elegir = _servicio._elegir
_predecir_online = _servicio._predecir_online
ejecutar = _servicio.ejecutar


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--access", type=Path, default=ACCESS_DEFAULT)
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar(access=args.access)
    if args.salida:
        escribir_json_reproducible(resultado, args.salida)
    print(
        json.dumps(
            {
                "ganador": resultado["ganador_micro_replay"],
                "contrato": resultado["evaluation_contract"],
                "metricas": resultado["metricas"],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

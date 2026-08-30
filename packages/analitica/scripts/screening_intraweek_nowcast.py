"""Adaptador CLI compatible para el nowcast de cierre intra-semanal.

La implementación vive en :mod:`analitica.servicios.nowcast`. Este módulo
conserva los nombres históricos para consumidores que todavía importan el
script directamente y solo contiene la composición de la interfaz CLI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.proyeccion.candidatos import escribir_json_reproducible
from analitica.servicios import nowcast as _nowcast
from analitica.servicios.parametros_nowcast import (
    columna_campania,  # noqa: F401
    leer_macro_h1,  # noqa: F401
    leer_reales_r09_fundo,  # noqa: F401
)

ACCESS_DEFAULT = _nowcast.ACCESS_DEFAULT
R09_ACCESS_DEFAULT = _nowcast.R09_ACCESS_DEFAULT
Configuracion = _nowcast.Configuracion

# Fachada compatible: se conservan tanto los nombres privados históricos como
# sus equivalentes públicos, todos apuntando a la implementación única.
_mapear_fundo_h01 = _nowcast._mapear_fundo_h01
_leer_diario = _nowcast.leer_diario
leer_diario = _nowcast.leer_diario
_metricas = _nowcast.metricas_intraweek
metricas = _nowcast.metricas_intraweek
_comparacion_pareada = _nowcast._comparacion_pareada
comparacion_pareada = _nowcast.comparacion_pareada
_keyset = _nowcast._keyset
_leer_macro_s34_run73 = _nowcast._leer_macro_s34_run73
_cargar_contrato = _nowcast._cargar_contrato
cargar_contrato = _nowcast.cargar_contrato
_predecir = _nowcast._predecir
predecir = _nowcast.predecir
_calibrar_residuo_online = _nowcast._calibrar_residuo_online
calibrar_residuo_online = _nowcast.calibrar_residuo_online
ejecutar = _nowcast.ejecutar_intraweek


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--access", type=Path, default=ACCESS_DEFAULT)
    parser.add_argument("--r09-access", type=Path, default=R09_ACCESS_DEFAULT)
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar(access=args.access, r09_access=args.r09_access)
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

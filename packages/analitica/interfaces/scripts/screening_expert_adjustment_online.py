"""Adaptador CLI compatible del ajuste experto regularizado online.

La implementación de negocio vive en :mod:`analitica.aplicacion.servicios.expertos`.
Este módulo conserva el CLI y los nombres históricos importados por terceros.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.aplicacion.procesos.candidatos import escribir_json_reproducible
from analitica.aplicacion.servicios import expertos as _expertos

ACCESS_DEFAULT = _expertos.ACCESS_DEFAULT
PANEL_DEFAULT = _expertos.PANEL_DEFAULT
Configuracion = _expertos.Configuracion
_ajustes = _expertos._ajustes
_cargar_contrato = _expertos._cargar_contrato
_keyset_sha256 = _expertos._keyset_sha256
_metricas = _expertos._metricas
_minimizar_absoluto = _expertos._minimizar_absoluto
_minimizar_escala = _expertos._minimizar_escala
_predecir_online = _expertos._predecir_online
ejecutar = _expertos.ejecutar
leer_macro_h1 = _expertos.leer_macro_h1
leer_reales_r09_fundo = _expertos.leer_reales_r09_fundo
normalizar_fundo = _expertos.normalizar_fundo

# Aliases públicos históricos utilizados por override, residual y validadores.
predecir_online = _predecir_online
metricas = _metricas
cargar_contrato = _cargar_contrato


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, default=PANEL_DEFAULT)
    parser.add_argument("--access", type=Path, default=ACCESS_DEFAULT)
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar(panel=args.panel, access=args.access)
    if args.salida:
        escribir_json_reproducible(resultado, args.salida)
    print(
        json.dumps(
            {
                "ganador": resultado["ganador_micro_replay"],
                "contrato": resultado["evaluation_contract"],
                "metricas": resultado["metricas"],
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

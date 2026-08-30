"""Fachada CLI compatible del micro-replay residual online."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.proyeccion.candidatos import escribir_json_reproducible
from analitica.servicios import estado_expertos as _estado

ACCESS_DEFAULT = _estado.ACCESS_DEFAULT
PANEL_DEFAULT = _estado.PANEL_DEFAULT
Configuracion = _estado.ConfiguracionResidual
_keyset_sha256 = _estado._keyset_residual
_base = _estado._base_residual
_actualizar_estado = _estado._actualizar_residual
_predecir_online = _estado.predecir_residual_online
_resumen = _estado._resumen_residual
_por_fundo = _estado._por_fundo_residual
ejecutar = _estado.ejecutar_residual
cargar_contrato = _estado.cargar_contrato
metricas = _estado.metricas


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
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fachada CLI compatible del micro-replay de override experto."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.aplicacion.procesos.candidatos import escribir_json_reproducible
from analitica.aplicacion.servicios import estado_expertos as _estado

ACCESS_DEFAULT = _estado.ACCESS_DEFAULT
PANEL_DEFAULT = _estado.PANEL_DEFAULT
Configuracion = _estado.ConfiguracionOverride
_metricas_semana = _estado._metricas_semana_override
_actualizar = _estado._actualizar_override
_predecir = _estado.predecir_override
_keyset = _estado._keyset_override
ejecutar = _estado.ejecutar_override
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

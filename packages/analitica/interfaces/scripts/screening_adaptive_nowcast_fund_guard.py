"""Fachada CLI compatible para el guardia adaptativo por fundo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.aplicacion.procesos.candidatos import escribir_json_reproducible
from analitica.aplicacion.servicios import nowcast as _nowcast

ACCESS_DEFAULT = _nowcast.ACCESS_DEFAULT
R09_ACCESS_DEFAULT = _nowcast.R09_ACCESS_DEFAULT
BASE_CONGELADA = _nowcast.BASE_CONGELADA
ConfiguracionFundGuard = _nowcast.ConfiguracionFundGuard
ConfiguracionReconciliacionFundos = _nowcast.ConfiguracionReconciliacionFundos
_aplicar_guardia_online = _nowcast._aplicar_guardia_online
_configuraciones_guardia = _nowcast._configuraciones_guardia
_configuraciones_reconciliacion = _nowcast._configuraciones_reconciliacion
_deterioros_por_fundo = _nowcast._deterioros_por_fundo
_evidencia_fundo = _nowcast._evidencia_fundo
_evaluar = _nowcast._evaluar
_hash_configuracion = _nowcast._hash_configuracion
_max_deterioro = _nowcast._max_deterioro
_reconciliar_total_empresa_online = _nowcast._reconciliar_total_empresa_online
_seleccionar_guardia = _nowcast._seleccionar_guardia
_seleccionar_reconciliacion = _nowcast._seleccionar_reconciliacion
_wape = _nowcast._wape

# Aliases públicos y privados históricos: el script conserva su contrato de
# importación, pero la implementación ejecutable vive en el servicio.
ejecutar = _nowcast.ejecutar_fund_guard


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
                "base": resultado["configuracion_base_congelada"],
                "guardia": resultado["configuracion_guardia_congelada"],
                "reconciliacion": resultado["configuracion_reconciliacion_congelada"],
                "variante_seleccionada": resultado["variante_seleccionada"],
                "evaluaciones": resultado["evaluaciones"],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

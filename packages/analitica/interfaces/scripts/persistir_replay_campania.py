"""Genera y persiste un replay completo, una campaña por ejecución.

El script es deliberadamente explícito: R09 es una emisión publicada de referencia;
``MacroLegacy_v1`` y ``HibridoLegacyResidual_v1`` se generan con el mismo snapshot y
solo se comparan cuando comparten lote, emisión y semana objetivo. No abre Excel ni
usa una emisión posterior como predictor.

Uso:
    python -m analitica.interfaces.scripts.persistir_replay_campania --campania C2024

La ejecución no limita cortes por defecto. ``--max-cortes`` solo sirve para una prueba
rápida y no debe usarse para la corrida que se vaya a presentar.
"""

from __future__ import annotations

import json

from analitica.aplicacion.servicios import persistir_replay_campania as _servicio

# Aliases históricos: la implementación única vive en el servicio.
argparse = _servicio.argparse
np = _servicio.np
pd = _servicio.pd
time = _servicio.time
settings = _servicio.settings
RepositorioAnalytics = _servicio.RepositorioAnalytics
construir_backtest = _servicio.construir_backtest
controles_predicciones = _servicio.controles_predicciones
cargar_datos = _servicio.cargar_datos
NOMBRE_MODELO = _servicio.NOMBRE_MODELO
VERSION_MODELO = _servicio.VERSION_MODELO
backtest_hibrido_v1 = _servicio.backtest_hibrido_v1
backtest_macro_legacy_v1 = _servicio.backtest_macro_legacy_v1
metricas_pareadas_modelos = _servicio.metricas_pareadas_modelos
metricas_pronostico = _servicio.metricas_pronostico
MODELO_MACRO = _servicio.MODELO_MACRO
MODELO_R09 = _servicio.MODELO_R09

_argumentos = _servicio._argumentos
_completar_prediccion = _servicio._completar_prediccion
_emisiones_r09 = _servicio._emisiones_r09
construir_replay = _servicio.construir_replay
persistir_campania = _servicio.persistir_campania
resumir_salida_cli = _servicio.resumir_salida_cli


def main() -> None:
    args = _argumentos()
    resultado = persistir_campania(
        args.campania,
        horizonte=args.horizonte_semanas,
        max_cortes=args.max_cortes,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            resumir_salida_cli(resultado),
            ensure_ascii=False,
            indent=2,
            default=str,
            allow_nan=True,
        )
    )


if __name__ == "__main__":
    main()

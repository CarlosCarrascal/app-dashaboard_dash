"""Fachada CLI compatible para persistir OcurrenciaOnline sobre un universo común.

La lógica reusable vive en :mod:`analitica.aplicacion.servicios.persistir_ocurrencia_universo`.
Este módulo conserva los aliases históricos y la frontera CLI.
"""

from __future__ import annotations

import json

from analitica.aplicacion.servicios import persistir_ocurrencia_universo as _servicio

# Aliases históricos: la implementación única vive en el servicio.
argparse = _servicio.argparse
np = _servicio.np
pd = _servicio.pd
settings = _servicio.settings
RepositorioAnalytics = _servicio.RepositorioAnalytics
NOMBRE_MODELO = _servicio.NOMBRE_MODELO
VERSION_MODELO = _servicio.VERSION_MODELO
ejecutar_replay_hibrido_ocurrencia = _servicio.ejecutar_replay_hibrido_ocurrencia
metricas_semanales = _servicio.metricas_semanales
metricas_pareadas_modelos = _servicio.metricas_pareadas_modelos
MODELO_R09 = _servicio.MODELO_R09
MODELO_MACRO = _servicio.MODELO_MACRO
SNAPSHOT_ID = _servicio.SNAPSHOT_ID
RUNS_MACRO = _servicio.RUNS_MACRO
CLAVES = _servicio.CLAVES

_argumentos = _servicio._argumentos
_leer_universo = _servicio._leer_universo
_por_modelo = _servicio._por_modelo
_preparar_panel_ocurrencia = _servicio._preparar_panel_ocurrencia
_contrato_predicciones = _servicio._contrato_predicciones
construir_corrida = _servicio.construir_corrida
persistir = _servicio.persistir


def main() -> None:
    args = _argumentos()
    print(json.dumps(persistir(args.dry_run), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

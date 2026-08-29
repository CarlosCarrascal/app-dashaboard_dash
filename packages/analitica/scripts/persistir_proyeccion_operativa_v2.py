"""Fachada CLI compatible para la emisión operativa de ``HibridoOcurrenciaOnline_v2``.

La lógica reusable vive en :mod:`analitica.servicios.persistir_proyeccion_operativa_v2`.
Este módulo conserva los aliases históricos y la frontera CLI.
"""

from __future__ import annotations

import json

from analitica.servicios import persistir_proyeccion_operativa_v2 as _servicio

# Aliases históricos: la implementación única vive en el servicio.
argparse = _servicio.argparse
np = _servicio.np
pd = _servicio.pd
settings = _servicio.settings
RepositorioAnalytics = _servicio.RepositorioAnalytics
NOMBRE_MODELO = _servicio.NOMBRE_MODELO
VERSION_MODELO = _servicio.VERSION_MODELO
ejecutar_replay_hibrido_ocurrencia_v2 = _servicio.ejecutar_replay_hibrido_ocurrencia_v2
banda_horizonte = _servicio.banda_horizonte
MODELO_BASE = _servicio.MODELO_BASE
CLAVES_SEMANA = _servicio.CLAVES_SEMANA

_argumentos = _servicio._argumentos
_semana_inicio = _servicio._semana_inicio
_primero = _servicio._primero
_cargar_fuentes = _servicio._cargar_fuentes
_agregar_semana = _servicio._agregar_semana
_construir_base = _servicio._construir_base
_componentes = _servicio._componentes
_distribuir_a_panas = _servicio._distribuir_a_panas
construir_corrida = _servicio.construir_corrida
persistir = _servicio.persistir


def main() -> None:
    print(json.dumps(persistir(_argumentos().dry_run), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

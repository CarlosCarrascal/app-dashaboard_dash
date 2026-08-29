"""Fachada CLI compatible para persistir el replay de OcurrenciaOnline v2.

La lógica reusable vive en :mod:`analitica.servicios.persistir_ocurrencia_v2`.
"""

from __future__ import annotations

import json

from analitica.servicios import persistir_ocurrencia_v2 as _servicio

# Aliases históricos: la implementación única vive en el servicio.
argparse = _servicio.argparse
np = _servicio.np
pd = _servicio.pd
settings = _servicio.settings
RepositorioAnalytics = _servicio.RepositorioAnalytics
MODELO_V1 = _servicio.MODELO_V1
VERSION_V1 = _servicio.VERSION_V1
ejecutar_replay_hibrido_ocurrencia = _servicio.ejecutar_replay_hibrido_ocurrencia
MODELO_V2 = _servicio.MODELO_V2
VERSION_V2 = _servicio.VERSION_V2
ejecutar_replay_hibrido_ocurrencia_v2 = _servicio.ejecutar_replay_hibrido_ocurrencia_v2
metricas_cobertura_operacional = _servicio.metricas_cobertura_operacional
metricas_pronostico = _servicio.metricas_pronostico
MODELO_R09 = _servicio.MODELO_R09
MODELO_MACRO = _servicio.MODELO_MACRO
MODELO_NAIVE = _servicio.MODELO_NAIVE
SNAPSHOT_ID = _servicio.SNAPSHOT_ID
RUNS_ORIGEN = _servicio.RUNS_ORIGEN
CLAVES = _servicio.CLAVES

_argumentos = _servicio._argumentos
_leer_fuentes = _servicio._leer_fuentes
_expandir_referencia = _servicio._expandir_referencia
_expandir_v1 = _servicio._expandir_v1
_naive = _servicio._naive
_contrato = _servicio._contrato
_metricas_modelo = _servicio._metricas_modelo
construir_corrida = _servicio.construir_corrida
persistir = _servicio.persistir


def main() -> None:
    print(json.dumps(persistir(_argumentos().dry_run), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

"""Persiste una corrida de replay con la referencia R09 reconstruida.

La corrida anterior conserva una selección histórica incompleta de R09. Este script no
la modifica: clona los modelos evaluados de la última corrida completa y reemplaza solo
la referencia R09 por la selección vintage obtenida desde ``stg.v_r09_forecast``.

Las filas reales sin emisión R09 se conservan como ``SIN_EMISION_R09`` con p50=0 y
``emitio_prediccion=false``. Eso permite medir por separado cobertura y precisión sin
inventar un pronóstico.

Uso:
    python -m analitica.interfaces.scripts.persistir_replay_r09_corregido
"""

from __future__ import annotations

import json

from analitica.aplicacion.servicios import persistir_replay_r09_corregido as _servicio

# Aliases históricos: la implementación única vive en el servicio.
argparse = _servicio.argparse
np = _servicio.np
pd = _servicio.pd
settings = _servicio.settings
RepositorioAnalytics = _servicio.RepositorioAnalytics
metricas_cobertura_operacional = _servicio.metricas_cobertura_operacional
metricas_pronostico = _servicio.metricas_pronostico
MODELO_R09 = _servicio.MODELO_R09
CONFIG_FUENTE = _servicio.CONFIG_FUENTE
_parsear_argumentos = _servicio._parsear_argumentos
_leer_base = _servicio._leer_base
_leer_r09_emitido = _servicio._leer_r09_emitido
_leer_real_universo = _servicio._leer_real_universo
_preparar_r09 = _servicio._preparar_r09
_metricas = _servicio._metricas
persistir = _servicio.persistir


def main() -> None:
    _parsear_argumentos(__doc__)
    resultado = persistir()
    if resultado.get("reused"):
        print(json.dumps({"run_id": resultado["run_id"], "reused": True}))
        return
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

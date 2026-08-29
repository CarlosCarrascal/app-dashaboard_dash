"""Añade la referencia R09 de C2025 a la corrida completa ya validada.

No recalcula el modelo: copia únicamente la emisión publicada que existía en la
corrida 76 y la incorpora a la corrida 77, que ya contiene el replay completo de
C2025. Esto evita volver a gastar horas de calibración para corregir una selección de
filas de referencia.
"""

from __future__ import annotations

import argparse
import json

from analitica.servicios import completar_replay_c2025_r09 as _servicio

# Reexportaciones históricas: públicos y privados conservan identidad y firma.
np = _servicio.np
pd = _servicio.pd
settings = _servicio.settings
RepositorioAnalytics = _servicio.RepositorioAnalytics
metricas_cobertura_operacional = _servicio.metricas_cobertura_operacional
metricas_pronostico = _servicio.metricas_pronostico
RUN_COMPLETO = _servicio.RUN_COMPLETO
RUN_ORIGEN = _servicio.RUN_ORIGEN
SNAPSHOT_ID = _servicio.SNAPSHOT_ID
MODELO_R09 = _servicio.MODELO_R09
_leer = _servicio._leer
_metricas = _servicio._metricas
leer = _servicio.leer
metricas = _servicio.metricas
ejecutar = _servicio.ejecutar


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    resumen = ejecutar()
    print(json.dumps(resumen, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

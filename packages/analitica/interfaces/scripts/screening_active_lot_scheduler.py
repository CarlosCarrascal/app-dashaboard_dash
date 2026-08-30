"""Screening candidate-only de auto-scheduler de lotes para MacroLegacy h1.

El candidato usa exclusivamente cosechas H01 anteriores a cada emision para
derivar Turno, ultimo ingreso y dias de reingreso.  No usa R09 ni calendarios
Excel como predictor.  R09 se incorpora solamente despues de congelar la
configuracion seleccionada, como referencia de evaluacion.

El scheduler no aplica gates binarios. Redistribuye continuamente el total
Macro de cada fundo entre lotes mediante una mezcla de participacion Macro y
actividad esperada. Opcionalmente escala el total con residuos historicos
cerrados anteriores a la emision. No escribe en PostgreSQL ni publica nada.

La logica de negocio vive en :mod:`analitica.aplicacion.servicios.active_lot_scheduler`.
Este modulo conserva la fachada CLI y los nombres historicos para consumidores
que todavia importan el script directamente.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.aplicacion.servicios import active_lot_scheduler as _scheduler

# Constantes y clase históricas: la implementación única vive en el servicio.
RUN_ID = _scheduler.RUN_ID
CAMPANIAS = _scheduler.CAMPANIAS
FUNDOS = _scheduler.FUNDOS
SEMANA_DESARROLLO_FINAL = _scheduler.SEMANA_DESARROLLO_FINAL
SEMANAS_HOLDOUT = _scheduler.SEMANAS_HOLDOUT
CIERRE_C2026 = _scheduler.CIERRE_C2026
RUTA_SALIDA = _scheduler.RUTA_SALIDA
R09_ACCESS_DEFAULT = _scheduler.R09_ACCESS_DEFAULT
ConfiguracionScheduler = _scheduler.ConfiguracionScheduler

# Fachada compatible: se conservan aliases públicos y privados históricos.
configuraciones = _scheduler.configuraciones
_normalizar_fechas = _scheduler._normalizar_fechas
leer_fuentes = _scheduler.leer_fuentes
_intervalo_mediano = _scheduler._intervalo_mediano
_distancia_periodica = _scheduler._distancia_periodica
derivar_contexto_asof = _scheduler.derivar_contexto_asof
_actividad = _scheduler._actividad
_metricas = _scheduler._metricas
_escala_online = _scheduler._escala_online
predecir_scheduler = _scheduler.predecir_scheduler
construir_verdad = _scheduler.construir_verdad
_cobertura_y_ceros = _scheduler._cobertura_y_ceros
bootstrap_pareado = _scheduler.bootstrap_pareado
resumir = _scheduler.resumir
anexar_r09 = _scheduler.anexar_r09
resumir_con_r09 = _scheduler.resumir_con_r09
seleccionar_configuracion = _scheduler.seleccionar_configuracion
_keyset_sha256 = _scheduler._keyset_sha256
ejecutar = _scheduler.ejecutar
_json_default = _scheduler._json_default
escribir_resultado = _scheduler.escribir_resultado

# Reexportaciones históricas que provenían del servicio de campañas.
leer_r09_access = _scheduler.leer_r09_access
normalizar_fundo = _scheduler.normalizar_fundo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, default=RUN_ID)
    parser.add_argument("--r09-access", type=Path, default=R09_ACCESS_DEFAULT)
    parser.add_argument("--salida", type=Path, default=RUTA_SALIDA)
    args = parser.parse_args()
    resultado = ejecutar(args.run_id, args.r09_access)
    escribir_resultado(resultado, args.salida)
    print(
        json.dumps(
            {
                "configuracion_id": resultado["configuracion_id"],
                "holdout": resultado["metricas"]["c2026_holdout_s31_s33"],
                "veredicto": resultado["veredicto"],
            },
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

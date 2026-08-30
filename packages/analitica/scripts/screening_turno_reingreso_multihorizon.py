"""Micro-replay candidate-only de Turno + reingreso sobre run73.

El script lee ``MacroLegacy_v1`` h1-h6 de la misma emision y lote, deriva el
ultimo cierre, Turno y una mediana jerarquica de reingreso usando solo H01
anterior a cada emision, y redistribuye el total h1-h6 con las funciones puras
de :mod:`analitica.proyeccion.candidate_turno_temporal`.

La seleccion usa exclusivamente semanas objetivo S13-S30. S31-S33 es holdout.
R09 se incorpora solo despues de elegir la configuracion y se evalua sobre las
claves donde realmente emitio. No hay escrituras ni publicacion en PostgreSQL.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.proyeccion.candidatos import escribir_json_reproducible
from analitica.servicios import turno_reingreso as _servicio

# Contrato y constantes históricos.
RUN_ID = _servicio.RUN_ID
CAMPANIA = _servicio.CAMPANIA
HORIZONTE_MIN = _servicio.HORIZONTE_MIN
HORIZONTE_MAX = _servicio.HORIZONTE_MAX
SEMANA_INICIAL = _servicio.SEMANA_INICIAL
SEMANA_DESARROLLO_FINAL = _servicio.SEMANA_DESARROLLO_FINAL
SEMANA_FINAL = _servicio.SEMANA_FINAL
CIERRE_CERTIFICADO = _servicio.CIERRE_CERTIFICADO
CONTRACT_ID = _servicio.CONTRACT_ID
CLAVE = _servicio.CLAVE
GRUPO_CURVA = _servicio.GRUPO_CURVA
MAPEO_FUNDO = _servicio.MAPEO_FUNDO
ConfiguracionTurnoTemporal = _servicio.ConfiguracionTurnoTemporal
aplicar_turno_reingreso_candidate = _servicio.aplicar_turno_reingreso_candidate
normalizar_forecast_candidate = _servicio.normalizar_forecast_candidate
postgres_dsn = _servicio.postgres_dsn

# Reexportación explícita: mantiene tanto APIs públicas como nombres privados
# históricos sin duplicar ninguna implementación.
_normalizar_fundo = _servicio._normalizar_fundo
leer_fuentes = _servicio.leer_fuentes
preparar_macro = _servicio.preparar_macro
preparar_r09 = _servicio.preparar_r09
_preparar_h01 = _servicio._preparar_h01
_mediana_grupo = _servicio._mediana_grupo
derivar_contexto_asof = _servicio.derivar_contexto_asof
enriquecer_macro = _servicio.enriquecer_macro
rejilla_configuraciones = _servicio.rejilla_configuraciones
aplicar_configuracion = _servicio.aplicar_configuracion
auditar_paridad_funcion_pura = _servicio.auditar_paridad_funcion_pura
_banda_horizonte = _servicio._banda_horizonte
_metricas = _servicio._metricas
_metricas_bandas = _servicio._metricas_bandas
_semanas_ganadas = _servicio._semanas_ganadas
_alinear_candidato = _servicio._alinear_candidato
_score_desarrollo = _servicio._score_desarrollo
seleccionar_configuracion = _servicio.seleccionar_configuracion
_cobertura_r09 = _servicio._cobertura_r09
_cobertura_r09_bandas = _servicio._cobertura_r09_bandas
comparar_r09_despues = _servicio.comparar_r09_despues
_hash_claves = _servicio._hash_claves
evaluar_panel = _servicio.evaluar_panel


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--salida",
        type=Path,
        default=Path(".tmp/screening_turno_reingreso_multihorizon.json"),
    )
    return parser


def main() -> int:
    args = construir_parser().parse_args()
    macro, r09, h01 = leer_fuentes()
    resultado = evaluar_panel(macro, r09, h01)
    escribir_json_reproducible(resultado, args.salida)
    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

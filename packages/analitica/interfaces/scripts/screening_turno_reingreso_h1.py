"""Fachada CLI compatible para el screening candidate-only de Turno + reingreso H1.

La lógica de negocio vive en :mod:`analitica.aplicacion.servicios.turno_reingreso_h1`.
Este módulo conserva los aliases públicos y privados, firmas, argumentos CLI,
serialización y ruta de salida históricas.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.aplicacion.servicios import turno_reingreso_h1 as _servicio

# Reexportaciones históricas, incluidas las dependencias que algunos notebooks
# importaban desde el script antes de la extracción del servicio.
hashlib = _servicio.hashlib
Iterable = _servicio.Iterable
Any = _servicio.Any
asdict = _servicio.asdict
np = _servicio.np
pd = _servicio.pd
psycopg = _servicio.psycopg
escribir_json_reproducible = _servicio.escribir_json_reproducible
ConfiguracionTurnoTemporal = _servicio.ConfiguracionTurnoTemporal
aplicar_turno_reingreso_candidate = _servicio.aplicar_turno_reingreso_candidate
postgres_dsn = _servicio.postgres_dsn

RUN_ID = _servicio.RUN_ID
CAMPANIA = _servicio.CAMPANIA
SEMANA_INICIAL = _servicio.SEMANA_INICIAL
SEMANA_FINAL = _servicio.SEMANA_FINAL
SEMANA_DESARROLLO_FINAL = _servicio.SEMANA_DESARROLLO_FINAL
CIERRE_CERTIFICADO = _servicio.CIERRE_CERTIFICADO
CONTRACT_ID = _servicio.CONTRACT_ID
CLAVE_LOTE = _servicio.CLAVE_LOTE
MAPEO_FUNDO = _servicio.MAPEO_FUNDO

_normalizar_fundo = _servicio._normalizar_fundo
_emitio_r09 = _servicio._emitio_r09
leer_fuentes = _servicio.leer_fuentes
preparar_contrato = _servicio.preparar_contrato
derivar_turno_reingreso_asof = _servicio.derivar_turno_reingreso_asof
auditar_aplicabilidad_h1 = _servicio.auditar_aplicabilidad_h1
_rejilla_configuraciones = _servicio._rejilla_configuraciones
demostrar_noop_h1 = _servicio.demostrar_noop_h1
_metricas_agregadas = _servicio._metricas_agregadas
_cobertura = _servicio._cobertura
_evaluar_split = _servicio._evaluar_split
_keyset_sha256 = _servicio._keyset_sha256
evaluar_panel = _servicio.evaluar_panel
ejecutar = _servicio.ejecutar


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--salida",
        type=Path,
        default=Path(".tmp/screening_turno_reingreso_h1.json"),
    )
    args = parser.parse_args()
    resultado = ejecutar()
    escribir_json_reproducible(resultado, args.salida)
    resumen = {
        "veredicto": resultado["veredicto"],
        "contrato": resultado["evaluation_contract"],
        "aplicabilidad": resultado["aplicabilidad"],
        "cobertura_feature": resultado["feature_turno_reingreso_asof"],
        "metricas": resultado["metricas"],
        "artefacto": str(args.salida),
    }
    print(json.dumps(resumen, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

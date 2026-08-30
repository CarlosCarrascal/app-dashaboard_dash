"""Diagnóstico candidate-only de v2 frente a nowcast y correcciones h1--h6.

No persiste, no publica y no modifica releases. Usa la corrida 81 sólo como
laboratorio porque la release aprobada de v2 conserva actualmente h1.

La lógica reusable vive en :mod:`analitica.aplicacion.servicios.diagnostico_nowcast_horizontes`.
Este archivo conserva únicamente la composición CLI porque los consumidores
históricos ejecutan esta ruta directamente y esperan sus aliases, firmas,
serialización y rutas de salida.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.aplicacion.servicios import diagnostico_nowcast_horizontes as _servicio

# Aliases históricos: la implementación única vive en el servicio.
pd = _servicio.pd
psycopg = _servicio.psycopg
postgres_dsn = _servicio.postgres_dsn
RUN_V2_APROBADO = _servicio.RUN_V2_APROBADO
RUN_V2_LABORATORIO = _servicio.RUN_V2_LABORATORIO
RUN_NOWCAST = _servicio.RUN_NOWCAST
ConfiguracionCorreccionHorizonte = _servicio.ConfiguracionCorreccionHorizonte
aplicar_correccion_horizonte = _servicio.aplicar_correccion_horizonte
configuraciones_loop = _servicio.configuraciones_loop
ejecutar_loop_horizonte = _servicio.ejecutar_loop_horizonte
metricas_horizonte = _servicio.metricas_horizonte
leer_v2 = _servicio.leer_v2
leer_nowcast = _servicio.leer_nowcast
_seleccionar_total_nowcast = _servicio._seleccionar_total_nowcast
_resumen_serie_semanal = _servicio._resumen_serie_semanal
_seleccionar_vintage_coherente = _servicio._seleccionar_vintage_coherente
_metricas_serie = _servicio._metricas_serie
resumen_nowcast = _servicio.resumen_nowcast
ejecutar = _servicio.ejecutar


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar()
    texto = json.dumps(resultado, ensure_ascii=False, indent=2, default=str)
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(texto, encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

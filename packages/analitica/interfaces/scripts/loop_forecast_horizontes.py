"""Fachada CLI compatible para el loop de forecast por horizontes.

La lógica reusable vive en :mod:`analitica.aplicacion.servicios.loop_forecast_horizontes`.
Este módulo conserva aliases públicos/privados, firmas, argumentos, JSON y
rutas históricas.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.aplicacion.servicios import loop_forecast_horizontes as _servicio

# Aliases históricos: la implementación única vive en el servicio.
Any = _servicio.Any
pd = _servicio.pd
psycopg = _servicio.psycopg
postgres_dsn = _servicio.postgres_dsn
RUN_MACRO_MULTI = _servicio.RUN_MACRO_MULTI
RUN_H1_APROBADO = _servicio.RUN_H1_APROBADO
RUN_R09_MULTI = _servicio.RUN_R09_MULTI
RUN_NOWCAST = _servicio.RUN_NOWCAST
CIERRES = _servicio.CIERRES
HORIZONTES = _servicio.HORIZONTES
HORIZONTES_LARGOS = _servicio.HORIZONTES_LARGOS
ConfiguracionCorreccionHorizonte = _servicio.ConfiguracionCorreccionHorizonte
aplicar_correccion_horizonte = _servicio.aplicar_correccion_horizonte
configuraciones_loop = _servicio.configuraciones_loop
ejecutar_loop_por_horizonte = _servicio.ejecutar_loop_por_horizonte
seleccionar_vintage_coherente = _servicio.seleccionar_vintage_coherente
_leer_predicciones = _servicio._leer_predicciones
_normalizar_fundo = _servicio._normalizar_fundo
_consolidar_fundos = _servicio._consolidar_fundos
_panel_base = _servicio._panel_base
_semanal = _servicio._semanal
_metricas = _servicio._metricas
_aplicar_mejores = _servicio._aplicar_mejores
_metricas_por_horizonte = _servicio._metricas_por_horizonte
_comparar_r09 = _servicio._comparar_r09
_leer_nowcast = _servicio._leer_nowcast
_resumen_nowcast_vs_v2 = _servicio._resumen_nowcast_vs_v2
ejecutar = _servicio.ejecutar


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campania", default="C2026", choices=sorted(CIERRES))
    parser.add_argument("--desarrollo-hasta")
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar(args.campania, args.desarrollo_hasta)
    texto = json.dumps(resultado, ensure_ascii=False, indent=2, default=str)
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(texto, encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

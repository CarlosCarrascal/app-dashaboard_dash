"""Replay candidate-only del router parámetros rezagados + Macro congelada.

No persiste ni publica. Reemplaza el h1 de Macro únicamente cuando existe un
snapshot completo de los cuatro fundos en la emisión anterior. El peso de la
estabilización naive se vuelve a seleccionar en cada origen usando solamente
semanas ya cerradas.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.proyeccion.candidatos import escribir_json_reproducible
from analitica.servicios import router_parametros_lagged as _servicio

# Reexportaciones históricas: el cálculo vive en el servicio, pero el módulo
# ejecutable conserva nombres y objetos para consumidores existentes.
ACCESS_DEFAULT = _servicio.ACCESS_DEFAULT
ARTEFACTO_LAGGED = _servicio.ARTEFACTO_LAGGED
ConfiguracionHibridoParametrosLagged = _servicio.ConfiguracionHibridoParametrosLagged
np = _servicio.np
pd = _servicio.pd
agregar = _servicio.agregar
cargar_reales_y_r09 = _servicio.cargar_reales_y_r09
ejecutar = _servicio.ejecutar
leer = _servicio.leer
seleccionar_peso_parametros_asof = _servicio.seleccionar_peso_parametros_asof
_bootstrap_beneficio = _servicio._bootstrap_beneficio
_metricas = _servicio._metricas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--access", type=Path, default=ACCESS_DEFAULT)
    parser.add_argument("--artefacto-lagged", type=Path, default=ARTEFACTO_LAGGED)
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar(access=args.access, artefacto_lagged=args.artefacto_lagged)
    if args.salida:
        escribir_json_reproducible(resultado, args.salida)
    print(
        json.dumps(
            {
                "resumen": resultado["resumen"],
                "por_horizonte": resultado["por_horizonte"],
                "bootstrap": resultado["bootstrap_beneficio_wape_vs_r09"],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

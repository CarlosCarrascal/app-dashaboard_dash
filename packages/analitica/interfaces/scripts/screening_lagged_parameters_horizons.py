"""Fachada CLI compatible para el screening de parámetros rezagados por horizonte.

La lógica de negocio vive en :mod:`analitica.aplicacion.servicios.lagged_parameters_horizons`.
Este módulo conserva aliases públicos/privados, firmas, CLI, serialización y
rutas históricas.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.aplicacion.servicios import lagged_parameters_horizons as _servicio

# Aliases públicos y privados históricos: la implementación única está en el
# servicio, pero el módulo ejecutable conserva los objetos importables.
ACCESS_DEFAULT = _servicio.ACCESS_DEFAULT
ROOT_DEFAULT = _servicio.ROOT_DEFAULT
cargar_reales_y_r09 = _servicio.cargar_reales_y_r09
ejecutar = _servicio.ejecutar
ejecutar_proyeccion_semanal_dataframe = _servicio.ejecutar_proyeccion_semanal_dataframe
escribir_json_reproducible = _servicio.escribir_json_reproducible
leer_libro_operativo = _servicio.leer_libro_operativo
pd = _servicio.pd
seleccionar_libros_parametros = _servicio.seleccionar_libros_parametros

_libros = _servicio._libros


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--access", type=Path, default=ACCESS_DEFAULT)
    parser.add_argument("--campania", default="C2026")
    parser.add_argument("--emisiones", nargs="*", type=int, default=[26, 27, 28, 29, 32, 33])
    parser.add_argument("--ultima-semana-cerrada", type=int, default=34)
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar(
        root=args.root,
        access=args.access,
        campania=args.campania,
        emisiones=tuple(args.emisiones),
        ultima_semana_cerrada=args.ultima_semana_cerrada,
    )
    if args.salida:
        escribir_json_reproducible(resultado, args.salida)
    print(json.dumps(resultado["resumen"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

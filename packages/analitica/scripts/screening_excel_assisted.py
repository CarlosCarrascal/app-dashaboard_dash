"""Fachada CLI compatible para el screening asistido por Excel.

La implementación de negocio vive en :mod:`analitica.servicios.excel_assisted`.
Este módulo conserva los nombres históricos, la CLI y la serialización.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.proyeccion.candidate_preflight import escribir_json_reproducible
from analitica.servicios import excel_assisted as _servicio

ROOT_DEFAULT = _servicio.ROOT_DEFAULT
ACCESS_DEFAULT = _servicio.ACCESS_DEFAULT
SEMANAS_LIMPIAS = _servicio.SEMANAS_LIMPIAS
np = _servicio.np
pd = _servicio.pd

_conexion_access = _servicio._conexion_access
_columna_campania = _servicio._columna_campania
cargar_reales_y_r09 = _servicio.cargar_reales_y_r09
fecha_lunes_iso = _servicio.fecha_lunes_iso
construir_modelo_operativo_excel = _servicio.construir_modelo_operativo_excel
ejecutar = _servicio.ejecutar


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--access", type=Path, default=ACCESS_DEFAULT)
    parser.add_argument("--campania", default="C2026")
    parser.add_argument("--semanas", nargs="*", type=int, default=list(SEMANAS_LIMPIAS))
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar(
        args.root,
        args.access,
        campania=args.campania,
        semanas=tuple(args.semanas),
    )
    if args.salida:
        escribir_json_reproducible(resultado, args.salida)
    print(json.dumps(resultado["metricas"], ensure_ascii=False, indent=2, default=str))
    print(json.dumps({"omitidas": resultado["omitidas"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

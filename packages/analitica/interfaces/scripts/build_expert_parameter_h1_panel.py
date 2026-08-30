"""Fachada CLI compatible para construir el panel experto H1.

La lógica de negocio vive en :mod:`analitica.aplicacion.servicios.expert_parameter_h1_panel`.
Este módulo conserva los aliases históricos, las firmas, la CLI, la serialización
y las rutas de salida.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.aplicacion.servicios import expert_parameter_h1_panel as _servicio

# Aliases históricos: la implementación única vive en el servicio.
ROOT_DEFAULT = _servicio.ROOT_DEFAULT
SEMANAS_CERTIFICADAS = _servicio.SEMANAS_CERTIFICADAS
construir = _servicio.construir
ejecutar_proyeccion_semanal_dataframe = _servicio.ejecutar_proyeccion_semanal_dataframe
leer_libro_operativo = _servicio.leer_libro_operativo
pd = _servicio.pd
seleccionar_libros_parametros = _servicio.seleccionar_libros_parametros


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--campania", default="C2026")
    parser.add_argument("--semanas", nargs="*", type=int, default=list(SEMANAS_CERTIFICADAS))
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()
    tabla, metadatos = construir(
        root=args.root,
        campania=args.campania,
        semanas_fuente=tuple(args.semanas),
    )
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    tabla.to_parquet(args.salida, index=False)
    args.salida.with_suffix(".json").write_text(
        json.dumps(metadatos, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {k: v for k, v in metadatos.items() if k not in {"faltantes", "errores"}}, indent=2
        )
    )
    print(
        json.dumps(
            {"n_faltantes": len(metadatos["faltantes"]), "errores": metadatos["errores"]}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

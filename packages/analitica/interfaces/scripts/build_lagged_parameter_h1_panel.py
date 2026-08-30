"""Construye una caché candidate-only de parámetros Excel rezagados para H1.

Cada emisión ``S`` usa exclusivamente el libro canónico ``S-1``. La salida no
contiene cosecha real ni R09: esos datos se incorporan después de proyectar, en
el evaluador. De este modo la caché puede reutilizarse sin contaminar el modelo.

No persiste en PostgreSQL ni publica en el dashboard.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.aplicacion.servicios import lagged_parameter_h1_panel as _servicio

ROOT_DEFAULT = _servicio.ROOT_DEFAULT
pd = _servicio.pd
ejecutar_proyeccion_semanal_dataframe = _servicio.ejecutar_proyeccion_semanal_dataframe
seleccionar_libros_parametros = _servicio.seleccionar_libros_parametros
leer_libro_operativo = _servicio.leer_libro_operativo
construir = _servicio.construir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--campania", default="C2026")
    parser.add_argument("--desde", type=int, default=1)
    parser.add_argument("--hasta", type=int, default=33)
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()
    tabla, metadatos = construir(
        root=args.root,
        campania=args.campania,
        semanas_fuente=tuple(range(args.desde, args.hasta + 1)),
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

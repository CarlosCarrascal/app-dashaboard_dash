"""Fachada pública de la interfaz de línea de órdenes analítica.

Los handlers viven en ``analitica.commands``; este módulo conserva la ruta
histórica, el entrypoint ``aquanqa-analytics`` y los símbolos que consumidores
existentes importan desde ``analitica.cli``.
"""

from __future__ import annotations

import argparse
import sys

from .commands.bhattacharya import ejecutar_bhattacharya
from .commands.common import (
    _parsear_horizontes,
    _raiz_operativa,
    _registrar_inicio,
    _repositorio,
    _salida,
)
from .commands.operational import ejecutar_project_operativo, ejecutar_validar_operativo
from .commands.parser import construir_parser
from .commands.relations import ejecutar_relaciones
from .commands.torneo import (
    _torneo,
    ejecutar_backtest,
    ejecutar_export,
    ejecutar_project,
    ejecutar_train,
)

__all__ = [
    "_parsear_horizontes",
    "_raiz_operativa",
    "_registrar_inicio",
    "_repositorio",
    "_salida",
    "_torneo",
    "ejecutar_bhattacharya",
    "ejecutar_backtest",
    "ejecutar_export",
    "ejecutar_project",
    "ejecutar_project_operativo",
    "ejecutar_relaciones",
    "ejecutar_train",
    "ejecutar_validar_operativo",
    "main",
    "parser",
]


def parser() -> argparse.ArgumentParser:
    """Devuelve el parser compatible de ``aquanqa-analytics``."""

    return construir_parser(
        {
            "ejecutar_relaciones": ejecutar_relaciones,
            "ejecutar_backtest": ejecutar_backtest,
            "ejecutar_train": ejecutar_train,
            "ejecutar_project": ejecutar_project,
            "ejecutar_export": ejecutar_export,
            "ejecutar_bhattacharya": ejecutar_bhattacharya,
            "ejecutar_validar_operativo": ejecutar_validar_operativo,
            "ejecutar_project_operativo": ejecutar_project_operativo,
        }
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

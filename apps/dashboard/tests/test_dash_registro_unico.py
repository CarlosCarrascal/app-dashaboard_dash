"""Reglas de seguridad para el descubrimiento de páginas y callbacks Dash."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "apps" / "dashboard"), str(ROOT / "packages")]

import dash  # noqa: E402
import dash._callback as callback_registry  # noqa: E402

import app as dashboard_app  # noqa: E402,F401


def _salidas_callback(spec: dict) -> list[str]:
    """Convierte la representación compacta de Dash en ``id.prop``."""
    return [parte.strip(".") for parte in spec.get("output", "").split("...") if parte.strip(".")]


def test_no_hay_dos_paginas_para_la_misma_ruta():
    rutas = Counter(page.get("path") for page in dash.page_registry.values())
    assert not {ruta: cantidad for ruta, cantidad in rutas.items() if cantidad > 1}


def test_no_hay_dos_callbacks_escribiendo_la_misma_salida():
    salidas = [
        salida
        for spec in callback_registry.GLOBAL_CALLBACK_LIST
        for salida in _salidas_callback(spec)
    ]
    duplicadas = {salida: cantidad for salida, cantidad in Counter(salidas).items() if cantidad > 1}
    assert not duplicadas

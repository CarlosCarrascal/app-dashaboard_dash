from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "interfaces" / "scripts"


def test_los_scripts_no_importan_nombres_privados_de_otros_scripts():
    problemas: list[str] = []
    for ruta in sorted(SCRIPTS.glob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.ImportFrom) or not nodo.module:
                continue
            if not nodo.module.startswith("analitica.interfaces.scripts."):
                continue
            privados = [alias.name for alias in nodo.names if alias.name.startswith("_")]
            if privados:
                problemas.append(f"{ruta.name}: {nodo.module}: {privados}")

    assert not problemas, "; ".join(problemas)


def test_los_scripts_no_importan_directamente_otros_scripts():
    problemas: list[str] = []
    for ruta in sorted(SCRIPTS.glob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom) and nodo.module:
                if nodo.module.startswith("analitica.interfaces.scripts."):
                    problemas.append(f"{ruta.name}: from {nodo.module}")
            elif isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    if alias.name.startswith("analitica.interfaces.scripts."):
                        problemas.append(f"{ruta.name}: import {alias.name}")

    assert not problemas, "; ".join(problemas)

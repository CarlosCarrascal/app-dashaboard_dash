"""Evita que la aplicación oficial vuelva a depender del dashboard legado."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "dashboard"
CORE = ROOT / "packages" / "analitica"


def _imports(archivo: Path) -> set[str]:
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    nombres: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.update(alias.name.split(".")[0] for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres.add(nodo.module.split(".")[0])
    return nombres


def test_dashboard_no_importa_streamlit_ni_el_nombre_anterior():
    prohibidos = {"streamlit", "dashboard_dash"}
    for archivo in APP.rglob("*.py"):
        assert not (_imports(archivo) & prohibidos), archivo.relative_to(ROOT)


def test_nucleo_analitico_no_importa_frameworks_web():
    prohibidos = {"streamlit", "dash", "dash_extensions", "fastapi"}
    for archivo in CORE.rglob("*.py"):
        assert not (_imports(archivo) & prohibidos), archivo.relative_to(ROOT)

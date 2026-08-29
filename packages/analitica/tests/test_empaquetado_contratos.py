from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _leer_toml(ruta: Path) -> dict:
    with ruta.open("rb") as archivo:
        return tomllib.load(archivo)


def test_access_es_opcional_en_las_dependencias_de_analitica_y_etl():
    analitica = _leer_toml(ROOT / "pyproject.toml")
    etl = _leer_toml(ROOT.parent.parent / "etl" / "pyproject.toml")

    extra_operativo = analitica["project"]["optional-dependencies"]["operativo"]
    assert any(dependencia.startswith("python-calamine") for dependencia in extra_operativo)
    assert any(dependencia.startswith("pyodbc") for dependencia in extra_operativo)

    dependencias_etl = etl["project"]["dependencies"]
    extra_access = etl["project"]["optional-dependencies"]["access"]
    assert not any(dependencia.startswith("pyodbc") for dependencia in dependencias_etl)
    assert any(dependencia.startswith("pyodbc") for dependencia in extra_access)


def test_el_dashboard_declara_los_iconos_svg_anidados():
    dashboard = _leer_toml(ROOT.parent.parent / "apps" / "dashboard" / "pyproject.toml")
    assets = dashboard["tool"]["setuptools"]["package-data"]["assets"]

    assert "icons/*.svg" in assets

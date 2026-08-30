from __future__ import annotations

import ast
from pathlib import Path

from analitica.aplicacion.servicios import cross_campaign

ROOT = Path(__file__).resolve().parents[1]
SERVICIOS = ROOT / "aplicacion" / "servicios"
PARTES = (
    SERVICIOS / "cross_campaign_lectura.py",
    SERVICIOS / "cross_campaign_features.py",
    SERVICIOS / "cross_campaign_prediccion.py",
    SERVICIOS / "cross_campaign_evaluacion.py",
    SERVICIOS / "cross_campaign_persistencia.py",
)


def test_la_fachada_reexporta_implementaciones_fisicamente_separadas() -> None:
    simbolos = {
        "construir_panel": "cross_campaign_lectura",
        "leer_macro_h1": "cross_campaign_lectura",
        "construir_features_asof": "cross_campaign_features",
        "Configuracion": "cross_campaign_prediccion",
        "predecir_rolling": "cross_campaign_prediccion",
        "seleccionar_configuracion": "cross_campaign_evaluacion",
        "ejecutar": "cross_campaign_evaluacion",
        "escribir_json": "cross_campaign_persistencia",
    }
    for nombre, modulo in simbolos.items():
        implementacion = getattr(cross_campaign, nombre)
        assert implementacion.__module__ == f"analitica.aplicacion.servicios.{modulo}"


def test_las_partes_no_importan_la_fachada() -> None:
    problemas: list[str] = []
    for ruta in PARTES:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom) and nodo.module and (
                nodo.module == "cross_campaign" or nodo.module.endswith(".cross_campaign")
            ):
                problemas.append(f"{ruta.name}: from {nodo.module}")
            elif isinstance(nodo, ast.Import) and any(
                alias.name == "analitica.aplicacion.servicios.cross_campaign"
                for alias in nodo.names
            ):
                problemas.append(
                    f"{ruta.name}: import analitica.aplicacion.servicios.cross_campaign"
                )
    assert not problemas, "; ".join(problemas)


def test_cross_campaign_sigue_siendo_una_fachada_sin_definiciones_ejecutables() -> None:
    ruta = SERVICIOS / "cross_campaign.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    definiciones = [
        nodo.name
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definiciones == []

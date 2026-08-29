from __future__ import annotations

import ast
from pathlib import Path

from analitica.servicios import nowcast

SERVICIOS = Path(__file__).parents[1] / "servicios"
PARTES = (
    SERVICIOS / "nowcast_partes_base.py",
    SERVICIOS / "nowcast_partes_intraweek.py",
    SERVICIOS / "nowcast_partes_adaptativo.py",
    SERVICIOS / "nowcast_partes_guardia.py",
)


def test_fachada_conserva_el_contrato_publico() -> None:
    assert nowcast.__all__ == [
        "ACCESS_DEFAULT",
        "BASE_CONGELADA",
        "Configuracion",
        "ConfiguracionAdaptativa",
        "ConfiguracionFundGuard",
        "ConfiguracionReconciliacionFundos",
        "EPS",
        "FUNDOS",
        "R09_ACCESS_DEFAULT",
        "RUNS_CERTIFICADOS",
        "agregar_empresa",
        "bootstrap_pareado",
        "calibrar_residuo_online",
        "cargar_contrato",
        "comparacion_pareada",
        "construir_contrato",
        "diagnostico_shares",
        "ejecutar_fund_guard",
        "leer_diario",
        "metricas",
        "metricas_adaptativa",
        "metricas_intraweek",
        "normalizar_fundo_r09",
        "predecir",
        "predecir_online",
        "sha256_archivo",
    ]
    assert all(hasattr(nowcast, nombre) for nombre in nowcast.__all__)


def test_las_partes_no_importan_la_fachada() -> None:
    for ruta in PARTES:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        imports = {
            nodo.module
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.ImportFrom)
            and nodo.module is not None
        }
        imports.update(
            alias.name
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.Import)
            for alias in nodo.names
        )
        assert "analitica.servicios.nowcast" not in imports

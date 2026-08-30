from __future__ import annotations

import ast
import inspect
from pathlib import Path

from analitica.aplicacion.servicios import cross_campaign, small_data
from analitica.interfaces.scripts import (
    screening_active_lot_scheduler,
    screening_cross_campaign_h1,
    screening_excel_parameter_deltas,
    screening_small_data_h1,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "interfaces" / "scripts"
TARGETS = (
    "screening_active_lot_scheduler.py",
    "screening_cross_campaign_h1.py",
    "screening_excel_parameter_deltas.py",
    "screening_small_data_h1.py",
)


def test_los_scripts_del_alcance_no_importan_otros_scripts() -> None:
    problemas: list[str] = []
    for nombre in TARGETS:
        ruta = SCRIPTS / nombre
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom) and nodo.module:
                if nodo.module.startswith("analitica.interfaces.scripts."):
                    problemas.append(f"{nombre}: from {nodo.module}")
            elif isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    if alias.name.startswith("analitica.interfaces.scripts."):
                        problemas.append(f"{nombre}: import {alias.name}")

    assert not problemas, "; ".join(problemas)


def test_las_fachadas_conservan_contratos_y_apuntan_a_servicios() -> None:
    assert screening_cross_campaign_h1.R09_ACCESS_DEFAULT == (
        cross_campaign.R09_ACCESS_DEFAULT
    )
    assert screening_cross_campaign_h1.normalizar_fundo is cross_campaign.normalizar_fundo
    assert screening_cross_campaign_h1.leer_r09_access is cross_campaign.leer_r09_access
    assert screening_cross_campaign_h1.preparar_r09_crudo is cross_campaign.preparar_r09_crudo
    assert screening_active_lot_scheduler.R09_ACCESS_DEFAULT == (
        cross_campaign.R09_ACCESS_DEFAULT
    )
    assert screening_active_lot_scheduler.normalizar_fundo is cross_campaign.normalizar_fundo
    assert screening_active_lot_scheduler.leer_r09_access is cross_campaign.leer_r09_access

    assert screening_excel_parameter_deltas.cargar_universo_lote is (
        small_data.cargar_universo_lote
    )
    assert inspect.signature(screening_small_data_h1.cargar_universo_lote) == inspect.signature(
        small_data.cargar_universo_lote
    )
    assert screening_small_data_h1.RUN_ID_DEFAULT == small_data.RUN_ID_DEFAULT
    assert screening_small_data_h1.CAMPANIA_DEFAULT == small_data.CAMPANIA_DEFAULT
    assert screening_small_data_h1.ULTIMO_CIERRE_DEFAULT == small_data.ULTIMO_CIERRE_DEFAULT

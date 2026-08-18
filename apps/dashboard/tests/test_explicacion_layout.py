"""Regresiones de la separación global/celda de Explicación del modelo."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "apps" / "dashboard"), str(ROOT / "packages")]

import app as dashboard_app  # noqa: E402,F401
from pages.modelo import explicacion  # noqa: E402


def _ids(componente) -> set[str]:
    encontrados: set[str] = set()

    def visitar(valor):
        if isinstance(valor, (list, tuple)):
            for hijo in valor:
                visitar(hijo)
            return
        if not hasattr(valor, "to_plotly_json"):
            return
        serializado = valor.to_plotly_json()
        props = serializado.get("props", {})
        if props.get("id"):
            encontrados.add(props["id"])
        visitar(props.get("children"))

    visitar(componente)
    return encontrados


def test_la_pagina_separa_global_y_auditoria_de_celda():
    layout = explicacion.layout()
    ids = _ids(layout)
    serializado = repr(layout.to_plotly_json())

    assert {"explicacion-bloque", "explicacion-contenido"} <= ids
    assert "¿Cómo convierte el modelo las variables en una predicción?" in serializado
    assert "Global (SHAP)" in serializado
    assert "Una celda" in serializado
    assert "RadioItems" not in serializado

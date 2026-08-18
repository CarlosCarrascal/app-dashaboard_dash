"""Regresiones de la lectura ejecutiva del módulo Modelo predictivo."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "apps" / "dashboard"), str(ROOT / "packages")]

import app as dashboard_app  # noqa: E402,F401
from pages.modelo import modelo  # noqa: E402


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


def test_las_salidas_principales_cargan_sin_checkbox():
    layout = modelo.layout()
    ids = _ids(layout)
    serializado = repr(layout.to_plotly_json())

    assert {"modelo-principal", "modelo-familias"} <= ids
    assert "modelo-comparar-familias" not in serializado
    assert "Respuesta corta" not in serializado


def test_el_modulo_explica_que_la_comparacion_no_es_una_recomendacion_causal():
    contenido = repr(modelo._respuesta_corta().to_plotly_json())
    assert "causal" in contenido

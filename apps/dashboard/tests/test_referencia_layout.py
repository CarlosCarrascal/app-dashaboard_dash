"""Regresiones visuales y estructurales del grupo Referencia."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "apps" / "dashboard"), str(ROOT / "packages")]

import app as dashboard_app  # noqa: E402,F401
from pages import datos_calidad, metodologia  # noqa: E402


def _serializado(componente) -> str:
    return repr(componente.to_plotly_json())


def _ids(componente) -> set[str]:
    encontrados: set[str] = set()

    def visitar(valor):
        if isinstance(valor, (list, tuple)):
            for hijo in valor:
                visitar(hijo)
            return
        if not hasattr(valor, "to_plotly_json"):
            return
        props = valor.to_plotly_json().get("props", {})
        if props.get("id"):
            encontrados.add(props["id"])
        visitar(props.get("children"))

    visitar(componente)
    return encontrados


def test_datos_y_calidad_conserva_filtros_y_tabla_en_el_layout():
    layout = datos_calidad.layout()
    ids = _ids(layout)
    serializado = _serializado(layout)

    assert {
        "calidad-hallazgos", "panel-grid", "f-fundo", "f-modulo",
        "f-semanas", "f-kgha", "f-sin-riego",
    } <= ids
    assert "¿Qué tan confiables son los datos que alimentan el análisis?" in serializado
    assert "Filtros del panel consolidado" in serializado


def test_metodologia_presenta_resumen_y_separa_las_tres_capas():
    serializado = _serializado(metodologia.layout())

    assert "¿Qué podemos afirmar y qué todavía no?" in serializado
    assert "Respuesta corta" in serializado
    assert "Tres resultados que deben mantenerse separados" in serializado
    assert "Qué falta para estimar un efecto agronómico" in serializado

"""Regresiones del montaje progresivo de la página Frutos y peso."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "apps" / "dashboard"), str(ROOT / "packages")]

import app as dashboard_app  # noqa: E402,F401
from pages.impacto import frutos_peso  # noqa: E402
from analitica.nucleo import clima  # noqa: E402
from components import ui  # noqa: E402


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


def test_outputs_interactivos_existen_en_el_primer_layout():
    ids = _ids(frutos_peso.layout())
    assert {
        "fp-modulo",
        "fp-trayectoria-body",
        "fp-picos-clima",
        "fp-picos-body",
        "fp-peso-clima",
        "fp-peso-body",
        "fp-floracion-objetivo",
        "fp-floracion-body",
        "fp-floracion-trigger",
        "fp-desfase-objetivo",
        "fp-desfase-variable",
        "fp-desfase-body",
        "fp-desfases-trigger",
    } <= ids


def test_frutos_tiene_un_solo_estado_de_carga_inicial():
    ids = _ids(frutos_peso.layout())
    assert "fp-carga-inicial" in ids
    assert "fp-pagina-lista" in ids
    assert {f"fp-listo-{parte}" for parte in (
        "resumen", "descomposicion", "trayectoria", "picos",
        "picos-grafico", "peso", "peso-grafico",
    )} <= ids


def test_floracion_opcional_no_deja_fallar_el_calculo_si_no_hay_columna():
    """Render puede no montar el Excel opcional de floración."""
    tabla = pd.DataFrame({"celda": ["M01"], "nsem": [1], "Frutos": [10.0]})

    assert clima.rezago_floracion(tabla).empty
    assert clima.rezagos_floracion_clima(tabla).empty


def test_panel_plegable_sin_id_sigue_siendo_valido():
    """Los paneles plegables comunes no necesitan un id para serializarse."""
    componente = ui.panel("Prueba", plegable=True)
    assert componente.to_plotly_json()["props"]["open"] is True

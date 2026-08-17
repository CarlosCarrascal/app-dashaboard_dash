"""Regresiones del montaje progresivo de la página Frutos y peso."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "apps" / "dashboard"), str(ROOT / "packages")]

import app as dashboard_app  # noqa: E402,F401
from pages.impacto import frutos_peso  # noqa: E402


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
        "fp-desfase-objetivo",
        "fp-desfase-variable",
        "fp-desfase-body",
    } <= ids


def test_frutos_tiene_un_solo_estado_de_carga_inicial():
    ids = _ids(frutos_peso.layout())
    assert "fp-carga-inicial" in ids
    assert "fp-pagina-lista" in ids
    assert {f"fp-listo-{parte}" for parte in (
        "resumen", "descomposicion", "trayectoria", "picos",
        "picos-grafico", "peso", "peso-grafico",
    )} <= ids

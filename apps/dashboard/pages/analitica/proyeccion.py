"""Coordinador liviano de la página operativa de Proyección."""

from __future__ import annotations

import dash
from dash import Input, Output, State, callback, dcc, html

from servicios.proyeccion import estado_proyeccion as datos

from .proyeccion_domain import (
    FUNDOS_OPERATIVOS,
    HORIZONTE_CAMPANIA,
    HORIZONTE_SEMANAS,
    MODELO_OPERATIVO_ACTUAL,
)
from .proyeccion_views import layout_view

dash.register_page(
    __name__, path="/analitica/proyeccion", name="Proyección", order=5, grupo="Plataforma analítica"
)


def layout():
    return layout_view(datos())


# Mantiene explícito el contrato de Dash y registra los callbacks exactamente una vez.
_DASH_IMPORT_CONTRACT = (Input, Output, State, callback, dcc, html)
from . import proyeccion_callbacks as _callbacks  # noqa: E402,F401

__all__ = [
    "layout",
    "FUNDOS_OPERATIVOS",
    "HORIZONTE_CAMPANIA",
    "HORIZONTE_SEMANAS",
    "MODELO_OPERATIVO_ACTUAL",
]

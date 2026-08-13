"""Entrada principal al análisis agronómico observacional.

Agrupa las vistas que antes competían en el menú: el estudio con controles, la
exploración descriptiva y el detalle por módulo. No cambia sus cálculos; cambia el orden
de lectura para que correlación, predicción y causalidad no se confundan.
"""

from __future__ import annotations

import streamlit as st

from config import ICONO
from nucleo import Panel
from vistas import clima, correlaciones, por_modulo


BLOQUES = {
    "evidencia": "Evidencia principal",
    "descriptivo": "Exploración descriptiva",
    "modulos": "Detalle por módulo y semana",
}


def render(panel: Panel) -> None:
    st.warning(
        "**Estado actual:** el tablero encuentra asociaciones climáticas, pero ninguna "
        "sobrevive al control no lineal del calendario. Esta sección mide evidencia "
        "observacional; todavía no estima un efecto causal por variable.",
        icon=ICONO["aviso"],
    )
    st.caption(
        "Orden recomendado: primero la evidencia principal; después la exploración de "
        "formas y, por último, la consistencia dentro de cada módulo. Frutos y peso están "
        "en la evidencia principal porque descomponen biológicamente el kg/ha."
    )

    bloque = st.radio(
        "Qué analizar",
        options=list(BLOQUES),
        format_func=lambda b: BLOQUES[b],
        horizontal=True,
        key="bloque_impacto",
    )
    st.divider()

    if bloque == "descriptivo":
        correlaciones.render(panel)
    elif bloque == "modulos":
        por_modulo.render(panel)
    else:
        clima.render(panel)


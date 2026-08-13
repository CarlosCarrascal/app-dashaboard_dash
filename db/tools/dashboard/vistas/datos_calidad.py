"""Datos y calidad: hallazgos de origen, panel consolidado y exportación."""

from __future__ import annotations

import streamlit as st

from nucleo import Panel
from vistas import panel_consolidado, resumen


def render(panel: Panel, origen: str) -> None:
    resumen.calidad(panel)
    st.divider()
    st.subheader("Panel consolidado y exportación")
    panel_consolidado.render(panel, origen)


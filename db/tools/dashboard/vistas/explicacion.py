"""Explicación del modelo: SHAP global y auditoría local en un solo lugar."""

from __future__ import annotations

import streamlit as st

import servicios as sv
from config import ICONO
from nucleo import Panel
from vistas import auditoria, importancia

BLOQUES = {
    "global": "Comportamiento global (SHAP)",
    "celda": "Auditoría de una celda",
}

# clave interna → (columna del panel, etiqueta corta, unidad)
OBJETIVOS_SHAP: dict[str, tuple[str, str, str]] = {
    "KgHa": ("KgHa", "kg/ha", "kg/ha"),
    "Frutos": ("Frutos", "Frutos", "frutos/planta"),
    "Peso": ("Peso", "Peso", "g"),
    "flores_promedio": ("flores_promedio", "Floración", "flores/turno"),
}


def render(panel: Panel) -> None:
    st.info(
        "Esta sección explica **cómo XGBoost usa las variables**. SHAP reparte una "
        "predicción del modelo; no estima cuánto cambiaría el campo al intervenir una "
        "variable climática.",
        icon=ICONO["info"],
    )
    bloque = st.radio(
        "Qué explicar",
        options=list(BLOQUES),
        format_func=lambda b: BLOQUES[b],
        horizontal=True,
        key="bloque_explicacion",
    )

    if bloque == "celda":
        # La auditoría de una celda muestra «kg/ha real» y sus unidades a lo largo de
        # toda la vista: cambiar el objetivo ahí exigiría reescribirla entera. Se deja
        # fija a KgHa; el comportamiento global sí puede explorar los tres.
        st.divider()
        ajuste = sv.entrenar(panel.tabla)
        auditoria.render(panel, ajuste)
        return

    disponibles = [
        o for o in OBJETIVOS_SHAP
        if o in panel.tabla.columns and panel.tabla[o].notna().sum() >= 30
    ]
    objetivo = st.selectbox(
        "Objetivo a explicar",
        disponibles,
        format_func=lambda o: OBJETIVOS_SHAP[o][1],
        key="explicacion_objetivo",
        help="El mismo modelo de 7 variables, entrenado contra kg/ha, Frutos, Peso o "
             "Floración — misma idea que la síntesis de Conclusiones y hallazgos, pero "
             "acá con el detalle completo: ranking, nube SHAP y dependencia por variable.",
    )
    st.divider()

    ajuste = sv.entrenar(panel.tabla, objetivo=objetivo)
    _, etiqueta_obj, unidad = OBJETIVOS_SHAP[objetivo]
    importancia.render(panel, ajuste, etiqueta_obj, unidad)


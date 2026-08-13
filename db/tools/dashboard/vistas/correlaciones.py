"""Pestaña «Correlaciones»: la asociación cruda, antes de cualquier modelo."""

from __future__ import annotations

import streamlit as st

import servicios as sv
from config import ICONO, VARIABLES_DESCRIPTIVAS
from nucleo import Panel
from vistas import graficos as g
from vistas.comun import selector_variable


@st.fragment
def render(panel: Panel) -> None:
    st.subheader("Matriz de correlación")
    st.caption(
        "Estas son las variables **sin desfase**, tal como se midieron. El promedio "
        "móvil que sí usa el modelo aparece en **Explicación del modelo** y **Modelo "
        "predictivo** — separado a propósito, para que esta sección muestre la asociación "
        "antes de cualquier decisión de ventana temporal."
    )
    metodo = st.radio("Método", ["Pearson (lineal)", "Spearman (monótona)"], horizontal=True)
    corr = sv.correlaciones_con_objetivo(
        panel.tabla, "pearson" if metodo.startswith("Pearson") else "spearman",
        VARIABLES_DESCRIPTIVAS,
    )
    st.plotly_chart(g.matriz_correlacion(corr), width="stretch")

    st.markdown("**Correlación de cada variable con el kg/ha**")
    contra_objetivo = corr["kg/ha"].drop("kg/ha")
    contra_objetivo.index = list(VARIABLES_DESCRIPTIVAS)
    st.plotly_chart(
        g.barras_correlacion(contra_objetivo, "correlación con kg/ha"), width="stretch"
    )

    st.info(
        "**Cómo leer esto.** Las variables de clima están fuertemente correlacionadas "
        "entre sí (DPV con Temp. máxima, Radiación con ETo): son casi la misma señal "
        "medida de tres maneras. Repartir el crédito entre ellas es en buena parte "
        "arbitrario. Además el clima es idéntico para todos los módulos de una misma "
        "semana — lo único que distingue a un módulo de otro es el riego.",
        icon=ICONO["info"],
    )

    st.markdown("**Dispersión contra kg/ha**")
    var = selector_variable(VARIABLES_DESCRIPTIVAS, "disp")
    st.plotly_chart(g.dispersion_contra_objetivo(panel.tabla, var), width="stretch")
    st.caption(
        "El color es el número de semana. Si los puntos se ordenan por color más que "
        "por la variable del eje X, lo que se está viendo es el calendario, no la variable."
    )

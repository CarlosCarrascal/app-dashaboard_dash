"""Pestaña «Por módulo y por semana».

Responde dos preguntas que el análisis celda-por-celda no contesta: si la relación se
repite dentro de cada módulo, y cuánto vale medida al grano al que el clima existe.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import servicios as sv
from config import CLIMA, ICONO, VARIABLES_DESCRIPTIVAS, etiqueta
from nucleo import Panel
from vistas import graficos as g
from vistas.comun import miles, selector_variable


def _resumen_de_signos(porm: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    """Cuántos módulos coinciden en el signo de cada correlación."""
    return pd.DataFrame(
        {
            "Variable": columnas,
            "Mediana": [porm[c].median() for c in columnas],
            "Mínimo": [porm[c].min() for c in columnas],
            "Máximo": [porm[c].max() for c in columnas],
            "Módulos con signo negativo": [
                f"{int((porm[c] < 0).sum())} de {len(porm)}" for c in columnas
            ],
        }
    )


@st.fragment
def render(panel: Panel) -> None:
    st.subheader("La relación, módulo por módulo")
    st.caption(
        "El clima se mide una vez por semana para todo el fundo, y con razón: la "
        "temperatura y el DPV no cambian de forma apreciable entre un módulo y el de al "
        "lado. La pregunta que sí se puede hacer es si la relación **se repite dentro de "
        "cada módulo** — si es física, debería."
    )

    porm = sv.por_modulo(panel.tabla)
    columnas = [c for c in (*(etiqueta(f) for f in CLIMA), "Riego")
                if c in porm.columns]
    st.plotly_chart(g.mapa_por_modulo(porm, columnas), width="stretch")

    st.dataframe(
        _resumen_de_signos(porm, columnas).style.format(
            {"Mediana": "{:+.3f}", "Mínimo": "{:+.3f}", "Máximo": "{:+.3f}"}
        ),
        width="stretch", hide_index=True,
    )

    st.markdown("#### Dónde cae la ventana de cosecha de cada módulo")
    st.caption(
        "Ésta es la clave para leer la tabla de arriba. El signo de la correlación depende "
        "de dónde se ubica la cosecha del módulo respecto de la curva anual de temperatura."
    )
    st.plotly_chart(g.ventana_de_cosecha(porm), width="stretch")

    tardios = porm.nlargest(2, etiqueta("TempMin"))
    st.warning(
        f"Los módulos que arrancan más tarde (S{tardios.Inicio.min()} y "
        f"S{tardios.Inicio.max()}) son los únicos con correlación **positiva**, y fuerte. "
        "Su cosecha crece hasta S52, que es justo cuando la temperatura también sube. "
        "Mismo clima, signo opuesto: lo que la correlación mide es **el solapamiento entre "
        "la ventana de cosecha y la curva anual de temperatura**, no una respuesta "
        "fisiológica a la temperatura.",
        icon=ICONO["aviso"],
    )

    st.divider()
    st.subheader("La relación al grano de la semana")
    st.caption(
        "Si el clima es un dato del fundo, la comparación que respeta ese grano es contra "
        "el kg/ha del fundo entero. Con una fila por semana la asociación es bastante más "
        "fuerte que celda por celda — y es la forma correcta de reportarla."
    )
    sem = sv.agregar_por_semana(panel.tabla)
    # Las columnas sin desfase: es la correlación cruda, no la del modelo. Las columnas
    # con lag no existen en el agregado semanal (son un promedio a nivel de módulo).
    corr_sem = pd.DataFrame(
        {
            "Variable": [etiqueta(f) for f in VARIABLES_DESCRIPTIVAS],
            "r": [sem[f].corr(sem.kg_ha) for f in VARIABLES_DESCRIPTIVAS],
        }
    )
    corr_sem["r² (varianza explicada)"] = corr_sem.r**2
    corr_sem = corr_sem.sort_values("r² (varianza explicada)", ascending=False)

    izq, der = st.columns([1, 1])
    with izq:
        st.dataframe(
            corr_sem.style.format({"r": "{:+.3f}", "r² (varianza explicada)": "{:.1%}"})
            .background_gradient(cmap="RdBu_r", subset=["r"], vmin=-1, vmax=1),
            width="stretch", hide_index=True,
        )
    with der:
        st.metric("Semanas", len(sem))
        st.metric("kg/ha del fundo, promedio", miles(sem.kg_ha.mean()))

    var = selector_variable(VARIABLES_DESCRIPTIVAS, "varsem", "Ver contra")
    st.plotly_chart(g.serie_semanal(sem, var), width="stretch")
    st.caption(
        "Las dos curvas se cruzan porque ambas siguen el calendario: la cosecha por la "
        "poda, la temperatura por la estación. Que se espejen no dice cuál mueve a cuál."
    )

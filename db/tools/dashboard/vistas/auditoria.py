"""Pestaña «Auditoría por módulo/semana»: de dónde sale un kg/ha concreto.

«kg/ha del modelo» no es un pronóstico: es cómo el XGBoost ya entrenado (`nucleo/modelo.py`)
describe esta celda usando las variables de `config.FEATURES`. `_demostracion` hace visible
esa cuenta en vez de dejarla detrás del número — con la ecuación real de la celda elegida y
una comprobación de que la suma cierra en todas las filas que entraron al ajuste (algunas se
descartan por no tener ventana de rezago completa; `ajuste.tiene()` distingue el caso).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import servicios as sv
from config import FEATURES, ICONO, PARAMS, etiqueta
from nucleo import Ajuste, Panel
from vistas import graficos as g
from vistas.comun import miles


def _ecuacion(base: float, contribuciones: pd.Series, prediccion: float) -> str:
    """La suma literal, variable por variable, en el mismo orden que la tabla de detalle."""
    orden = contribuciones.reindex(contribuciones.abs().sort_values(ascending=False).index)
    ancho = max(len(etiqueta(v)) for v in orden.index)
    lineas = [f"    {miles(base, '{:,.1f}'):>10}   valor base (promedio del panel)"]
    for var, valor in orden.items():
        signo = "+" if valor >= 0 else "−"
        lineas.append(f"{signo}   {miles(abs(valor), '{:,.1f}'):>10}   {etiqueta(var):<{ancho}}")
    lineas.append("    " + "─" * 16)
    lineas.append(f"  = {miles(prediccion, '{:,.1f}'):>10}   kg/ha del modelo (suma exacta)")
    return "\n".join(lineas)


def _demostracion(
    ajuste: Ajuste, contribuciones: pd.Series, prediccion: float, titulo: str, n_filas: int
) -> None:
    """Explica el cálculo, lo muestra con números reales, y verifica que cierra."""
    with st.expander("¿En qué cálculo se basa el «kg/ha del modelo»? Ver la demostración"):
        st.markdown(
            f"**Paso 1 — el modelo.** XGBoost ajustó {PARAMS['n_estimators']} árboles de "
            f"decisión (profundidad {PARAMS['max_depth']}) sobre las {n_filas} celdas del "
            "panel, cada uno corrigiendo el error que dejó el anterior (*gradient "
            f"boosting*). El resultado es una función de las {len(FEATURES)} variables "
            "que, para cualquier combinación de DPV, riego, radiación, ETo y temperaturas, "
            "devuelve un número. Hasta acá no hay reparto entre variables: es una caja que "
            "da un solo valor. El porqué de esta configuración está en la sección "
            "**Modelo predictivo**."
        )
        st.markdown(
            f"**Paso 2 — repartir ese número entre las {len(FEATURES)} variables.** Un "
            "solo número no dice cuánto pesó cada una. Para eso se usa SHAP (*SHapley "
            "Additive exPlanations*): reparte la diferencia entre la predicción de esta "
            "celda y el promedio general del panel, de forma que la suma sea exacta, no "
            "aproximada:"
        )
        st.latex(
            r"\text{kg/ha del modelo} \;=\; \text{valor base} \;+\; "
            rf"\sum_{{i=1}}^{{{len(FEATURES)}}} \phi_i"
        )
        st.markdown(
            "Para un modelo de árboles, `TreeExplainer` no estima esa suma por muestreo "
            "—que es lo que hace la versión genérica de SHAP con cualquier otro modelo—: "
            "recorre la estructura exacta de los árboles y calcula el valor de Shapley "
            "de forma cerrada. Es una identidad algebraica, no una lectura aproximada del "
            "gráfico."
        )
        st.markdown(f"**La demostración, con los números de {titulo}:**")
        st.code(_ecuacion(ajuste.base_value, contribuciones, prediccion), language=None)

        consistencia = sv.verificar_consistencia(ajuste, str(n_filas))
        if consistencia.todas_coinciden:
            st.success(
                "**Verificado, no asumido:** la misma igualdad se comprobó para las "
                f"{consistencia.n_filas} filas del panel, no solo para ésta. Coincide en "
                f"{consistencia.coinciden} de {consistencia.n_filas} "
                f"(diferencia máxima: {consistencia.diferencia_maxima:.4f} kg/ha, "
                "redondeo de punto flotante).",
                icon=ICONO["ok"],
            )
        else:
            st.error(
                "La igualdad NO se cumple en "
                f"{consistencia.n_filas - consistencia.coinciden} de "
                f"{consistencia.n_filas} filas (diferencia máxima "
                f"{consistencia.diferencia_maxima:.2f} kg/ha) — hay un error de cálculo "
                "en esta versión del tablero, no en la teoría.",
                icon=ICONO["error"],
            )

        st.warning(
            "**Qué NO demuestra esto.** Que la suma cierre exactamente prueba que el "
            "reparto está bien calculado — no prueba que el modelo generalice a datos "
            "nuevos ni que exista una relación causal. Lo primero se mide en **Qué "
            "explica el R²** y se recalcula con las ventanas activas. Lo segundo no lo "
            "puede probar ningún reparto interno de un modelo observacional: requiere "
            "un diseño causal con tratamiento, confusores y solapamiento.",
            icon=ICONO["aviso"],
        )


@st.fragment
def render(panel: Panel, ajuste: Ajuste) -> None:
    st.subheader("Auditoría de una celda concreta")
    st.caption(
        "Elegí un módulo y una semana: el gráfico descompone ese kg/ha variable por variable."
    )
    tabla = panel.tabla

    izq, der = st.columns(2)
    modulo = izq.selectbox("Módulo", sorted(tabla.celda.unique()))
    semanas = tabla.loc[tabla.celda == modulo].sort_values("nsem")
    kg_por_semana = dict(zip(semanas.Semana, semanas.KgHa, strict=True))
    semana = der.selectbox(
        "Semana",
        semanas.Semana.tolist(),
        format_func=lambda s: f"{s}  ·  {miles(kg_por_semana[s])} kg/ha",
    )

    indice = tabla.index[(tabla.celda == modulo) & (tabla.Semana == semana)][0]
    fila = tabla.loc[indice]

    if not ajuste.tiene(indice):
        st.warning(
            f"**{modulo} · {semana} no tiene ventana de rezago completa** (el módulo "
            "empezó a cosechar hace menos semanas que la ventana configurada, o tuvo un "
            "hueco justo antes). El modelo se entrenó sin esta celda — no hay «kg/ha del "
            "modelo» que mostrar para ella. Elegí otra semana, o achicá la ventana de "
            "desfase en el menú lateral.",
            icon=ICONO["aviso"],
        )
        st.metric("kg/ha real", miles(fila.KgHa))
        return

    contribuciones = ajuste.contribuciones(indice)
    prediccion = ajuste.prediccion(indice)

    m1, m2, m3 = st.columns(3)
    m1.metric("kg/ha real", miles(fila.KgHa))
    m2.metric("kg/ha del modelo", miles(prediccion),
              delta=f"{miles(prediccion - fila.KgHa, '{:+,.0f}')} vs real")
    m3.metric("Riego esa semana", f"{miles(fila.riego_lt_planta, '{:,.2f}')} L/planta")

    st.markdown("#### SHAP Waterfall")
    st.plotly_chart(
        g.waterfall(ajuste.base_value, contribuciones, prediccion, f"{modulo} · {semana}"),
        width="stretch",
    )
    _demostracion(ajuste, contribuciones, prediccion, f"{modulo} · {semana}",
                  len(ajuste.X))

    st.markdown("#### Valores de esa semana")
    detalle = pd.DataFrame(
        {
            "Variable": [etiqueta(f) for f in FEATURES],
            "Valor": [fila[f] for f in FEATURES],
            "Efecto (kg/ha)": [contribuciones[f] for f in FEATURES],
        }
    ).sort_values("Efecto (kg/ha)", key=abs, ascending=False)
    st.dataframe(
        detalle.style.format({"Valor": "{:.2f}", "Efecto (kg/ha)": "{:+.0f}"})
        .background_gradient(cmap="RdBu_r", subset=["Efecto (kg/ha)"]),
        width="stretch", hide_index=True,
    )

    st.markdown("#### El módulo a lo largo de la campaña")
    serie = tabla[tabla.celda == modulo].sort_values("nsem")
    st.plotly_chart(g.serie_del_modulo(serie, int(fila.nsem)), width="stretch")

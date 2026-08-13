"""Sección «Pregunta, datos y límites»: objetivo, alcance y grano disponible.

Es la primera pantalla. Su trabajo es que nadie confunda asociación, predicción y efecto
agronómico. Los hallazgos detallados se movieron a «Datos y calidad».
"""

from __future__ import annotations

import streamlit as st

import servicios as sv
from config import ICONO
from nucleo import Hallazgo, Panel
from vistas.comun import entero, explica_simple, glosario, tarjetas

COLOR_GRAVEDAD = {"alta": ICONO["error"], "media": ICONO["aviso"], "baja": ICONO["info"]}
NOMBRE_GRAVEDAD = {"alta": "Grave", "media": "A tener en cuenta", "baja": "Menor"}


def _que_hace() -> None:
    st.markdown(
        "La pregunta principal es: **¿qué impacto agronómico tiene cada variable "
        "climática sobre los kg/ha, los frutos y el peso del fruto?** Con la campaña 2025 "
        "el tablero cuantifica asociaciones y aporte predictivo; todavía no identifica "
        "un efecto causal por variable."
    )
    izq, der = st.columns(2)
    with izq.container(border=True):
        st.markdown(f"**{ICONO['ok']} Lo que sí responde**")
        st.markdown(
            "- Qué variables acompañan a las semanas de mayor rendimiento\n"
            "- Cuánto de esa relación se confunde con el calendario\n"
            "- Qué aporta cada variable o grupo a un modelo fuera de muestra\n"
            "- De dónde sale el número de una celda concreta\n"
            "- Qué tan confiable es cada cifra, y con qué tamaño de muestra"
        )
    with der.container(border=True):
        st.markdown(f"**{ICONO['error']} Lo que NO responde**")
        st.markdown(
            "- Cuántos kilos se van a cosechar la semana que viene\n"
            "- Si subir el riego aumentaría el rendimiento\n"
            "- Qué variable **causa** qué — son datos observacionales de una campaña\n"
            "- El efecto por fase fenológica observada — M_Poda aporta un reloj proxy, "
            "pero todavía no trae la fase fenológica medida"
        )


def _estado_analitico() -> None:
    st.subheader("Qué está medido hoy")
    st.dataframe(
        {
            "Resultado": ["Asociación", "Aporte predictivo", "Efecto agronómico"],
            "Pregunta": [
                "¿Qué se mueve junto con el resultado?",
                "¿Qué mejora un modelo fuera de muestra?",
                "¿Cuánto cambiaría el resultado al intervenir la exposición?",
            ],
            "Estado": ["Sí", "Sí", "Todavía no"],
            "Dónde verlo": [
                "Impacto agronómico",
                "Qué explica el R²",
                "Marco metodológico y referencias",
            ],
        },
        width="stretch",
        hide_index=True,
    )
    st.warning(
        "La evidencia actual indica que la asociación climática está confundida con el "
        "calendario. M_Poda permite controlarlo con días desde poda, pero como la fecha "
        "original está a nivel de lote y se resume al módulo, el control todavía es proxy. "
        "Eso no dice que el clima no importe: dice qué parte queda identificada con estos datos.",
        icon=ICONO["aviso"],
    )


def _hallazgo(h: Hallazgo) -> None:
    with st.container(border=True):
        c1, c2 = st.columns([5, 1])
        c1.markdown(f"**{COLOR_GRAVEDAD[h.gravedad]} {h.titulo}**")
        c2.caption(NOMBRE_GRAVEDAD[h.gravedad])
        st.markdown(h.detalle)
        st.caption(f"**Efecto sobre el análisis:** {h.efecto}")


def calidad(panel: Panel) -> None:
    st.subheader("Calidad de los datos")
    graves = panel.graves()
    if graves:
        st.error(
            f"**{len(graves)} problema(s) grave(s) detectado(s) automáticamente al leer el "
            "archivo.** No impiden el análisis, pero cambian cómo hay que leer los "
            "resultados. Están desplegados abajo.",
            icon=ICONO["error"],
        )
    else:
        st.success("No se detectaron problemas graves en el archivo.", icon=ICONO["ok"])

    orden = {"alta": 0, "media": 1, "baja": 2}
    for h in sorted(panel.hallazgos, key=lambda x: orden[x.gravedad]):
        _hallazgo(h)


def _granularidad(panel: Panel) -> None:
    st.subheader("A qué grano se mide cada variable")
    ef = sv.tamano_efectivo(panel.tabla)

    st.markdown(
        f"Las hojas de clima —**Temp Max-Min**, **Rad y ET** y **DPV**— traen "
        f"**un valor por semana**, no por módulo: el de la semana 1 se aplica a los "
        f"{panel.n_modulos} módulos de la semana 1, el de la 2 a los de la 2, y así."
    )
    st.dataframe(
        {
            "Variable": ["Rendimiento (kg/ha)", "Riego (L/planta)", "Temp. máx / mín",
                         "Amplitud térmica", "Radiación y ETo", "DPV"],
            "Se mide por": ["módulo × semana", "módulo × semana", "semana", "semana",
                            "semana", "semana"],
            "¿Distingue módulos?": ["sí", "sí", "no", "no", "no", "no"],
            "Valores distintos": [len(panel.tabla), len(panel.tabla),
                                  ef.n_semanas, ef.n_semanas, ef.n_semanas, ef.n_semanas],
        },
        width="stretch", hide_index=True,
    )

    izq, der = st.columns([3, 2])
    with izq:
        st.info(
            "**¿Es un problema del dato?** No. Dentro de un mismo fundo la temperatura y "
            "el déficit de presión de vapor no cambian de forma apreciable de un módulo al "
            "de al lado: medirlos por módulo daría el mismo número repetido. La estructura "
            "**representa bien la realidad física**.\n\n"
            "**¿Tiene consecuencias?** Dos, y ambas importan:",
            icon=ICONO["info"],
        )
        st.markdown(
            f"1. **El tamaño de muestra real es {ef.n_semanas}, no {ef.n_celdas}.** Cada "
            f"valor de clima se repite {ef.n_celdas / ef.n_semanas:.1f} veces en el panel. "
            f"Un intervalo de confianza calculado sobre las celdas saldría "
            f"**{ef.factor_inflacion:.1f} veces más estrecho** de lo correcto. Todas las "
            "cifras de la sección *Impacto agronómico* usan el n correcto.\n"
            f"2. **Ninguna variable climática puede explicar las diferencias entre módulos "
            "de una misma semana**, porque vale lo mismo para todos. Eso no es una "
            "limitación del análisis sino aritmética."
        )
    with der:
        tarjetas([("n aparente", entero(ef.n_celdas), "Filas del panel"),
                  ("n efectivo", entero(ef.n_semanas), "Mediciones climáticas distintas")])
        st.metric("Inflación si se usa el n equivocado",
                  f"{ef.factor_inflacion:.1f}×",
                  help="Cuánto más estrechos —y por tanto falsamente seguros— saldrían "
                       "los intervalos de confianza.")

    st.markdown(
        "**¿Convendría enriquecer el dato por módulo?** Para temperatura y DPV, no: no hay "
        "variación espacial que capturar dentro del fundo. Lo que sí falta son variables "
        "que **sí** distingan un módulo de otro — fecha de poda, variedad, edad de planta, "
        "suelo. Ésas son las que podrían explicar el tramo que hoy queda sin explicar."
    )


def render(panel: Panel) -> None:
    tabla = panel.tabla
    tarjetas([
        ("Celdas módulo × semana", entero(len(tabla)),
         "Cada fila es un módulo en una semana concreta."),
        ("Módulos", str(panel.n_modulos), "Con cosecha registrada en 2025."),
        ("Semanas", str(panel.n_semanas), "Semanas del año con al menos una cosecha."),
        ("kg/ha promedio", entero(tabla.KgHa.mean()),
         "Promedio simple sobre las celdas del panel."),
    ])
    explica_simple(
        f"Este tablero mira {panel.n_modulos} campos (módulos) durante {panel.n_semanas} "
        "semanas de cosecha, y trata de entender qué hizo que unas semanas y módulos "
        "dieran más arándanos que otros."
    )
    st.divider()
    _que_hace()
    st.divider()
    _estado_analitico()
    st.divider()
    _granularidad(panel)
    glosario()

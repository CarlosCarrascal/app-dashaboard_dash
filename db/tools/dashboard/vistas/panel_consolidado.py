"""Sección «Datos»: el panel tal como lo leyó el modelo, filtrable y exportable.

Los filtros que se apliquen acá son los que viajan al Excel: lo que se ve es lo que se
descarga, sin sorpresas.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

import servicios as sv
from config import ICONO, etiqueta
from nucleo import Panel
from vistas.comun import entero, glosario

COLUMNAS_VISIBLES = [
    "Fundo", "Modulo", "Semana", "Area", "Kg", "KgHa", "Frutos", "Peso",
    "riego_lt_planta", "riego_m3_ha", "TempMax", "TempMin", "VarDia", "Rad", "ETo", "DPV",
    "poda_fecha", "poda_dispersion_dias", "dias_desde_poda", "Variedad",
    "edad_planta_anos", "gdd_acum_poda_obs",
    "flores_promedio", "flores_dispersion_relativa",
]


def _filtros(tabla: pd.DataFrame) -> pd.DataFrame:
    """Controles de filtrado. Devuelve la tabla ya filtrada."""
    with st.container(border=True):
        st.markdown("**Filtros**")
        c1, c2, c3 = st.columns([2, 2, 3])
        fundos = c1.multiselect("Fundo", sorted(tabla.Fundo.unique()),
                                placeholder="Todos")
        disponibles = tabla[tabla.Fundo.isin(fundos)] if fundos else tabla
        modulos = c2.multiselect("Módulo", sorted(disponibles.celda.unique()),
                                 placeholder="Todos")
        lo, hi = int(tabla.nsem.min()), int(tabla.nsem.max())
        semanas = c3.slider("Semanas", lo, hi, (lo, hi),
                            help="Rango de semanas del año 2025 a incluir.")

        c4, c5 = st.columns(2)
        kg_lo, kg_hi = float(tabla.KgHa.min()), float(tabla.KgHa.max())
        rango_kg = c4.slider("Rendimiento (kg/ha)", kg_lo, kg_hi, (kg_lo, kg_hi),
                             help="Deja fuera las celdas con rendimiento extremo.")
        solo_con_riego = c5.checkbox(
            "Excluir semanas con riego cero", value=False,
            help="Un riego de 0 puede ser una parada real o un dato que no se cargó.",
        )

    d = tabla
    if fundos:
        d = d[d.Fundo.isin(fundos)]
    if modulos:
        d = d[d.celda.isin(modulos)]
    d = d[d.nsem.between(*semanas)]
    d = d[d.KgHa.between(*rango_kg)]
    if solo_con_riego:
        d = d[d.riego_lt_planta > 0]
    return d


def _exportacion(panel: Panel, filtrada: pd.DataFrame, origen: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{ICONO['datos']} Exportar a Excel**")
        st.caption(
            "Un libro con portada, el panel filtrado, la metodología, la calidad de los "
            "datos y las limitaciones — para que se sostenga solo cuando alguien lo abra "
            "sin el tablero delante."
        )
        c1, c2 = st.columns([3, 2])
        bloques = c1.multiselect(
            "Incluir además",
            options=["clima", "modulo"],
            default=["clima", "modulo"],
            format_func=lambda b: {"clima": "Impacto agronómico (incluye frutos/peso)",
                                   "modulo": "Análisis por módulo (2 hojas)"}[b],
            help="Las hojas de contexto —metodología, calidad, limitaciones y glosario— "
                 "van siempre.",
        )
        with c2:
            st.metric("Celdas a exportar", entero(len(filtrada)),
                      delta=f"de {entero(len(panel.tabla))}", delta_color="off")

        if filtrada.empty:
            st.warning("Los filtros no dejan ninguna fila.", icon=ICONO["aviso"])
            return

        fecha = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        libro = sv.construir_informe(
            panel, filtrada, frozenset(bloques), origen, fecha
        )
        st.download_button(
            "Descargar Excel",
            data=libro,
            file_name=f"aquanqa_relacion_clima_rendimiento_{dt.date.today():%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=ICONO["datos"],
            type="primary",
            width="stretch",
        )


@st.fragment
def render(panel: Panel, origen: str = "IA.final.xlsx") -> None:
    filtrada = _filtros(panel.tabla)

    st.caption(
        f"Mostrando **{entero(len(filtrada))}** de {entero(len(panel.tabla))} celdas · "
        f"{filtrada.celda.nunique()} módulos · {filtrada.nsem.nunique()} semanas"
    )
    columnas = [c for c in COLUMNAS_VISIBLES if c in filtrada.columns]
    st.dataframe(
        filtrada[columnas].rename(columns={c: etiqueta(c) for c in columnas}),
        width="stretch", hide_index=True, height=420,
    )

    glosario()
    _exportacion(panel, filtrada, origen)

    st.download_button(
        "Descargar solo la tabla en CSV",
        filtrada[columnas].to_csv(index=False).encode("utf-8-sig"),
        file_name="panel_kgha_2025.csv",
        mime="text/csv",
    )

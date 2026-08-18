"""Página «Datos y calidad».
(= `resumen.calidad` + `panel_consolidado.render`).

El panel completo se muestra con `dash-ag-grid` (tabla virtualizada) en vez del viejo
`dash_table` — pilar C de la arquitectura: cientos de filas se ordenan y filtran en el
navegador sin pedirle nada al servidor. Los filtros de arriba (fundo, módulo, semana,
kg/ha) sí son de servidor porque también acotan lo que se exporta a Excel/CSV — igual que
en el Streamlit, "lo que se ve es lo que se descarga".
"""

from __future__ import annotations

import datetime as dt
import math

import dash
import dash_ag_grid as dag
import pandas as pd
from dash import dcc, html
from dash.exceptions import PreventUpdate
from dash_extensions.enrich import Input, Output, State, callback

from analitica import nucleo
from analitica.config import etiqueta
from components import ui
from servicios.carga import PANEL_STORE

dash.register_page(__name__, path="/datos-calidad", name="Datos y calidad", order=0, grupo="Referencia")

COLUMNAS_VISIBLES = [
    "Fundo", "Modulo", "Semana", "Area", "Kg", "KgHa", "Frutos", "Peso",
    "riego_lt_planta", "riego_m3_ha", "TempMax", "TempMin", "VarDia", "Rad", "ETo", "DPV",
    "poda_fecha", "poda_dispersion_dias", "dias_desde_poda", "Variedad",
    "edad_planta_anos", "gdd_acum_poda_obs",
    "flores_promedio", "flores_dispersion_relativa",
]

_NOMBRE_GRAVEDAD = {"alta": "Grave", "media": "A tener en cuenta", "baja": "Menor"}
_ESTADO_GRAVEDAD = {"alta": "error", "media": "aviso", "baja": "info"}


def layout():
    return html.Div(
        className="space-y-4",
        children=[
            ui.encabezado_pagina(
                "¿Qué tan confiables son los datos que alimentan el análisis?",
                "Revisa el alcance del panel, los problemas detectados al consolidarlo y las "
                "filas concretas que entran en cada lectura.",
            ),
            html.Div(id="calidad-hallazgos", children=ui.esqueleto_seccion("h-40")),
            ui.panel(
                "Filtros del panel consolidado",
                html.Div(
                    className="aq-data-filters grid gap-4 md:grid-cols-2",
                    children=[
                        html.Div([
                            html.Label("Fundo", className=ui.SUBTITULO),
                            dcc.Dropdown(id="f-fundo", multi=True, placeholder="Todos"),
                        ]),
                        html.Div([
                            html.Label("Módulo", className=ui.SUBTITULO),
                            dcc.Dropdown(id="f-modulo", multi=True, placeholder="Todos"),
                        ]),
                        html.Div([
                            html.Label("Semanas", className=ui.SUBTITULO),
                            dcc.RangeSlider(
                                id="f-semanas", step=1, allowCross=False,
                                tooltip={"placement": "bottom"},
                            ),
                        ]),
                        html.Div([
                            html.Label("Rendimiento (kg/ha)", className=ui.SUBTITULO),
                            dcc.RangeSlider(
                                id="f-kgha", step=1, allowCross=False,
                                tooltip={"placement": "bottom"},
                            ),
                        ]),
                        html.Div(
                            className="md:col-span-2",
                            children=dcc.Checklist(
                                id="f-sin-riego",
                                options=[{"label": " Excluir semanas con riego cero", "value": "on"}],
                                value=[],
                                className="text-sm text-slate-600",
                            ),
                        ),
                    ],
                ),
                ayuda="Filtra la tabla para comprobar qué filas sustentan cada resultado y qué se exportará.",
            ),
            html.Div(
                className="space-y-3",
                children=[
                    html.Div(id="panel-resumen-texto", className="text-xs text-slate-500"),
                    html.Div(
                        className="overflow-hidden rounded-xl border border-stone-200/80 bg-white",
                        children=dag.AgGrid(
                            id="panel-grid",
                            columnDefs=[],
                            rowData=[],
                            defaultColDef={"sortable": True, "filter": True, "resizable": True},
                            dashGridOptions={"pagination": True, "paginationPageSize": 20},
                            style={"height": "480px"},
                            className="ag-theme-alpine",
                        ),
                    ),
                ],
            ),
            ui.panel(
                "Glosario del panel",
                ui.glosario(plano=True),
                plegable=True,
                abierto=False,
                ayuda="Definiciones de las variables que aparecen en la tabla y en los análisis.",
            ),
            ui.panel(
                "Exportar el análisis",
                ui.parrafo(
                    "Descarga el panel filtrado junto con la metodología, la calidad de los datos "
                    "y, si lo seleccionas, los análisis de impacto y por módulo.",
                ),
                html.Label("Bloques adicionales", className=ui.SUBTITULO),
                dcc.Dropdown(
                    id="f-bloques",
                    multi=True,
                    options=[
                        {"label": "Impacto agronómico (incluye frutos/peso)", "value": "clima"},
                        {"label": "Análisis por módulo (2 hojas)", "value": "modulo"},
                    ],
                    value=["clima", "modulo"],
                    className="mt-1.5",
                ),
                html.Div(
                    className="flex flex-wrap gap-3",
                    children=[
                        html.Button(
                            "Descargar Excel", id="btn-excel",
                            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700",
                        ),
                        html.Button(
                            "Descargar solo la tabla en CSV", id="btn-csv",
                            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50",
                        ),
                    ],
                ),
                dcc.Download(id="descarga-excel"),
                dcc.Download(id="descarga-csv"),
            ),
        ],
    )


def _filtrar(tabla: pd.DataFrame, fundos, modulos, semanas, kgha, excluir_riego) -> pd.DataFrame:
    d = tabla
    if fundos:
        d = d[d.Fundo.isin(fundos)]
    if modulos:
        d = d[d.celda.isin(modulos)]
    if semanas:
        d = d[d.nsem.between(*semanas)]
    if kgha:
        d = d[d.KgHa.between(*kgha)]
    if excluir_riego:
        d = d[d.riego_lt_planta > 0]
    return d


def _resumen_calidad(panel) -> html.Div:
    tabla = panel.tabla
    return ui.fila_kpi([
        ui.kpi(
            "Celdas observadas",
            str(len(tabla)),
            nota="Filas módulo × semana consolidadas desde las fuentes.",
            serie=tabla.groupby("nsem").size().tolist(),
        ),
        ui.kpi(
            "Módulos",
            str(tabla.celda.nunique()),
            nota="Unidades que aparecen en el panel consolidado.",
        ),
        ui.kpi(
            "Semanas",
            str(tabla.nsem.nunique()),
            nota="Semanas con al menos una fila observada.",
        ),
        ui.kpi(
            "Hallazgos de calidad",
            str(len(panel.hallazgos)),
            nota=f"{len(panel.graves())} de gravedad alta; revisar antes de interpretar.",
        ),
    ])


def _respuesta_calidad(panel) -> html.Div:
    graves = panel.graves()
    if graves:
        estado = "error"
        mensaje = (
            f"**El panel se puede consultar, pero tiene {len(graves)} problema(s) grave(s).** "
            "Los resultados deben leerse junto con los hallazgos y los filtros de cobertura; "
            "la tabla no garantiza que todas las variables tengan la misma calidad."
        )
    elif panel.hallazgos:
        estado = "aviso"
        mensaje = (
            f"**El panel está disponible con {len(panel.hallazgos)} advertencia(s).** "
            "La cobertura es suficiente para explorar, pero cada análisis debe conservar "
            "sus límites de medición y agregación."
        )
    else:
        estado = "ok"
        mensaje = (
            "**No se detectaron problemas al consolidar el panel.** La tabla queda lista "
            "para filtrar y exportar; la calidad estadística de cada modelo se revisa en "
            "sus módulos específicos."
        )
    return ui.panel(
        "Respuesta corta",
        ui.semaforo(estado, mensaje),
        html.Div(
            className="grid gap-4",
            children=[
                html.Div([
                    html.Div("Este análisis responde", className="text-sm font-semibold text-slate-700"),
                    html.P(
                        "Qué observaciones entraron al panel y qué problemas de origen, "
                        "agregación o cobertura pueden afectar su lectura.",
                        className="mt-1.5 text-sm leading-relaxed text-slate-600",
                    ),
                ]),
                html.Div([
                    html.Div("Cómo ayuda al modelo", className="text-sm font-semibold text-slate-700"),
                    html.P(
                        "Fija el alcance de los datos antes de comparar variables o entrenar "
                        "un predictor. Un hallazgo de calidad no es una señal agronómica.",
                        className="mt-1.5 text-sm leading-relaxed text-slate-600",
                    ),
                ]),
            ],
        ),
        ayuda="Conclusión de calidad y relación con el resto del dashboard.",
    )


def _panel_hallazgos(panel) -> html.Div:
    orden = {"alta": 0, "media": 1, "baja": 2}
    if not panel.hallazgos:
        return ui.panel(
            "Hallazgos detectados al cargar el archivo",
            ui.semaforo("ok", "No se detectaron hallazgos automáticos en el panel."),
            ayuda="Revisión automática de la carga y consolidación de las fuentes.",
        )

    filas = []
    for h in sorted(panel.hallazgos, key=lambda x: orden[x.gravedad]):
        filas.append(
            html.Div(
                className="py-3 first:pt-0 last:pb-0",
                children=[
                    html.Div(
                        className="flex flex-wrap items-center justify-between gap-2",
                        children=[
                            html.Div(h.titulo, className="text-sm font-semibold text-slate-700"),
                            html.Span(
                                _NOMBRE_GRAVEDAD[h.gravedad],
                                className="text-xs font-medium text-slate-500",
                            ),
                        ],
                    ),
                    ui.parrafo(h.detalle),
                    html.P(
                        f"Efecto sobre el análisis: {h.efecto}",
                        className="mt-1 text-xs text-slate-500",
                    ),
                ],
            )
        )
    return ui.panel(
        "Hallazgos detectados al cargar el archivo",
        html.Div(filas, className="divide-y divide-stone-200/80"),
        plegable=True,
        abierto=False,
        ayuda="Problemas y advertencias encontrados al construir el panel consolidado.",
    )


@callback(
    Output("calidad-hallazgos", "children"),
    Output("f-fundo", "options"),
    Output("f-modulo", "options"),
    Output("f-semanas", "min"), Output("f-semanas", "max"), Output("f-semanas", "value"),
    Output("f-semanas", "marks"),
    Output("f-kgha", "min"), Output("f-kgha", "max"), Output("f-kgha", "value"),
    Output("f-kgha", "marks"),
    Input(PANEL_STORE, "data"),
)
def _inicializar(panel):
    if panel is None:
        return (
            ui.esqueleto_seccion("h-40"), [], [],
            0, 1, [0, 1], {},
            0.0, 1.0, [0.0, 1.0], {},
        )

    graves = panel.graves()
    bloques = [_resumen_calidad(panel), _respuesta_calidad(panel), _panel_hallazgos(panel)]

    tabla = panel.tabla
    fundos = [{"label": f, "value": f} for f in sorted(tabla.Fundo.unique())]
    modulos = [{"label": m, "value": m} for m in sorted(tabla.celda.unique())]
    lo_s, hi_s = int(tabla.nsem.min()), int(tabla.nsem.max())
    lo_k = math.floor(float(tabla.KgHa.min()))
    hi_k = math.ceil(float(tabla.KgHa.max()))
    paso_s = max(1, (hi_s - lo_s) // 8)
    marcas_s = {s: str(s) for s in range(lo_s, hi_s + 1, paso_s)}
    marcas_s[hi_s] = str(hi_s)
    paso_k = max(1, round((hi_k - lo_k) / 4))
    marcas_k = {k: ui.miles(k) for k in range(lo_k, hi_k + 1, paso_k)}
    marcas_k[hi_k] = ui.miles(hi_k)
    return (
        html.Div(bloques, className="space-y-3"),
        fundos, modulos,
        lo_s, hi_s, [lo_s, hi_s], marcas_s,
        lo_k, hi_k, [lo_k, hi_k], marcas_k,
    )


@callback(
    Output("panel-grid", "columnDefs"),
    Output("panel-grid", "rowData"),
    Output("panel-resumen-texto", "children"),
    Input(PANEL_STORE, "data"),
    Input("f-fundo", "value"), Input("f-modulo", "value"),
    Input("f-semanas", "value"), Input("f-kgha", "value"), Input("f-sin-riego", "value"),
)
def _actualizar_grid(panel, fundos, modulos, semanas, kgha, sin_riego):
    if panel is None:
        return [], [], ""
    filtrada = _filtrar(panel.tabla, fundos, modulos, semanas, kgha, "on" in (sin_riego or []))
    columnas = [c for c in COLUMNAS_VISIBLES if c in filtrada.columns]
    column_defs = [{"field": c, "headerName": etiqueta(c)} for c in columnas]
    row_data = filtrada[columnas].to_dict("records")
    resumen = (
        f"Mostrando {len(filtrada):,}".replace(",", ".") + f" de {len(panel.tabla):,}".replace(",", ".")
        + f" celdas · {filtrada.celda.nunique()} módulos · {filtrada.nsem.nunique()} semanas"
    )
    return column_defs, row_data, resumen


@callback(
    Output("descarga-excel", "data"),
    Input("btn-excel", "n_clicks"),
    State(PANEL_STORE, "data"),
    State("f-fundo", "value"), State("f-modulo", "value"),
    State("f-semanas", "value"), State("f-kgha", "value"), State("f-sin-riego", "value"),
    State("f-bloques", "value"),
    prevent_initial_call=True,
)
def _descargar_excel(n, panel, fundos, modulos, semanas, kgha, sin_riego, bloques):
    if not n or panel is None:
        raise PreventUpdate
    filtrada = _filtrar(panel.tabla, fundos, modulos, semanas, kgha, "on" in (sin_riego or []))
    if filtrada.empty:
        raise PreventUpdate
    fecha = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    libro = nucleo.construir_informe(panel, filtrada, frozenset(bloques or []), "IA.final.xlsx", fecha)
    nombre = f"aquanqa_relacion_clima_rendimiento_{dt.date.today():%Y%m%d}.xlsx"
    return dcc.send_bytes(libro, nombre)


@callback(
    Output("descarga-csv", "data"),
    Input("btn-csv", "n_clicks"),
    State(PANEL_STORE, "data"),
    State("f-fundo", "value"), State("f-modulo", "value"),
    State("f-semanas", "value"), State("f-kgha", "value"), State("f-sin-riego", "value"),
    prevent_initial_call=True,
)
def _descargar_csv(n, panel, fundos, modulos, semanas, kgha, sin_riego):
    if not n or panel is None:
        raise PreventUpdate
    filtrada = _filtrar(panel.tabla, fundos, modulos, semanas, kgha, "on" in (sin_riego or []))
    columnas = [c for c in COLUMNAS_VISIBLES if c in filtrada.columns]
    return dcc.send_data_frame(filtrada[columnas].to_csv, "panel_kgha_2025.csv", index=False)

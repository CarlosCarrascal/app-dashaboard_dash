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
        className="space-y-6",
        children=[
            html.Div(id="calidad-hallazgos", children=ui.esqueleto_seccion("h-40")),
            html.Hr(className="border-slate-200"),
            ui.titulo_seccion("Panel consolidado y exportación"),
            html.Div(
                className="grid grid-cols-2 gap-3 rounded-lg border border-slate-200 bg-white p-4 md:grid-cols-4",
                children=[
                    html.Div([
                        html.Label("Fundo", className="text-xs font-medium text-slate-500"),
                        dcc.Dropdown(id="f-fundo", multi=True, placeholder="Todos"),
                    ]),
                    html.Div([
                        html.Label("Módulo", className="text-xs font-medium text-slate-500"),
                        dcc.Dropdown(id="f-modulo", multi=True, placeholder="Todos"),
                    ]),
                    html.Div(
                        className="col-span-2",
                        children=[
                            html.Label("Semanas", className="text-xs font-medium text-slate-500"),
                            dcc.RangeSlider(id="f-semanas", tooltip={"placement": "bottom"}),
                        ],
                    ),
                    html.Div(
                        className="col-span-2",
                        children=[
                            html.Label("Rendimiento (kg/ha)", className="text-xs font-medium text-slate-500"),
                            dcc.RangeSlider(id="f-kgha", tooltip={"placement": "bottom"}),
                        ],
                    ),
                    html.Div(
                        className="col-span-2 flex items-end",
                        children=dcc.Checklist(
                            id="f-sin-riego",
                            options=[{"label": " Excluir semanas con riego cero", "value": "on"}],
                            value=[],
                            className="text-sm",
                        ),
                    ),
                ],
            ),
            html.Div(id="panel-resumen-texto", className="text-xs text-slate-500"),
            dag.AgGrid(
                id="panel-grid",
                columnDefs=[],
                rowData=[],
                defaultColDef={"sortable": True, "filter": True, "resizable": True},
                dashGridOptions={"pagination": True, "paginationPageSize": 20},
                style={"height": "480px"},
                className="ag-theme-alpine",
            ),
            ui.glosario(),
            html.Div(
                className="rounded-lg border border-slate-200 bg-white p-4",
                children=[
                    html.P("Exportar a Excel", className="mb-1 font-semibold"),
                    ui.parrafo(
                        "Un libro con portada, el panel filtrado, la metodología, la "
                        "calidad de los datos y las limitaciones."
                    ),
                    dcc.Dropdown(
                        id="f-bloques",
                        multi=True,
                        options=[
                            {"label": "Impacto agronómico (incluye frutos/peso)", "value": "clima"},
                            {"label": "Análisis por módulo (2 hojas)", "value": "modulo"},
                        ],
                        value=["clima", "modulo"],
                        className="mb-3",
                    ),
                    html.Div(
                        className="flex gap-3",
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
                ],
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


@callback(
    Output("calidad-hallazgos", "children"),
    Output("f-fundo", "options"),
    Output("f-modulo", "options"),
    Output("f-semanas", "min"), Output("f-semanas", "max"), Output("f-semanas", "value"),
    Output("f-kgha", "min"), Output("f-kgha", "max"), Output("f-kgha", "value"),
    Input(PANEL_STORE, "data"),
)
def _inicializar(panel):
    if panel is None:
        return ui.esqueleto_seccion("h-40"), [], [], 0, 1, [0, 1], 0.0, 1.0, [0.0, 1.0]

    graves = panel.graves()
    orden = {"alta": 0, "media": 1, "baja": 2}
    bloques = [
        ui.semaforo(
            "error" if graves else "ok",
            f"**{len(graves)} problema(s) grave(s) detectado(s) automáticamente al leer "
            "el archivo.** No impiden el análisis, pero cambian cómo hay que leer los "
            "resultados." if graves else "No se detectaron problemas graves en el archivo.",
        ),
    ]
    for h in sorted(panel.hallazgos, key=lambda x: orden[x.gravedad]):
        bloques.append(
            ui.caja(
                html.Div(
                    className="mb-1 flex items-center justify-between",
                    children=[
                        html.Span(h.titulo, className="font-semibold"),
                        html.Span(_NOMBRE_GRAVEDAD[h.gravedad], className="text-xs text-slate-500"),
                    ],
                ),
                ui.parrafo(h.detalle),
                html.P(f"Efecto sobre el análisis: {h.efecto}", className="mt-1 text-xs text-slate-500"),
            )
        )

    tabla = panel.tabla
    fundos = [{"label": f, "value": f} for f in sorted(tabla.Fundo.unique())]
    modulos = [{"label": m, "value": m} for m in sorted(tabla.celda.unique())]
    lo_s, hi_s = int(tabla.nsem.min()), int(tabla.nsem.max())
    lo_k, hi_k = float(tabla.KgHa.min()), float(tabla.KgHa.max())
    return (
        html.Div(bloques, className="space-y-3"),
        fundos, modulos,
        lo_s, hi_s, [lo_s, hi_s],
        lo_k, hi_k, [lo_k, hi_k],
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

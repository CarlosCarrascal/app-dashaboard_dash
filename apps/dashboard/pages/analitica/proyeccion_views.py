"""Composición visual de Proyección, orientada a la operación diaria."""

from __future__ import annotations

import dash_ag_grid as dag
import pandas as pd
from dash import dcc, html

from components import ui

from .proyeccion_charts import (
    figura_matriz_six,
    figura_nowcast_cierre,
    historico_y_desviacion,
)
from .proyeccion_domain import (
    FUNDOS_OPERATIVOS,
    HORIZONTE_CAMPANIA,
    HORIZONTE_SEMANAS,
    columnas_grid,
    enriquecer,
    matriz_six,
    plan_semanal,
    resumen_fundos,
    seleccionar_modelo_operativo,
)


def _kg(valor: object) -> str:
    numero = pd.to_numeric(pd.Series([valor]), errors="coerce").iloc[0]
    return "—" if pd.isna(numero) else f"{numero:,.0f}".replace(",", ".")


def _porcentaje(valor: object) -> str:
    numero = pd.to_numeric(pd.Series([valor]), errors="coerce").iloc[0]
    return "Pendiente" if pd.isna(numero) else f"{100 * numero:.1f} %"


def _rango_semana_compacto(inicio: object, fin: object) -> str:
    """Presenta semanas sin ruido numérico, por ejemplo: 31 ago — 6 sep."""
    meses = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
    fecha_inicio = pd.to_datetime(inicio, errors="coerce")
    fecha_fin = pd.to_datetime(fin, errors="coerce")
    if pd.isna(fecha_inicio) or pd.isna(fecha_fin):
        return "Semana sin fecha"
    if fecha_inicio.month == fecha_fin.month:
        return f"{fecha_inicio.day}–{fecha_fin.day} {meses[fecha_fin.month - 1]}"
    return (
        f"{fecha_inicio.day} {meses[fecha_inicio.month - 1]}"
        f" — {fecha_fin.day} {meses[fecha_fin.month - 1]}"
    )


def contexto_corrida(tabla: pd.DataFrame) -> html.Div:
    if tabla.empty:
        return html.Div("Sin corrida operativa persistida", className="aq-proy-context-error")
    emision = pd.to_datetime(tabla.fecha_emision, errors="coerce").max()
    generada = pd.to_datetime(tabla.get("generado_en"), errors="coerce").max()
    campania = ", ".join(sorted(tabla.campania.dropna().astype(str).unique())) or "—"
    piezas = [
        html.Span(campania),
        html.Span("·"),
        html.Span(f"Emisión {emision:%d/%m/%Y}" if pd.notna(emision) else "Emisión sin fecha"),
    ]
    if pd.notna(generada):
        piezas.extend([html.Span("·"), html.Span(f"Actualizado {generada:%d/%m %H:%M}")])
    return html.Div(piezas, className="aq-proy-context")


def resumen_principal(tabla: pd.DataFrame) -> html.Div:
    plan = plan_semanal(tabla)
    if plan.empty:
        return html.Div(
            [
                html.Strong("Sin proyección disponible"),
                html.Span("La corrida no contiene semanas para este filtro."),
            ],
            className="aq-proy-empty",
        )
    proxima = plan.iloc[0]
    pico = plan.loc[plan.total_kg.idxmax()]
    n_fundos = int(tabla.fundo.nunique())
    etiqueta_fundo = "fundo" if n_fundos == 1 else "fundos"
    periodo_proxima = _rango_semana_compacto(proxima.semana_inicio, proxima.semana_cierre)
    periodo_pico = _rango_semana_compacto(pico.semana_inicio, pico.semana_cierre)
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Semana próxima", className="aq-proy-eyebrow"),
                    html.Div(
                        [html.Strong(_kg(proxima.total_kg)), html.Small("kg")],
                        className="aq-proy-primary-value",
                    ),
                    html.P(periodo_proxima, className="aq-proy-period"),
                ],
                className="aq-proy-primary",
            ),
            html.Div(
                [
                    html.Span("Total · 6 semanas", className="aq-proy-stat-label"),
                    html.Strong(f"{_kg(plan.head(6).total_kg.sum())} kg"),
                    html.Small("Volumen planificado"),
                ],
                className="aq-proy-stat",
            ),
            html.Div(
                [
                    html.Span("Mayor carga", className="aq-proy-stat-label"),
                    html.Strong(periodo_pico),
                    html.Small(f"{_kg(pico.total_kg)} kg"),
                ],
                className="aq-proy-stat",
            ),
            html.Div(
                [
                    html.Span("Cobertura del cálculo", className="aq-proy-stat-label"),
                    html.Strong(f"{tabla.lote_id.nunique():,.0f}".replace(",", ".") + " lotes"),
                    html.Small(f"{n_fundos} {etiqueta_fundo} · parámetros automáticos"),
                ],
                className="aq-proy-stat",
            ),
        ],
        className="aq-proy-summary",
    )


def tabla_fundos(tabla: pd.DataFrame) -> html.Div:
    resumen = resumen_fundos(tabla)
    tarjetas = []
    for fila in resumen.itertuples(index=False):
        disponible = fila.estado == "Disponible"
        tarjetas.append(
            html.Article(
                [
                    html.Div(
                        [
                            html.Span(
                                className=(f"aq-proy-fund-dot aq-proy-fund-{fila.fundo.casefold()}")
                            ),
                            html.Strong(fila.fundo),
                            html.Small(fila.estado),
                        ],
                        className="aq-proy-fund-head",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Próxima"),
                                    html.Strong(
                                        f"{_kg(fila.proxima_semana_kg)} kg" if disponible else "—"
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Span("6 semanas"),
                                    html.Strong(
                                        f"{_kg(fila.total_periodo_kg)} kg" if disponible else "—"
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Span("Pico"),
                                    html.Strong(
                                        fila.semana_pico.strftime("%d/%m")
                                        if disponible and pd.notna(fila.semana_pico)
                                        else "—"
                                    ),
                                ]
                            ),
                        ],
                        className="aq-proy-fund-metrics",
                    ),
                ],
                className="aq-proy-fund-card" + ("" if disponible else " is-missing"),
            )
        )
    return html.Div(tarjetas, className="aq-proy-fund-grid")


def tabla_plan(tabla: pd.DataFrame) -> html.Div:
    plan = plan_semanal(tabla)
    if plan.empty:
        return html.Div("No hay semanas disponibles.", className="aq-proy-empty")
    vista = pd.DataFrame(
        {
            "Semana": plan.semana_iso.astype(str),
            "Período": plan.rango_semana,
            "Arena": plan.Arena.map(_kg),
            "Ayllu": plan.Ayllu.map(_kg),
            "Kawsay": plan.Kawsay.map(_kg),
            "Quri": plan.Quri.map(_kg),
            "Total kg": plan.total_kg.map(_kg),
        }
    )
    return ui.tabla_desde_df(vista, plano=True)


def panel_nowcast_cierre(estado: dict) -> html.Div:
    """Vista separada para el cierre del miércoles, sin confundirlo con el plan."""
    tabla = estado.get("nowcast_cierre", pd.DataFrame())
    if not isinstance(tabla, pd.DataFrame) or tabla.empty:
        return html.Div(
            [
                html.Strong("Cierre semanal todavía no disponible"),
                html.Span("Solo se muestra una release histórica aprobada y reproducible."),
            ],
            className="aq-proy-empty",
        )
    empresa = tabla.loc[tabla.fundo.astype(str).eq("Empresa")].copy()
    if empresa.empty:
        return html.Div(
            "La release no contiene el total reconciliado de empresa.",
            className="aq-proy-empty",
        )
    empresa["semana_inicio"] = pd.to_datetime(empresa.semana_inicio, errors="coerce")
    for column in (
        "p50_kg",
        "real_kg",
        "macro_kg",
        "r09_presemana_kg",
        "r09_misma_semana_kg",
    ):
        empresa[column] = pd.to_numeric(empresa.get(column), errors="coerce")
    empresa = empresa.dropna(subset=["semana_inicio", "p50_kg", "real_kg"]).sort_values(
        "semana_inicio"
    )
    if empresa.empty:
        return html.Div("No hay semanas evaluadas.", className="aq-proy-empty")

    def wape(column: str) -> float | None:
        paired = empresa.loc[empresa[column].notna()]
        denominator = float(paired.real_kg.abs().sum())
        if paired.empty or denominator <= 0:
            return None
        return float((paired[column] - paired.real_kg).abs().sum() / denominator)

    latest = empresa.iloc[-1]
    error_kg = float(latest.p50_kg - latest.real_kg)
    error_pct = error_kg / float(latest.real_kg) if latest.real_kg else float("nan")
    periodo = _rango_semana_compacto(
        latest.semana_inicio, latest.semana_inicio + pd.Timedelta(days=6)
    )
    wape_nowcast = wape("p50_kg")
    wape_macro = wape("macro_kg")
    wape_r09_same = wape("r09_misma_semana_kg")
    wape_r09_pre = wape("r09_presemana_kg")

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Último cierre evaluado"),
                            html.Strong(f"{_kg(latest.p50_kg)} kg"),
                            html.Small(f"{periodo} · real {_kg(latest.real_kg)} kg"),
                        ]
                    ),
                    html.Div(
                        [
                            html.Span("Error del último cierre"),
                            html.Strong(f"{error_kg:+,.0f} kg".replace(",", ".")),
                            html.Small("—" if pd.isna(error_pct) else f"{100 * error_pct:+.1f} %"),
                        ]
                    ),
                    html.Div(
                        [
                            html.Span("WAPE histórico"),
                            html.Strong(
                                "—" if wape_nowcast is None else f"{100 * wape_nowcast:.1f} %"
                            ),
                            html.Small(f"{len(empresa)} semanas cerradas"),
                        ]
                    ),
                    html.Div(
                        [
                            html.Span("Estado"),
                            html.Strong("Mejora frente a Macro"),
                            html.Small("Equivalente a R09 intra-semanal; no superior"),
                        ]
                    ),
                ],
                className="aq-nowcast-summary",
            ),
            html.Div(
                [
                    html.Strong("Qué compara"),
                    html.Span(
                        "Estimación emitida el miércoles con los kilos reales de lunes y martes. "
                        "Sirve para cerrar la semana; no reemplaza el plan emitido "
                        "antes de iniciarla."
                    ),
                ],
                className="aq-nowcast-explainer",
            ),
            dcc.Graph(
                figure=figura_nowcast_cierre(tabla),
                config={"displayModeBar": False, "responsive": True},
                style={"height": "470px"},
            ),
            html.Div(
                [
                    html.Span(
                        f"Macro {100 * wape_macro:.1f} %" if wape_macro is not None else "Macro —"
                    ),
                    html.Span(
                        f"R09 previo {100 * wape_r09_pre:.1f} %"
                        if wape_r09_pre is not None
                        else "R09 previo —"
                    ),
                    html.Span(
                        f"R09 ajustado en la semana {100 * wape_r09_same:.1f} %"
                        if wape_r09_same is not None
                        else "R09 ajustado —"
                    ),
                ],
                className="aq-nowcast-benchmarks",
            ),
        ],
        className="aq-nowcast-panel",
    )


def comparacion_historica(estado: dict) -> html.Div:
    del estado
    return html.Div(
        [
            html.Div(
                [
                    html.Label(
                        [
                            html.Span("Campaña"),
                            dcc.Dropdown(
                                id="proy-hist-campania",
                                options=[],
                                value=None,
                                multi=False,
                                clearable=False,
                                placeholder="Selecciona una campaña",
                            ),
                        ]
                    ),
                    html.Label(
                        [
                            html.Span("Serie a comparar"),
                            dcc.Dropdown(
                                id="proy-hist-serie",
                                options=[],
                                value=None,
                                clearable=False,
                                placeholder="Cargando series disponibles",
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Span("Agrupar por"),
                            dcc.RadioItems(
                                id="proy-hist-grano",
                                options=[
                                    {"label": "Semana", "value": "semana"},
                                    {"label": "Mes", "value": "mes"},
                                    {"label": "Campaña", "value": "campania"},
                                ],
                                value="mes",
                                inline=True,
                                className="aq-proy-segmented aq-proy-hist-segmented",
                            ),
                        ]
                    ),
                    html.Label(
                        [
                            html.Span("Ventana semanal"),
                            dcc.Dropdown(
                                id="proy-hist-ventana",
                                options=[
                                    {"label": "Últimas 12 semanas", "value": "12"},
                                    {"label": "Últimas 26 semanas", "value": "26"},
                                    {"label": "Todo el histórico", "value": "todo"},
                                ],
                                value="12",
                                clearable=False,
                                searchable=False,
                            ),
                        ],
                        id="proy-hist-ventana-wrap",
                        style={"display": "none"},
                    ),
                ],
                className="aq-proy-history-toolbar",
            ),
            html.Div(id="proy-hist-resumen", className="aq-proy-history-summary"),
            html.P(
                "Semana y Mes se evalúan dentro de una campaña. Campaña compara los "
                "totales entre temporadas sin mezclarlas por año calendario. El WAPE "
                "operativo incluye emisiones faltantes; el condicionado solo mide filas "
                "emitidas. MASE y RMSSE comparan contra repetir la semana anterior.",
                className="aq-proy-section-note aq-proy-history-note",
            ),
            dcc.Loading(
                dcc.Graph(
                    id="proy-hist-grafico",
                    figure=historico_y_desviacion(pd.DataFrame(), nombre_serie="Proyección"),
                    config={"displayModeBar": False, "responsive": True},
                ),
                type="dot",
            ),
            html.Div(id="proy-hist-estado", className="aq-proy-history-status"),
        ],
        className="aq-proy-secondary-content",
    )


def tabla_six(matriz: pd.DataFrame) -> html.Div:
    if matriz.empty:
        return html.Div("No hay emisiones históricas suficientes.", className="aq-proy-empty")
    vista = matriz.tail(10).copy()
    vista.index = [f"Emisión {pd.Timestamp(x):%d/%m}" for x in vista.index]
    vista.columns = [f"S{pd.Timestamp(x).isocalendar().week:02d}" for x in vista.columns]
    vista = vista.map(_kg).reset_index(names="Emisión")
    return ui.tabla_desde_df(vista, plano=True)


def _controles(modelo: pd.DataFrame) -> html.Div:
    fundos = [f for f in FUNDOS_OPERATIVOS if f in set(modelo.get("fundo", pd.Series(dtype=str)))]
    return html.Div(
        [
            html.Label(
                [
                    html.Span("Fundo"),
                    dcc.Dropdown(
                        id="proy-fundo",
                        options=[{"label": f, "value": f} for f in fundos],
                        value=[],
                        multi=True,
                        closeOnSelect=False,
                        searchable=True,
                        placeholder="Todos",
                    ),
                ]
            ),
            html.Label(
                [
                    html.Span("Módulo"),
                    dcc.Dropdown(
                        id="proy-modulo",
                        options=[],
                        value=[],
                        multi=True,
                        closeOnSelect=False,
                        searchable=True,
                        placeholder="Todos",
                    ),
                ]
            ),
            html.Label(
                [
                    html.Span("Lote"),
                    dcc.Dropdown(
                        id="proy-lote",
                        options=[],
                        value=[],
                        multi=True,
                        closeOnSelect=False,
                        searchable=True,
                        placeholder="Todos",
                    ),
                ]
            ),
            html.Label(
                [
                    html.Span("Horizonte"),
                    dcc.Dropdown(
                        id="proy-horizonte",
                        options=[
                            {"label": "6 semanas", "value": HORIZONTE_SEMANAS},
                            {"label": "Campaña completa", "value": HORIZONTE_CAMPANIA},
                        ],
                        value=HORIZONTE_SEMANAS,
                        clearable=False,
                        searchable=False,
                        className="aq-proy-horizon-select",
                    ),
                ]
            ),
            html.Div(
                [
                    dcc.Checklist(
                        id="proy-mostrar-r09",
                        options=[{"label": "Ver R09", "value": "mostrar"}],
                        value=[],
                        className="aq-proy-check",
                    ),
                    dcc.Checklist(
                        id="proy-mostrar-nowcast",
                        options=[
                            {
                                "label": "Nowcast cierre semanal",
                                "value": "mostrar",
                            }
                        ],
                        # El cierre semanal es una lectura distinta del plan. Se deja
                        # disponible como comparación opcional para no mezclarlo con
                        # las seis semanas del modelo operativo al abrir la pantalla.
                        value=[],
                        className="aq-proy-check aq-proy-check-nowcast",
                    ),
                    dcc.Checklist(
                        id="proy-mostrar-hibrido-v2",
                        options=[{"label": "Híbrido ocurrencia v2", "value": "mostrar"}],
                        value=["mostrar"],
                        className="aq-proy-check aq-proy-check-hibrido-v2",
                    ),
                ],
                className="aq-proy-comparisons",
            ),
            html.Button(
                "Limpiar",
                id="proy-limpiar",
                className="aq-proy-clear",
                n_clicks=0,
                title="Restablecer todos los filtros",
            ),
        ],
        className="aq-proy-toolbar",
    )


def layout_view(estado: dict) -> html.Div:
    modelo = enriquecer(seleccionar_modelo_operativo(estado), estado.get("lotes"))
    six = matriz_six(estado.get("replay", pd.DataFrame()))
    return html.Div(
        [
            ui.fuente_oficial(),
            html.Header(
                [
                    html.Div(
                        [
                            html.H1("Plan semanal de cosecha"),
                            html.P("Proyección operativa por fundo, módulo, lote y paña."),
                        ]
                    ),
                    html.Div(id="proy-contexto", children=contexto_corrida(modelo)),
                ],
                className="aq-proy-header",
            ),
            _controles(modelo),
            html.Div(id="proy-resumen-principal", children=resumen_principal(modelo)),
            html.Section(
                [
                    html.Div(
                        [
                            html.H2("Curva semanal de cosecha"),
                            html.P(
                                "La semana en curso compara el avance real con la estimación "
                                "de cierre; las siguientes son planificación."
                            ),
                        ],
                        className="aq-proy-section-head",
                    ),
                    dcc.Graph(
                        id="proy-curva",
                        config={"displayModeBar": False, "responsive": True},
                        style={"height": "480px"},
                    ),
                ],
                className="aq-proy-panel aq-proy-chart-panel",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.H2("Perfil de cosecha por fundo"),
                            html.P(
                                "Cuatro curvas con la misma escala para comparar volumen y forma."
                            ),
                        ],
                        className="aq-proy-section-head",
                    ),
                    dcc.Graph(
                        id="proy-curvas-fundos",
                        config={"displayModeBar": False, "responsive": True},
                        style={"height": "300px"},
                    ),
                ],
                className="aq-proy-panel",
            ),
            dcc.Tabs(
                id="proy-vista-secundaria",
                value="plan",
                className="aq-proy-tabs",
                children=[
                    dcc.Tab(
                        label="Plan semanal",
                        value="plan",
                        children=html.Div(id="proy-plan-semanal", className="aq-proy-tab-body"),
                    ),
                    dcc.Tab(
                        label="Detalle por lote",
                        value="detalle",
                        children=html.Div(
                            [
                                html.Div(id="proy-resumen-tabla", className="aq-proy-grid-meta"),
                                dag.AgGrid(
                                    id="proy-grid",
                                    columnDefs=columnas_grid(),
                                    rowData=[],
                                    defaultColDef={
                                        "sortable": True,
                                        "filter": True,
                                        "resizable": True,
                                    },
                                    dashGridOptions={
                                        "pagination": True,
                                        "paginationPageSize": 25,
                                        "rowBuffer": 10,
                                    },
                                    style={"height": "620px"},
                                    className="ag-theme-alpine",
                                ),
                            ],
                            className="aq-proy-tab-body",
                        ),
                    ),
                    dcc.Tab(
                        label="Cierre semanal",
                        value="nowcast",
                        children=html.Div(
                            children=panel_nowcast_cierre(estado),
                            className="aq-proy-tab-body",
                        ),
                    ),
                    dcc.Tab(
                        label="Histórico y desviación",
                        value="precision",
                        children=html.Div(
                            id="proy-historico",
                            children=comparacion_historica(estado),
                            className="aq-proy-tab-body",
                        ),
                    ),
                    dcc.Tab(
                        label="Matriz SIX",
                        value="six",
                        children=html.Div(
                            [
                                html.P(
                                    "Cada fila es una emisión y cada columna una semana objetivo; "
                                    "permite ver cuánto cambió el plan publicado.",
                                    className="aq-proy-section-note",
                                ),
                                dcc.Graph(
                                    id="proy-six",
                                    figure=figura_matriz_six(six),
                                    config={"displayModeBar": False},
                                    style={"height": "390px"},
                                ),
                                html.Div(id="proy-six-tabla", children=tabla_six(six)),
                            ],
                            className="aq-proy-tab-body",
                        ),
                    ),
                ],
            ),
            html.Div(
                [
                    dcc.Download(id="proy-descarga-excel"),
                    dcc.Download(id="proy-descarga-csv"),
                    html.Button(
                        "Descargar plan Excel",
                        id="proy-btn-excel",
                        className="aq-btn aq-btn-primary",
                    ),
                    html.Button(
                        "Descargar CSV", id="proy-btn-csv", className="aq-btn aq-btn-secondary"
                    ),
                ],
                className="aq-proy-actions",
            ),
        ],
        className="aq-projection-workspace",
    )

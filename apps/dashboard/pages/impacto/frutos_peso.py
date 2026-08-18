"""Página «Frutos y peso».
(incluye `_floracion` y `_desfases_conjunto`) y la lectura integrada de resultados.
_picos_y_clima` / `_peso_y_clima`.

kg/ha no se mide directo: sale de multiplicar frutos por planta por peso del fruto. Esta
página compara clima y riego contra Frutos y Peso por separado (¿el efecto es sobre el
cuajado o sobre el tamaño?), muestra la trayectoria de cada módulo, si la floración
anticipa el cuajado, y qué desfase explica mejor cada uno de los cuatro objetivos.
"""

from __future__ import annotations

import logging

import dash
import plotly.express as px
import plotly.graph_objects as go
from dash import Input as DashInput
from dash import Output as DashOutput
from dash import clientside_callback, dcc, html
from dash_extensions.enrich import Input, Output, callback
from plotly.subplots import make_subplots

from analitica import nucleo
from analitica.config import AZUL, GRIS, ROJO, etiqueta
from components import ui
from servicios.cache_analisis import obtener, precargar
from servicios.carga import PANEL_STORE

_LOGGER = logging.getLogger(__name__)

dash.register_page(__name__, path="/impacto/frutos-peso", name="Frutos y peso", order=3, grupo="Impacto agronómico")

VARIABLES_PRE_PEAK = ["TempMin", "DPV", "Rad", "ETo", "riego_lt_planta", "gdd_semana"]
_COLUMNA_PRE_PEAK = {
    "TempMin": "TempMin 4sem pre-peak", "DPV": "DPV 4sem pre-peak", "Rad": "Rad 4sem pre-peak",
    "ETo": "ETo 4sem pre-peak", "riego_lt_planta": "Riego 4sem pre-peak", "gdd_semana": "GDD 4sem pre-peak",
}


def _sem(panel):
    return obtener(
        panel,
        "fp:semana",
        lambda: nucleo.clima.agregar_por_semana(panel.tabla),
    )


def _tray(panel):
    return obtener(
        panel,
        "fp:trayectorias",
        lambda: nucleo.clima.trayectorias_frutos_peso(panel.tabla),
    )


def _descomp(panel, sem):
    return obtener(
        panel,
        "fp:descomposicion",
        lambda: nucleo.clima.descomponer_frutos_peso(sem),
    )


def _picos(panel):
    return obtener(
        panel,
        "fp:picos",
        lambda: nucleo.clima.resumen_picos_frutos_peso(panel.tabla),
    )


def _rezago(panel, sem):
    return obtener(
        panel,
        "fp:mejor-rezago",
        lambda: nucleo.clima.mejor_rezago_por_variable(sem, panel.tabla),
    )


def _rezagos(panel, sem):
    return obtener(
        panel,
        "fp:rezagos",
        lambda: nucleo.clima.rezagos_todos(sem, panel.tabla),
    )


def _precargar_lecturas(panel, sem):
    """Programa las tablas que usan varias secciones y callbacks."""
    precargar(
        panel,
        {
            "fp:trayectorias": lambda: nucleo.clima.trayectorias_frutos_peso(panel.tabla),
            "fp:descomposicion": lambda: nucleo.clima.descomponer_frutos_peso(sem),
            "fp:picos": lambda: nucleo.clima.resumen_picos_frutos_peso(panel.tabla),
            # Los puntos 5 y 6 forman parte de la lectura principal. Se preparan detrás
            # de las piezas visibles para no bloquear el primer viewport.
            "fp:floracion:Frutos": lambda: nucleo.clima.rezago_floracion(panel.tabla, objetivo="Frutos"),
            "fp:mejor-rezago": lambda: nucleo.clima.mejor_rezago_por_variable(sem, panel.tabla),
            "fp:rezagos": lambda: nucleo.clima.rezagos_todos(sem, panel.tabla),
        },
    )


def layout():
    return html.Div(
        id="fp-contenido",
        children=[
            *[
                dcc.Store(id=f"fp-listo-{parte}", data=False)
                for parte in (
                    "resumen", "descomposicion", "trayectoria", "picos",
                    "picos-grafico", "peso", "peso-grafico",
                )
            ],
            html.Div(id="fp-carga-inicial", children=ui.esqueleto_pagina()),
            html.Div(id="fp-pagina-lista", style={"display": "none"}, children=_estructura()),
        ],
    )


def _estilo_figura(fig, altura: int):
    """Acabado común para que el gráfico acompañe la explicación, no compita con ella."""
    fig.update_layout(
        height=altura,
        margin={"l": 8, "r": 8, "t": 26, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "ui-sans-serif, system-ui, sans-serif", "color": "#475569"},
        hoverlabel={"bgcolor": "#ffffff", "bordercolor": "#d6d3d1"},
    )
    fig.update_xaxes(gridcolor="#e7e5e4", zeroline=False)
    fig.update_yaxes(gridcolor="#f5f5f4", zeroline=False)
    return fig


def _formato_p(p: float) -> str:
    return "p < 0,001" if p < 0.001 else f"p = {p:.3f}".replace(".", ",")


def _resumen(descomp, tray) -> html.Div:
    frutos = descomp[descomp.Objetivo == "Frutos"]
    peso = descomp[descomp.Objetivo == "Peso"]
    sobreviven_frutos = int(frutos.Sobrevive.sum())
    sobreviven_peso = int(peso.Sobrevive.sum())
    cambio = tray["Cambio neto peso (g)"]
    return ui.fila_kpi([
        ui.kpi(
            "Módulos con Frutos y Peso",
            str(len(tray)),
            nota="Módulos con al menos tres semanas observadas de ambos componentes.",
        ),
        ui.kpi(
            "Peak observado",
            f"{int(tray['Semana peak frutos'].min())}–{int(tray['Semana peak frutos'].max())}",
            nota=f"Semanas del peak; la mediana es S{int(tray['Semana peak frutos'].median())}.",
            serie=sorted(tray["Semana peak frutos"].tolist()),
        ),
        ui.kpi(
            "Peso baja al cierre",
            f"{int((cambio < 0).sum())} / {len(cambio)}",
            nota="Comparación entre la primera y la última semana observada; no es causalidad.",
        ),
        ui.kpi(
            "Cuajado / tamaño",
            f"{sobreviven_frutos} / {sobreviven_peso}",
            nota="Señales que sobreviven al control del calendario: Frutos / Peso.",
        ),
    ])


def _respuesta_corta(descomp) -> html.Div:
    frutos = descomp[descomp.Objetivo == "Frutos"]
    peso = descomp[descomp.Objetivo == "Peso"]
    quedan_frutos = frutos.loc[frutos.Sobrevive, "Variable"].tolist()
    quedan_peso = peso.loc[peso.Sobrevive, "Variable"].tolist()
    respuesta = (
        "**La separación sí aporta una lectura nueva.** Después de descontar el "
        f"calendario queda señal para **Frutos** en {', '.join(quedan_frutos) or 'ninguna variable'} "
        f"y para **Peso** en {', '.join(quedan_peso) or 'ninguna variable'}. "
        "Eso orienta si la relación aparece en el cuajado o en el tamaño, pero sigue "
        "siendo una asociación observacional."
    )
    conexion = html.Div(
        className="grid gap-4",
        children=[
            html.Div([
                html.Div("Este análisis responde", className="text-sm font-semibold text-slate-700"),
                html.P(
                    "Si el clima y el riego acompañan a la cantidad de frutos, al peso "
                    "del fruto o a ambos por mecanismos distintos.",
                    className="mt-1.5 text-sm leading-relaxed text-slate-600",
                ),
            ]),
            html.Div([
                html.Div("Cómo ayuda al modelo", className="text-sm font-semibold text-slate-700"),
                html.P(
                    "Evita entrenar una sola historia de kg/ha. El modelo puede probar por "
                    "separado cuajado y tamaño, con sus propias ventanas de tiempo y sus "
                    "propios límites de evidencia.",
                    className="mt-1.5 text-sm leading-relaxed text-slate-600",
                ),
            ]),
        ],
    )
    return ui.panel(
        "Respuesta corta",
        ui.semaforo("aviso", respuesta),
        conexion,
        ayuda="La conclusión ejecutiva sobre los dos componentes del kg/ha.",
    )


def _cargando(id_: str, altura: str = "h-56") -> html.Div:
    """Reserva el espacio de una sección con un skeleton, no con un bloque en blanco."""
    return html.Div(id=id_, children=ui.esqueleto_seccion(altura))


def _estructura():
    """Estructura estable: ningún callback apunta a un componente creado por otro.

    Dash registra todos estos IDs en el mismo render inicial de la página. Así se evita la
    carrera que producía «nonexistent object» y también se reserva todo el espacio antes de
    que lleguen los gráficos.
    """
    return html.Div(
        children=[
            ui.encabezado_pagina(
                "¿Qué cambia: cuántos frutos o cuánto pesa cada fruto?",
                "kg/ha mezcla dos procesos. Los separamos para saber qué relación aparece "
                "en el cuajado, cuál en el tamaño y qué puede pasar al modelo predictivo.",
            ),
            html.Div(
                className="space-y-4",
                children=[
                    _cargando("fp-resumen-body"),
                    ui.panel(
                        "1 · Separar frutos y peso cambia la pregunta",
                        _cargando("fp-descomposicion-body", "h-64"),
                        ayuda="Comparación de asociaciones crudas y controladas para cuajado y tamaño.",
                    ),
                    ui.panel(
                        "2 · Cómo evoluciona un módulo durante la campaña",
                        html.Div(
                            className="space-y-3",
                            children=[
                                ui.parrafo(
                                    "Selecciona un módulo para ver tres lecturas distintas: "
                                    "la sincronía temporal de Frutos y Peso, el momento del peak "
                                    "y si el peso termina por encima o por debajo de su inicio."
                                ),
                                dcc.Dropdown(
                                    id="fp-modulo", options=[], value=None,
                                    clearable=False, className="max-w-sm",
                                    persistence=True, persistence_type="session",
                                ),
                                 _cargando("fp-trayectoria-body"),
                             ],
                         ),
                        ayuda="Lectura de una trayectoria concreta, sin confundirla con el promedio del fundo.",
                    ),
                    ui.panel(
                        "3 · Cuándo aparece el peak entre módulos",
                        _cargando("fp-picos-narrativa"),
                        ui.plegable(
                            "Explorar el clima de las cuatro semanas pre-peak",
                            dcc.Dropdown(
                                id="fp-picos-clima",
                                options=[{"label": etiqueta(c), "value": c} for c in VARIABLES_PRE_PEAK],
                                value="TempMin", clearable=False,
                                persistence=True, persistence_type="session",
                            ),
                            _cargando("fp-picos-body", "h-48"),
                        ),
                        ayuda="Distribución del peak observado y clima de las semanas previas.",
                    ),
                    ui.panel(
                        "4 · Qué acompaña el cambio de peso",
                        _cargando("fp-peso-narrativa"),
                        dcc.Dropdown(
                            id="fp-peso-clima",
                            options=[{"label": etiqueta(c), "value": c} for c in VARIABLES_PRE_PEAK],
                            value="TempMin", clearable=False, className="max-w-sm",
                            persistence=True, persistence_type="session",
                        ),
                        _cargando("fp-peso-body", "h-48"),
                        ayuda="Relación exploratoria entre exposición pre-peak y cambio observado de peso.",
                    ),
                    ui.panel(
                        "5 · ¿La floración anticipa el cuajado?",
                        ui.parrafo(
                            "Compara dos mediciones biológicas reales —flores y frutos— y "
                            "descuenta tanto el calendario como el promedio de cada módulo."
                        ),
                        dcc.RadioItems(
                            id="fp-floracion-objetivo",
                            options=[
                                {"label": "Frutos (cuajado)", "value": "Frutos"},
                                {"label": "kg/ha (cosecha)", "value": "KgHa"},
                            ],
                            value="Frutos", inline=True, className="flex gap-4 text-sm",
                            persistence=True, persistence_type="session",
                        ),
                        _cargando("fp-floracion-body", "h-64"),
                        ayuda="Control más exigente con dos mediciones biológicas reales.",
                    ),
                    ui.panel(
                        "6 · Qué desfase explica cada resultado",
                        _cargando("fp-desfase-resumen", "h-48"),
                        html.Div(
                            className="grid grid-cols-2 gap-3",
                            children=[
                                dcc.Dropdown(
                                    id="fp-desfase-objetivo", options=[], value=None,
                                    clearable=False, persistence=True, persistence_type="session",
                                ),
                                dcc.Dropdown(
                                    id="fp-desfase-variable", options=[], value=None,
                                    clearable=False, persistence=True, persistence_type="session",
                                ),
                            ],
                        ),
                        _cargando("fp-desfase-body", "h-48"),
                        ayuda="Búsqueda exploratoria de ventanas temporales para cada objetivo.",
                    ),
                ],
            ),
        ],
    )


clientside_callback(
    """
    function() {
        const listos = Array.prototype.slice.call(arguments)
        const terminado = listos.length > 0 && listos.every(Boolean)
        return terminado
            ? [{'display': 'none'}, {'display': 'block'}]
            : [{'display': 'block'}, {'display': 'none'}]
    }
    """,
    DashOutput("fp-carga-inicial", "style"),
    DashOutput("fp-pagina-lista", "style"),
    *[
        DashInput(f"fp-listo-{parte}", "data")
        for parte in (
            # El primer viewport se revela junto: KPIs y explicación comparativa. Las
            # trayectorias y secciones 3–6 continúan debajo y no retienen toda la página
            # mientras Plotly prepara gráficos que todavía están fuera de pantalla.
            "resumen", "descomposicion",
        )
    ],
)


@callback(
    Output("fp-resumen-body", "children"),
    Output("fp-modulo", "options"),
    Output("fp-modulo", "value"),
    Output("fp-listo-resumen", "data"),
    Input(PANEL_STORE, "data"),
)
def _render_resumen(panel):
    if panel is None:
        return ui.esqueleto_pagina(), [], None, False
    try:
        sem = _sem(panel)
        _precargar_lecturas(panel, sem)
        tray = _tray(panel)
        descomp = _descomp(panel, sem)
        modulos = tray["Módulo"].tolist()
        contenido = html.Div(
            [_resumen(descomp, tray), _respuesta_corta(descomp)], className="space-y-4"
        )
        return contenido, modulos, (modulos[0] if modulos else None), True
    except Exception:  # pragma: no cover - la página principal ya muestra el error legible
        _LOGGER.exception("No se pudo renderizar el resumen de Frutos y peso")
        return (
            ui.semaforo("error", "No se pudo preparar el resumen de Frutos y Peso."),
            [], None, True,
        )


@callback(
    Output("fp-descomposicion-body", "children"),
    Output("fp-listo-descomposicion", "data"),
    Input(PANEL_STORE, "data"),
)
def _render_descomposicion(panel):
    if panel is None:
        return ui.esqueleto_seccion("h-64"), False
    sem = _sem(panel)
    return _descomposicion_narrativa(_descomp(panel, sem)), True


@callback(
    Output("fp-picos-narrativa", "children"),
    Output("fp-listo-picos", "data"),
    Input(PANEL_STORE, "data"),
)
def _render_picos_narrativa(panel):
    if panel is None:
        return ui.esqueleto_seccion("h-64"), False
    return _picos_narrativa(panel), True


@callback(
    Output("fp-peso-narrativa", "children"),
    Output("fp-listo-peso", "data"),
    Input(PANEL_STORE, "data"),
)
def _render_peso_narrativa(panel):
    if panel is None:
        return ui.esqueleto_seccion("h-48"), False
    return _peso_narrativa(panel), True


@callback(
    Output("fp-desfase-resumen", "children"),
    Output("fp-desfase-objetivo", "options"),
    Output("fp-desfase-objetivo", "value"),
    Input(PANEL_STORE, "data"),
)
def _render_desfases_shell(panel):
    if panel is None:
        return ui.esqueleto_seccion("h-48"), [], None
    sem = _sem(panel)
    try:
        resumen = _rezago(panel, sem)
    except (KeyError, TypeError, ValueError) as exc:
        _LOGGER.warning("No se pudo preparar la tabla de desfases: %s", exc)
        return ui.semaforo(
            "info",
            "La lectura de desfases no está disponible para esta fuente de datos; "
            "las demás lecturas de Frutos y Peso sí pueden consultarse.",
        ), [], None
    objetivos = resumen.Objetivo.unique().tolist() if not resumen.empty else []
    return _desfases_shell(sem, panel.tabla, resumen), objetivos, (objetivos[0] if objetivos else None)


@callback(
    Output("fp-trayectoria-body", "children"),
    Output("fp-listo-trayectoria", "data"),
    Input(PANEL_STORE, "data"), Input("fp-modulo", "value", allow_optional=True),
)
def _render_trayectoria(panel, modulo):
    if panel is None or modulo is None:
        return ui.esqueleto_seccion("h-64"), False
    trayectorias = _tray(panel)
    serie = panel.tabla[panel.tabla.celda == modulo].dropna(subset=["Frutos", "Peso"]).sort_values("nsem")
    fila = trayectorias.loc[trayectorias["Módulo"] == modulo].iloc[0]
    usa_poda = "dias_desde_poda" in serie.columns and serie.dias_desde_poda.notna().any()
    eje_x = "dias_desde_poda" if usa_poda else "nsem"
    peak = int(fila["Semana peak frutos"])
    huecos = int(fila["Huecos de calendario"])
    titulo_x = "días desde poda (proxy)" if usa_poda else "semana calendario"

    x_peak = float(fila["Días desde poda peak"]) if usa_poda else peak
    fig_juntas = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.14,
        subplot_titles=("Cuántos frutos hay", "Cuánto pesa cada fruto"),
    )
    fig_juntas.add_trace(
        go.Scatter(
            x=serie[eje_x], y=serie.Frutos, mode="lines+markers", name="Frutos/planta",
            line={"color": AZUL, "width": 2.5},
            hovertemplate="%{x}<br>frutos/planta = %{y:.1f}<extra></extra>",
        ), row=1, col=1,
    )
    fig_juntas.add_trace(
        go.Scatter(
            x=serie[eje_x], y=serie.Peso, mode="lines+markers", name="Peso (g)",
            line={"color": ROJO, "width": 2.5},
            hovertemplate="%{x}<br>peso = %{y:.2f} g<extra></extra>",
        ), row=2, col=1,
    )
    fig_juntas.add_vline(x=x_peak, line_dash="dash", line_color="#94a3b8", row=1, col=1)
    fig_juntas.add_vline(x=x_peak, line_dash="dash", line_color="#94a3b8", row=2, col=1)
    fig_juntas.update_yaxes(title_text="frutos/planta", row=1, col=1)
    fig_juntas.update_yaxes(title_text="peso (g)", row=2, col=1)
    fig_juntas.update_xaxes(title_text=titulo_x, row=2, col=1)
    _estilo_figura(fig_juntas, 470)
    fig_juntas.update_layout(showlegend=False, hovermode="x unified")

    fig_frutos = go.Figure(go.Scatter(x=serie[eje_x], y=serie.Frutos, mode="lines+markers", name="Frutos/planta", line={"color": AZUL, "width": 2.8}))
    fig_frutos.add_vline(x=x_peak, line_dash="dash", line_color=ROJO)
    fig_frutos.add_annotation(x=x_peak, y=float(fila["Peak frutos/planta"]),
                              text=f"peak S{peak}", showarrow=True, arrowhead=2)
    fig_frutos.update_layout(xaxis_title=titulo_x, yaxis_title="frutos por planta")
    _estilo_figura(fig_frutos, 360)

    fig_peso = go.Figure()
    fig_peso.add_trace(
        go.Scatter(
            x=serie[eje_x], y=serie.Peso, mode="lines+markers", name="Peso observado",
            line={"color": ROJO, "width": 2.8},
            hovertemplate="%{x}<br>peso = %{y:.2f} g<extra></extra>",
        )
    )
    fig_peso.add_trace(
        go.Scatter(
            x=[serie[eje_x].iloc[0], serie[eje_x].iloc[-1]],
            y=[serie.Peso.iloc[0], serie.Peso.iloc[-1]],
            mode="markers+text", name="Inicio y final",
            marker={"color": [AZUL, ROJO], "size": 9},
            text=["inicio", "final"], textposition="top center",
        )
    )
    fig_peso.update_layout(xaxis_title=titulo_x, yaxis_title="peso del fruto (g)", showlegend=False)
    _estilo_figura(fig_peso, 360)

    bloques = [
        ui.fila_kpi([
            ui.kpi(
                "Peak de frutos", f"S{peak}",
                nota=f"Aparece en la posición {fila['Posición del peak'].lower()} de la ventana observada.",
            ),
            ui.kpi(
                "Frutos en el peak", f"{fila['Peak frutos/planta']:.1f}",
                nota="Peak semanal por planta; no es el total de la campaña.",
            ),
            ui.kpi(
                "Peso: inicio → final",
                f"{fila['Peso inicial (g)']:.2f} → {fila['Peso final (g)']:.2f}",
                nota="Gramos por fruto; compara solo semanas observadas.",
            ),
            ui.kpi(
                "Cambios de sentido", str(int(fila["Cambios de sentido"])),
                nota="La curva no es monotónica; por eso se evita una recta como conclusión.",
            ),
        ]),
    ]
    if huecos:
        bloques.append(ui.semaforo(
            "aviso",
            f"Este módulo tiene **{huecos} hueco(s) de calendario**. La suma acumulada "
            "es solo la suma de semanas observadas y no debe presentarse como total "
            "anual hasta completar o justificar esos huecos.",
        ))
    bloques.append(dcc.Tabs(children=[
        dcc.Tab(label="Frutos + peso", children=dcc.Graph(figure=fig_juntas, config={"displaylogo": False})),
        dcc.Tab(label="Peak de frutos", children=dcc.Graph(figure=fig_frutos, config={"displaylogo": False})),
        dcc.Tab(label="Curva de peso", children=dcc.Graph(figure=fig_peso, config={"displaylogo": False})),
    ]))
    bloques.append(ui.parrafo(
        f"El módulo acumula **{fila['Frutos acumulados observados/planta']:.1f} frutos/planta "
        "observados**, pero tiene "
        f"**{huecos} huecos de calendario**; no se presenta como total anual. "
        f"La curva de peso cambia de dirección {int(fila['Cambios de sentido'])} veces, "
        "así que su lectura principal es el inicio y el final observados, no una recta global."
    ))
    bloques.append(ui.plegable(
        "Ver el detalle de todos los módulos",
        ui.parrafo(
            "La posición del peak divide la ventana observada en tres partes. Es una "
            "descripción del registro disponible, no una fase fenológica medida."
        ),
        ui.tabla_desde_df(trayectorias, formato={
            "Peak frutos/planta": "{:.2f}", "Frutos acumulados observados/planta": "{:.1f}",
            "Peso inicial (g)": "{:.2f}", "Peso final (g)": "{:.2f}",
            "Cambio neto peso (g)": "{:+.2f}", "Pendiente peso (g/sem)": "{:+.3f}",
        }),
    ))
    return html.Div(bloques, className="space-y-3"), True


def _descomposicion_narrativa(tabla) -> html.Div:
    """Una sola lectura comparativa: qué queda para Frutos y qué queda para Peso."""
    filas = [("Frutos", "Frutos por planta"), ("Peso", "Peso del fruto")]
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.14,
        subplot_titles=("Frutos por planta · cuajado", "Peso del fruto · tamaño"),
    )
    lecturas = []
    for i, (objetivo, titulo) in enumerate(filas, start=1):
        sub = tabla[tabla.Objetivo == objetivo].sort_values(
            "r sin controlar", key=lambda s: s.abs(), ascending=False
        )
        fig.add_trace(
            go.Bar(
                y=sub.Variable, x=sub["r sin controlar"], orientation="h",
                name="Sin controlar", legendgroup="cruda", showlegend=i == 1,
                marker_color=ROJO, opacity=0.8,
                hovertemplate="%{y}<br>r cruda = %{x:+.3f}<extra></extra>",
            ), row=i, col=1,
        )
        fig.add_trace(
            go.Bar(
                y=sub.Variable, x=sub["r control no lineal"], orientation="h",
                name="Descontando el calendario", legendgroup="control", showlegend=i == 1,
                marker_color=AZUL,
                hovertemplate="%{y}<br>r controlada = %{x:+.3f}<extra></extra>",
            ), row=i, col=1,
        )
        fig.add_vline(x=0, line_color="#888", row=i, col=1)
        fig.update_yaxes(title_text=titulo, row=i, col=1)
        sobreviven = sub.loc[sub.Sobrevive]
        nombres = ", ".join(
            f"{r.Variable} ({r['r control no lineal']:+.2f})" for _, r in sobreviven.iterrows()
        ) or "ninguna variable"
        cruda = sub.loc[sub["r sin controlar"].abs().idxmax()]
        lecturas.append(
            f"**{titulo}:** la asociación cruda más fuerte es {cruda.Variable} "
            f"(r = {cruda['r sin controlar']:+.2f}); después del control sobreviven "
            f"{nombres}."
        )
    fig.update_xaxes(range=[-1, 1], title_text="correlación", row=2, col=1)
    _estilo_figura(fig, 620)
    fig.update_layout(barmode="group", legend={"orientation": "h", "y": 1.06})
    frutos = tabla[tabla.Objetivo == "Frutos"]
    peso = tabla[tabla.Objetivo == "Peso"]
    sobreviven_frutos = frutos.loc[frutos.Sobrevive, "Variable"].tolist()
    sobreviven_peso = peso.loc[peso.Sobrevive, "Variable"].tolist()
    mensaje = (
        "**El calendario cambia la historia.** "
        f"En Frutos queda: {', '.join(sobreviven_frutos) or 'ninguna señal'}. "
        f"En Peso queda: {', '.join(sobreviven_peso) or 'ninguna señal'}. "
        "Las barras rojas no son todavía efectos: son asociaciones antes del control."
    )
    return html.Div(
        className="space-y-3",
        children=[
            ui.parrafo(
                "La misma variable puede asociarse con cuántos frutos hay y con cuánto "
                "pesa cada fruto de forma distinta. La comparación correcta es entre la "
                "barra roja —sin controlar el calendario— y la azul —después de descontarlo—."
            ),
            dcc.Graph(figure=fig, config={"displaylogo": False}),
            ui.semaforo("aviso", mensaje),
            ui.parrafo(" ".join(lecturas)),
            ui.plegable(
                "Ver los valores estadísticos",
                ui.tabla_desde_df(tabla, ocultar=["clave"], formato={
                    "r sin controlar": "{:+.3f}", "p sin controlar": "{:.4f}",
                    "r control no lineal": "{:+.3f}", "p control no lineal": "{:.4f}",
                }),
            ),
        ],
    )


def _descomposicion(sem) -> html.Div:
    tabla = nucleo.clima.descomponer_frutos_peso(sem)
    bloques = [
        ui.titulo_seccion("Relación de frutos y peso con clima y riego"),
    ]
    for objetivo, titulo in [("Frutos", "Frutos por planta"), ("Peso", "Peso del fruto")]:
        sub = tabla[tabla.Objetivo == objetivo].sort_values("r sin controlar", key=lambda s: s.abs(), ascending=False)
        fig = go.Figure()
        fig.add_trace(go.Bar(y=sub.Variable, x=sub["r sin controlar"], orientation="h", name="Sin controlar", marker_color=ROJO, opacity=0.85))
        fig.add_trace(go.Bar(y=sub.Variable, x=sub["r control no lineal"], orientation="h", name="Descontando el calendario", marker_color=AZUL))
        fig.add_vline(x=0, line_color="#888")
        fig.update_layout(height=280, barmode="group", margin={"l": 10, "r": 10, "t": 10, "b": 10},
                          xaxis_title=f"correlación con {titulo.lower()}", xaxis_range=[-1, 1],
                          legend={"orientation": "h", "y": 1.2}, showlegend=(objetivo == "Frutos"))
        bloques.append(ui.titulo_seccion(titulo, "h4"))
        bloques.append(dcc.Graph(figure=fig, config={"displaylogo": False}))

        sobreviven = sub.loc[sub.Sobrevive, "Variable"].tolist()
        bloques.append(
            ui.semaforo("ok", f"Sobreviven al control del calendario: **{', '.join(sobreviven)}**.")
            if sobreviven else
            ui.semaforo("info", f"Ninguna variable sobrevive al control del calendario para {titulo.lower()}.")
        )
        if not sub.empty:
            cruda = sub.loc[sub["r sin controlar"].abs().idxmax()]
            controlada = sub.loc[sub["r control no lineal"].abs().idxmax()]
            if bool(controlada["Sobrevive"]):
                lectura = (
                    f"**Lectura dinámica para {titulo.lower()}:** la asociación cruda "
                    f"más fuerte es {cruda['Variable']} (r = {cruda['r sin controlar']:+.3f}), "
                    "pero la señal que queda con mayor magnitud tras descontar el "
                    f"calendario es {controlada['Variable']} (r = "
                    f"{controlada['r control no lineal']:+.3f}; p = "
                    f"{controlada['p control no lineal']:.3f}). Esto sigue siendo una "
                    "asociación temporal controlada, no un efecto causal."
                )
            else:
                lectura = (
                    f"**Lectura dinámica para {titulo.lower()}:** {cruda['Variable']} "
                    f"presenta la mayor asociación cruda (r = {cruda['r sin controlar']:+.3f}), "
                    "pero ninguna señal queda estadísticamente respaldada al descontar "
                    f"el calendario; la mayor restante es {controlada['Variable']} "
                    f"(r = {controlada['r control no lineal']:+.3f}). No se puede decir "
                    "que el clima haya causado el cambio observado."
                )
            bloques.append(ui.parrafo(lectura))

        poda_sub = sub.dropna(subset=["r control poda"]) if "r control poda" in sub else sub.iloc[0:0]
        if not poda_sub.empty:
            fig_poda = go.Figure(go.Bar(
                y=poda_sub.Variable, x=poda_sub["r control poda"], orientation="h",
                marker_color=[ROJO if s else AZUL for s in poda_sub["Sobrevive poda"]],
                hovertemplate="%{y}<br>r control poda = %{x:+.3f}<extra></extra>",
            ))
            fig_poda.add_vline(x=0, line_color="#888")
            fig_poda.update_layout(height=260, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                                   xaxis_title=f"asociación con {titulo.lower()} después de controlar días desde poda", xaxis_range=[-1, 1])
            bloques.append(dcc.Graph(figure=fig_poda, config={"displaylogo": False}))
            sobreviv_poda = poda_sub.loc[poda_sub["Sobrevive poda"], "Variable"].tolist()
            bloques.append(ui.parrafo(
                f"**Lectura con poda para {titulo.lower()}:** " + (
                    f"quedan señales en {', '.join(sobreviv_poda)}; siguen siendo "
                    "asociaciones condicionadas, no efectos causales."
                    if sobreviv_poda else
                    "ninguna variable mantiene p < 0,05 después de usar días desde poda como control proxy."
                )
            ))

    bloques.append(ui.como_leer(
        "Mismo formato que la Prueba 2 de Evidencia: la barra roja es la correlación "
        "cruda y la azul es lo que queda tras descontar el tiempo. La figura adicional "
        "usa días desde poda como control proxy. Si una variable pesa distinto sobre "
        "Frutos que sobre Peso, es una pista sobre EN QUÉ ETAPA actúa — cuajado o "
        "llenado — que kg/ha por sí solo no puede distinguir.\n\n"
        "**Advertencia de siempre:** correlación, no causalidad. Y con Frutos y Peso "
        "el riesgo de leer causalidad al revés es mayor: el fundo puede estar "
        "*ajustando* el riego según cómo viene la fruta, no solo la fruta respondiendo "
        "al riego que se le dio."
    ))
    bloques.append(ui.tabla_desde_df(tabla, ocultar=["clave"], formato={
        "r sin controlar": "{:+.3f}", "p sin controlar": "{:.4f}",
        "r control no lineal": "{:+.3f}", "p control no lineal": "{:.4f}",
    }))
    return html.Div(bloques, className="space-y-3")


def _floracion_shell(panel) -> html.Div:
    if "flores_promedio" not in panel.tabla.columns or panel.tabla.flores_promedio.isna().all():
        return html.Div([
            ui.titulo_seccion("Floración: ¿anticipa el cuajado de fruta?", "h4"),
            ui.semaforo("info", "No se cargó «DAtos mes.xlsx» (hoja EvFlores) — sin esto no hay conteo real de flores para comparar contra Frutos."),
        ])
    return html.Div(
        className="space-y-3",
        children=[
            ui.titulo_seccion("Floración: ¿anticipa el cuajado de fruta?", "h4"),
            ui.parrafo(
                "A diferencia de todo lo demás en esta sección, esto no compara clima "
                "contra resultado: compara **dos mediciones biológicas reales** — "
                "flores contadas por turno y frutos por planta — para ver si la "
                "floración de hace algunas semanas anticipa el cuajado de fruta. El "
                "control es más exigente que el resto del tablero: además de "
                "descontar el calendario, se descuenta el **promedio de cada módulo** "
                "(efecto fijo)."
            ),
            dcc.RadioItems(
                id="fp-floracion-objetivo",
                options=[{"label": "Frutos (cuajado)", "value": "Frutos"}, {"label": "kg/ha (cosecha)", "value": "KgHa"}],
                value="Frutos", inline=True, className="flex gap-4 text-sm",
                persistence=True, persistence_type="session",
            ),
            html.Div(id="fp-floracion-body", children=ui.esqueleto_seccion("h-64")),
        ],
    )


@callback(
    Output("fp-floracion-body", "children"),
    Input(PANEL_STORE, "data"),
    Input("fp-floracion-objetivo", "value", allow_optional=True),
)
def _render_floracion(panel, objetivo_flor):
    if panel is None or objetivo_flor is None:
        return ui.esqueleto_seccion("h-64")
    try:
        rezago = obtener(
            panel,
            f"fp:floracion:{objetivo_flor}",
            lambda: nucleo.clima.rezago_floracion(panel.tabla, objetivo=objetivo_flor),
        )
    except (KeyError, TypeError, ValueError) as exc:
        _LOGGER.warning("Floración opcional no disponible: %s", exc)
        return ui.semaforo(
            "info",
            "La fuente opcional de floración no está disponible en este despliegue; "
            "el resto del análisis de Frutos y Peso sí puede consultarse.",
        )
    if rezago.empty:
        return ui.semaforo("info", f"No hay suficiente solapamiento entre floración y {objetivo_flor} para esta prueba.")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rezago.Rezago, y=rezago["r bruto"], mode="lines+markers", name="Sin controlar", line={"color": GRIS}))
    fig.add_trace(go.Scatter(x=rezago.Rezago, y=rezago["r control módulo"], mode="lines+markers", name="Controlando módulo", line={"color": ROJO, "dash": "dot"}))
    fig.add_trace(go.Scatter(x=rezago.Rezago, y=rezago["r control módulo y calendario"], mode="lines+markers", name="Controlando módulo y calendario", line={"color": AZUL, "width": 2.8}))
    fig.add_hline(y=0, line_color="#888")
    nombre_obj = "Frutos" if objetivo_flor == "Frutos" else "kg/ha"
    fig.update_layout(height=380, xaxis_title=f"semanas de floración antes de {nombre_obj}", yaxis_title=f"correlación con {nombre_obj}",
                      yaxis_range=[-1, 1], margin={"l": 10, "r": 10, "t": 10, "b": 10}, legend={"orientation": "h", "y": 1.14})

    mejor = rezago.loc[rezago["r control módulo y calendario"].abs().idxmax()]
    con_mismo = (rezago.Rezago == 0).any()
    r_mismo = float(rezago.loc[rezago.Rezago == 0, "r control módulo y calendario"].iloc[0]) if con_mismo else None
    r_mejor = float(mejor["r control módulo y calendario"])
    if con_mismo:
        nota_mismo = f" (negativa: mientras el módulo florece todavía no tiene {nombre_obj.lower()})" if r_mismo < 0 else ""
        mensaje = (
            f"Sí. Con el control completo (módulo y calendario), la correlación con la "
            f"misma semana es {r_mismo:+.3f}{nota_mismo}, y sube a {r_mejor:+.3f} "
            f"(p = {mejor['p control módulo y calendario']:.1e}, n = {int(mejor.n)} "
            f"celdas de {int(mejor['módulos'])} módulos) con {int(mejor.Rezago)} semanas de anticipación."
        )
        mejora = abs(r_mejor) > abs(r_mismo)
    else:
        mensaje = f"Mejor rezago: {int(mejor.Rezago)} semanas, r = {r_mejor:+.3f} (p = {mejor['p control módulo y calendario']:.1e})."
        mejora = True

    return html.Div(
        className="space-y-3",
        children=[
            dcc.Graph(figure=fig, config={"displaylogo": False}),
            ui.veredicto_de_prueba(
                f"¿La floración de antes explica mejor {nombre_obj} que la de la misma semana?",
                mensaje, "ok" if mejora else "aviso",
                "**Por qué el control de módulo, además del de calendario.** Todo el "
                "resto del tablero compara clima (igual para todos los módulos de una "
                "semana) contra un resultado que varía por módulo. Acá las dos series "
                "varían por módulo, así que un módulo que simplemente florece y "
                "fructifica más que el resto inflaría la correlación si no se descuenta "
                "también su propio promedio.\n\n"
                "**Este resultado sobrevive controles que casi ninguna variable "
                "climática del tablero sobrevive.** Sigue siendo observacional: es una "
                "correlación controlada, no un modelo entrenado.",
            ),
            ui.tabla_desde_df(rezago, formato={
                "r bruto": "{:+.3f}", "p bruto": "{:.4f}", "r control módulo": "{:+.3f}",
                "p control módulo": "{:.4f}", "r control módulo y calendario": "{:+.3f}",
                "p control módulo y calendario": "{:.4f}",
            }),
            html.P(
                "El número de celdas y de módulos baja con el rezago porque cada "
                "semana de anticipación exige una semana más de floración observada "
                "antes: por eso ésta no se agregó como variable del modelo conjunto.",
                className="text-xs text-slate-500",
            ),
            ui.semaforo(
                "aviso",
                "**Probado y descartado: usar solo la floración (con su mejor rezago) "
                f"para predecir {nombre_obj} con XGBoost.** La correlación de arriba es "
                "real, pero un modelo entrenado únicamente con floración da R² honesto "
                "(deja-un-bloque-fuera) de **−0,04** — peor que predecir siempre el "
                "promedio. El modelo actual (las 7 variables de clima y riego) da +0,32 "
                "en el mismo test.",
            ),
        ],
    )


def _desfases_shell(sem, tabla, resumen) -> html.Div:
    if resumen.empty:
        return html.Div([
            ui.titulo_seccion("Qué desfase explica mejor kg/ha, Frutos, Peso y Floración", "h4"),
            ui.semaforo("info", "No hay suficientes semanas con Frutos y Peso para esta búsqueda."),
        ])
    tope = int(resumen["Mejor rezago (semanas)"].max())
    en_el_tope = resumen[resumen["Mejor rezago (semanas)"] == tope]
    bloques = [
        ui.titulo_seccion("Qué desfase explica mejor kg/ha, Frutos, Peso y Floración", "h4"),
        ui.parrafo(
            "Repite la misma búsqueda de la Prueba 3 de Evidencia —mismo rango de 0 a 8 "
            "semanas, mismo control no lineal del calendario— pero también contra "
            "**Frutos**, **Peso** y **Floración**, para decir si el riego, la "
            "temperatura o la ETo pesan en una ventana distinta sobre el cuajado que "
            "sobre el llenado."
        ),
    ]
    if len(en_el_tope) >= len(resumen) / 2:
        bloques.append(ui.semaforo(
            "aviso",
            f"**{len(en_el_tope)} de {len(resumen)} combinaciones eligen el rezago "
            f"máximo probado ({tope} semanas).** Eso es una señal de alerta, no una "
            "confirmación: con solo 50 semanas de campaña y muchas combinaciones "
            "probadas, parte de esas correlaciones altas puede ser el mejor resultado "
            "de muchos intentos, no un óptimo real dentro de la ventana probada.",
        ))
    bloques.append(ui.tabla_desde_df(resumen, ocultar=["clave"], formato={
        "r sin tendencia en el mejor rezago": "{:+.3f}", "r sin tendencia en rezago 0": "{:+.3f}",
    }))
    if "Floración" in resumen.Objetivo.values:
        bloques.append(ui.semaforo(
            "info",
            "**La fila de Floración usa un control distinto de las otras tres.** "
            "kg/ha, Frutos y Peso se miden con la serie semanal agregada del fundo; la "
            "floración varía por módulo, así que acá se descuenta ADEMÁS el promedio "
            "de cada módulo (efecto fijo).",
        ))
    bloques.append(ui.como_leer(
        "**«Mejor rezago»** es el número de semanas de promedio móvil que maximiza la "
        "correlación **ya descontado el calendario** — no la cruda. Un mejor rezago de "
        "0 semanas quiere decir que ninguna ventana desplazada superó a la señal "
        "contemporánea."
    ))

    return html.Div(bloques, className="space-y-3")


@callback(
    Output("fp-desfase-variable", "options"), Output("fp-desfase-variable", "value"),
    Input(PANEL_STORE, "data"),
    Input("fp-desfase-objetivo", "value", allow_optional=True),
)
def _opciones_desfase_variable(panel, objetivo_sel):
    if panel is None or objetivo_sel is None:
        return [], None
    sem = _sem(panel)
    try:
        resumen = _rezago(panel, sem)
    except (KeyError, TypeError, ValueError) as exc:
        _LOGGER.warning("No se pudieron preparar las opciones de desfase: %s", exc)
        return [], None
    claves = resumen.loc[resumen.Objetivo == objetivo_sel, "clave"].tolist()
    opciones = [{"label": etiqueta(c), "value": c} for c in claves]
    return opciones, (claves[0] if claves else None)


@callback(
    Output("fp-desfase-body", "children"),
    Input(PANEL_STORE, "data"),
    Input("fp-desfase-objetivo", "value", allow_optional=True),
    Input("fp-desfase-variable", "value", allow_optional=True),
)
def _render_desfase(panel, objetivo_sel, variable_sel):
    if panel is None:
        return ui.esqueleto_seccion("h-48")
    if objetivo_sel is None or variable_sel is None:
        return ui.semaforo(
            "info",
            "No hay suficientes datos para buscar un desfase en esta fuente de datos.",
        )
    sem = _sem(panel)
    try:
        todos = _rezagos(panel, sem)
    except (KeyError, TypeError, ValueError) as exc:
        _LOGGER.warning("No se pudo renderizar el detalle de desfase: %s", exc)
        return ui.semaforo(
            "info",
            "El detalle de desfases no está disponible para esta fuente de datos.",
        )
    d = todos[(todos.Objetivo == objetivo_sel) & (todos.clave == variable_sel)]
    if d.empty:
        return ui.semaforo(
            "info",
            "No hay observaciones suficientes para ese objetivo y variable.",
        )
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d.Rezago, y=d["r bruto"], mode="lines+markers", name="Sin descontar la estación", line={"color": ROJO}))
    fig.add_trace(go.Scatter(x=d.Rezago, y=d["r sin tendencia"], mode="lines+markers", name="Descontando la estación", line={"color": AZUL, "dash": "dot"}))
    fig.add_hline(y=0, line_color="#888")
    fig.update_layout(height=340, xaxis_title="semanas de rezago", yaxis_title=f"correlación con {objetivo_sel}",
                      yaxis_range=[-1, 1], margin={"l": 10, "r": 10, "t": 10, "b": 10}, legend={"orientation": "h", "y": 1.14})
    return dcc.Graph(figure=fig, config={"displaylogo": False})


def _picos_narrativa(panel) -> html.Div:
    tray = _tray(panel)
    resumen = _picos(panel)
    if tray.empty or resumen.empty:
        return ui.semaforo("info", "No hay suficientes pares Frutos–Peso para comparar el momento del peak.")

    fig = px.scatter(
        tray.sort_values("Semana peak frutos"),
        x="Semana peak frutos", y="Módulo", size="Peak frutos/planta",
        color="Días desde poda peak", color_continuous_scale="Viridis",
        hover_name="Módulo",
        hover_data=["Semana inicial", "Semana final", "Peak frutos/planta", "Posición del peak"],
        labels={
            "Semana peak frutos": "semana del peak de frutos",
            "Días desde poda peak": "días desde poda",
            "Peak frutos/planta": "frutos/planta en el peak",
        },
    )
    fig.update_xaxes(dtick=2)
    _estilo_figura(fig, max(430, 28 * len(tray)))
    fig.update_layout(margin={"l": 8, "r": 8, "t": 18, "b": 8})

    peaks = tray["Semana peak frutos"]
    posicion = tray["Posición del peak"].value_counts().reindex(["Inicio", "Medio", "Final"], fill_value=0)
    return html.Div(
        className="space-y-3",
        children=[
            ui.parrafo(
                f"El peak observado cae entre **S{int(peaks.min())} y S{int(peaks.max())}**, "
                f"con mediana en **S{int(peaks.median())}**. Cada punto es un módulo; el "
                "tamaño representa cuántos frutos/planta había en ese peak y el color "
                "indica los días desde poda. Aquí mostramos la semana real del peak, no "
                "solo su posición relativa dentro de una ventana incompleta."
            ),
            dcc.Graph(figure=fig, config={"displaylogo": False}),
            ui.semaforo(
                "info",
                f"**Lectura del registro actual:** {int(posicion.get('Inicio', 0))} módulos "
                f"quedan clasificados en Inicio, {int(posicion.get('Medio', 0))} en Medio y "
                f"{int(posicion.get('Final', 0))} en Final. Esta clasificación describe "
                "la ventana observada; no demuestra por sí sola una fase biológica."
            ),
            ui.plegable(
                "Ver el resumen por posición relativa",
                ui.parrafo(
                    "La posición relativa sirve como descriptor del tramo observado, pero "
                    "no debe leerse como una fase fenológica medida."
                ),
                ui.tabla_desde_df(resumen, formato={
                    "DAP peak medio": "{:.0f}", "Poda dispersion dias media": "{:.0f}",
                    "Semana peak media": "{:.1f}", "Frutos peak medio": "{:.1f}",
                    "Peso peak medio (g)": "{:.2f}", "TempMin pre-peak": "{:.2f}",
                    "DPV pre-peak": "{:.2f}", "Rad pre-peak": "{:.1f}",
                    "ETo pre-peak": "{:.1f}", "Riego pre-peak": "{:.2f}",
                    "GDD pre-peak": "{:.1f}",
                }),
            ),
        ],
    )


def _picos_shell(panel) -> html.Div:
    tray = _tray(panel)
    resumen = _picos(panel)
    if tray.empty or resumen.empty:
        return html.Div([
            ui.titulo_seccion("Por qué el peak de frutos aparece al inicio, medio o final", "h4"),
            ui.semaforo("info", "No hay suficientes pares Frutos–Peso por módulo para comparar la posición del peak."),
        ])

    conteo = tray["Posición del peak"].value_counts().reindex(["Inicio", "Medio", "Final"], fill_value=0)
    fig_conteo = px.bar(
        x=conteo.index, y=conteo.values, text=conteo.values,
        color=conteo.index, color_discrete_sequence=[AZUL, "#7f8c8d", ROJO],
        labels={"x": "posición del peak dentro de la ventana observada", "y": "módulos"},
    )
    fig_conteo.update_layout(height=330, showlegend=False, margin={"l": 10, "r": 10, "t": 10, "b": 10})

    bloques = [
        ui.titulo_seccion("Por qué el peak de frutos aparece al inicio, medio o final", "h4"),
        ui.parrafo(
            "La posición del peak se calcula dentro de la ventana observada de cada "
            "módulo. Después se compara con días desde poda, con la dispersión de poda "
            "y con el clima de las cuatro semanas observadas que preceden al peak."
        ),
        html.Div(className="grid grid-cols-2 gap-4", children=[
            dcc.Graph(figure=fig_conteo, config={"displaylogo": False}),
            html.Div([
                dcc.Dropdown(
                    id="fp-picos-clima",
                    options=[{"label": etiqueta(c), "value": c} for c in VARIABLES_PRE_PEAK],
                    value="TempMin", clearable=False,
                ),
                html.Div(id="fp-picos-body"),
            ]),
        ]),
        ui.tabla_desde_df(resumen, formato={
            "DAP peak medio": "{:.0f}", "Poda dispersion dias media": "{:.0f}", "Semana peak media": "{:.1f}",
            "Frutos peak medio": "{:.1f}", "Peso peak medio (g)": "{:.2f}", "TempMin pre-peak": "{:.2f}",
            "DPV pre-peak": "{:.2f}", "Rad pre-peak": "{:.1f}", "ETo pre-peak": "{:.1f}",
            "Riego pre-peak": "{:.2f}", "GDD pre-peak": "{:.1f}",
        }),
    ]

    columna_peak_resumen = next((c for c in resumen.columns if str(c).lower().startswith("posici") and "peak" in str(c).lower()), None)
    columna_peak_tray = next((c for c in tray.columns if str(c).lower().startswith("posici") and "peak" in str(c).lower()), None)
    if columna_peak_resumen and "Inicio" not in set(resumen[columna_peak_resumen].astype(str)):
        bloques.append(ui.semaforo(
            "info",
            "En la campaña actual no aparece un peak clasificado como Inicio: se "
            f"observan {int((tray[columna_peak_tray] == 'Medio').sum())} módulos en "
            f"Medio y {int((tray[columna_peak_tray] == 'Final').sum())} en Final. Esto "
            "describe la ventana observada disponible; no permite concluir que el "
            "cultivo nunca tenga peaks tempranos.",
        ))

    disponibles = resumen.dropna(subset=["DAP peak medio"])
    if len(disponibles) >= 2:
        temprano, tardio = disponibles.iloc[0], disponibles.iloc[-1]
        diff_dap = float(tardio["DAP peak medio"] - temprano["DAP peak medio"])
        diff_temp = float(tardio["TempMin pre-peak"] - temprano["TempMin pre-peak"])
        diff_dpv = float(tardio["DPV pre-peak"] - temprano["DPV pre-peak"])
        bloques.append(ui.parrafo(
            f"**Lectura dinámica:** los peaks del grupo **{temprano['Posición del peak']}** "
            f"ocurren en promedio a {temprano['DAP peak medio']:.0f} días desde poda y "
            f"los del grupo **{tardio['Posición del peak']}** a {tardio['DAP peak medio']:.0f} "
            f"días; la diferencia es de {diff_dap:+.0f} días. En las cuatro semanas "
            f"pre-peak, la temperatura mínima cambia {diff_temp:+.2f} °C y el DPV "
            f"{diff_dpv:+.2f} kPa entre ambos grupos. Esto permite ver si el "
            "desplazamiento del peak coincide con una exposición climática distinta, "
            "pero no demuestra causalidad."
        ))
    return html.Div(bloques, className="space-y-3")


@callback(
    Output("fp-picos-body", "children"),
    Output("fp-listo-picos-grafico", "data"),
    Input(PANEL_STORE, "data"), Input("fp-picos-clima", "value", allow_optional=True),
)
def _render_picos(panel, variable):
    if panel is None or variable is None:
        return ui.esqueleto_seccion("h-48"), False
    tray = _tray(panel)
    columna = _COLUMNA_PRE_PEAK[variable]
    x = "Días desde poda peak" if tray["Días desde poda peak"].notna().any() else "Semana peak frutos"
    fig = px.scatter(
        tray, x=x, y=columna, color="Posición del peak", hover_name="Módulo",
        category_orders={"Posición del peak": ["Inicio", "Medio", "Final"]},
        color_discrete_sequence=[AZUL, "#7f8c8d", ROJO],
    )
    fig.update_layout(height=330, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      xaxis_title="días desde poda del peak" if x.startswith("Días") else "semana del peak",
                      yaxis_title=f"{etiqueta(variable)}: promedio de 4 semanas pre-peak")
    return dcc.Graph(figure=fig, config={"displaylogo": False}), True


def _peso_narrativa(panel) -> html.Div:
    tray = _tray(panel)
    if tray.empty:
        return ui.semaforo("info", "No hay suficientes trayectorias de peso para esta comparación.")
    cambio = tray["Cambio neto peso (g)"]
    return html.Div(
        className="space-y-3",
        children=[
            ui.parrafo(
                f"En el registro actual, el peso termina por debajo del inicio en "
                f"**{int((cambio < 0).sum())} de {len(cambio)} módulos**. Eso describe una "
                "caída observada en el intervalo disponible; no significa que el clima "
                "sea su causa. La nube siguiente sirve para comprobar si alguna exposición "
                "de las cuatro semanas pre-peak acompaña ese cambio."
            ),
        ],
    )


def _peso_shell(panel) -> html.Div:
    tray = _tray(panel)
    if tray.empty:
        return None
    return html.Div(
        className="space-y-3",
        children=[
            ui.titulo_seccion("Peso del fruto: subida, bajada y olas", "h4"),
            dcc.Dropdown(
                id="fp-peso-clima",
                options=[{"label": etiqueta(c), "value": c} for c in VARIABLES_PRE_PEAK],
                value="TempMin", clearable=False, className="max-w-sm",
            ),
            html.Div(id="fp-peso-body"),
        ],
    )


@callback(
    Output("fp-peso-body", "children"),
    Output("fp-listo-peso-grafico", "data"),
    Input(PANEL_STORE, "data"), Input("fp-peso-clima", "value", allow_optional=True),
)
def _render_peso(panel, variable):
    if panel is None or variable is None:
        return ui.esqueleto_seccion("h-48"), False
    tray = _tray(panel)
    columna = _COLUMNA_PRE_PEAK[variable]
    fig = px.scatter(
        tray, x=columna, y="Cambio neto peso (g)", color="Posición del peak", hover_name="Módulo",
        category_orders={"Posición del peak": ["Inicio", "Medio", "Final"]},
        color_discrete_sequence=[AZUL, "#7f8c8d", ROJO],
    )
    fig.add_hline(y=0, line_color="#888")
    fig.update_layout(
        xaxis_title=f"{etiqueta(variable)}: promedio de 4 semanas pre-peak",
        yaxis_title="cambio neto del peso observado (g)",
    )
    _estilo_figura(fig, 380)

    positivo = int((tray["Cambio neto peso (g)"] > 0).sum())
    negativo = int((tray["Cambio neto peso (g)"] < 0).sum())
    olas = int((tray["Cambios de sentido"] > 0).sum())
    r = float(tray[columna].corr(tray["Cambio neto peso (g)"]))
    return html.Div([
        dcc.Graph(figure=fig, config={"displaylogo": False}),
        ui.semaforo(
            "info",
            f"**La relación es débil en esta exploración:** r = {r:+.2f}. "
            "La nube no basta para afirmar que una exposición pre-peak explique la "
            "caída del peso.",
        ),
        ui.parrafo(
            f"**Lectura dinámica:** en los módulos con suficientes datos, el peso "
            f"termina por encima del inicio en {positivo}, por debajo en {negativo}, y "
            f"presenta al menos un cambio de sentido en {olas}. La nube permite "
            f"comprobar si esas trayectorias cambian junto con {etiqueta(variable)} "
            "antes del peak; la asociación sigue siendo observacional."
        ),
    ], className="space-y-3"), True

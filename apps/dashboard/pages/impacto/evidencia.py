"""Página «Evidencia» de Impacto agronómico — puerto de las Pruebas 1, 2, 3 y 4 de
Evidencia observacional y pruebas de asociación.

Cinco pruebas encadenadas en el Streamlit; acá van cuatro (la Prueba 5, por módulo, tiene
su propia página — ver `pages/impacto/por_modulo.py`). Ninguna toca XGBoost ni SHAP: es
la capa de asociación observada, separada a propósito de «Modelo predictivo».
"""

from __future__ import annotations

import dash
import plotly.graph_objects as go
from dash import dcc, html
from dash_extensions.enrich import Input, Output, callback

from analitica import nucleo
from analitica.config import AZUL, CLIMA, GRIS, ROJO, etiqueta
from components import ui
from servicios.carga import PANEL_STORE

dash.register_page(__name__, path="/impacto/evidencia", name="Evidencia", order=1, grupo="Impacto agronómico")


def layout():
    return html.Div(id="evidencia-contenido", children=ui.esqueleto_pagina())


def _kpis(sem, panel) -> html.Div:
    """Indicadores de lectura rápida, con el mismo patrón visual de General."""
    ver = nucleo.clima.veredicto(sem)
    ef = nucleo.clima.tamano_efectivo(panel.tabla)
    corr = nucleo.clima.correlaciones_semanales(sem)
    parcial = nucleo.clima.correlacion_parcial(sem)
    return ui.fila_kpi([
        ui.kpi(
            "Señal más visible",
            f"{ver.r_mas_alta:+.2f}".replace(".", ","),
            nota=f"{ver.variable_mas_asociada}. Asociación inicial con el kg/ha.",
            serie=corr["r (Pearson)"].abs(),
        ),
        ui.kpi(
            "Señales que se sostienen",
            f"{len(ver.sobreviven_al_control)} / {len(CLIMA)}",
            nota="Variables que siguen asociadas tras controlar la estación.",
            serie=parcial["r control no lineal"].abs(),
        ),
        ui.kpi(
            "Semanas efectivas",
            str(ef.n_semanas),
            nota=f"El clima tiene {ef.n_semanas} observaciones distintas, no {ef.n_celdas}.",
        ),
        ui.kpi(
            "Control de realidad",
            f"{ver.r_placebo:+.2f}".replace(".", ","),
            nota=f"{ver.placebo_mas_fuerte}. Serie inventada que sigue el calendario.",
            serie=[abs(ver.r_mas_alta), abs(ver.r_placebo)],
        ),
    ])


def _respuesta_corta(sem, panel) -> html.Div:
    """La conclusión ejecutiva como card independiente, igual que en General."""
    ver = nucleo.clima.veredicto(sem)
    if ver.hay_relacion_robusta:
        estado = "ok"
        respuesta = (
            "**Sí queda señal después del control.** Se sostienen: "
            f"{', '.join(ver.sobreviven_al_control)}. Son relaciones candidatas para "
            "contrastar en el modelo predictivo, todavía no efectos causales."
        )
    else:
        estado = "aviso"
        respuesta = (
            "**La campaña muestra asociaciones, pero no permite atribuirlas al clima "
            "con seguridad.** La más fuerte —"
            f"{ver.variable_mas_asociada}, "
            f"r = {ver.r_mas_alta:+.2f}— se diluye al descontar el calendario; además, "
            f"una serie inventada («{ver.placebo_mas_fuerte}») llega a "
            f"r = {ver.r_placebo:+.2f}."
        )

    conexion = html.Div(
        className="grid gap-4",
        children=[
            html.Div(
                children=[
                    html.Div(
                        "Este análisis responde",
                        className="text-sm font-semibold text-slate-700",
                    ),
                    html.P(
                        "Qué relaciones aparecen en los datos y cuáles resisten controles "
                        "contra explicaciones engañosas como el calendario.",
                        className="mt-1.5 text-sm leading-relaxed text-slate-600",
                    ),
                ],
            ),
            html.Div(
                children=[
                    html.Div(
                        "Cómo ayuda al modelo",
                        className="text-sm font-semibold text-slate-700",
                    ),
                    html.P(
                        "Propone variables candidatas y advierte qué patrones no deben "
                        "confundirse con señal estable. El modelo predictivo, en su propia "
                        "sección, prueba si esas variables mejoran predicciones fuera de muestra.",
                        className="mt-1.5 text-sm leading-relaxed text-slate-600",
                    ),
                ],
            ),
        ],
    )

    return ui.panel(
        "Respuesta corta",
        ui.semaforo(estado, respuesta),
        conexion,
        ayuda="La conclusión ejecutiva y su relación con el modelo predictivo.",
    )


def _estilo_figura(fig: go.Figure, altura: int) -> go.Figure:
    """Acabado común: gráficos silenciosos que viven dentro de un panel, no otra card."""
    fig.update_layout(
        height=altura,
        margin={"l": 8, "r": 8, "t": 18, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "ui-sans-serif, system-ui, sans-serif", "color": "#475569"},
        hoverlabel={"bgcolor": "#ffffff", "bordercolor": "#d6d3d1"},
    )
    fig.update_xaxes(gridcolor="#e7e5e4", zeroline=False)
    fig.update_yaxes(gridcolor="#f5f5f4", zeroline=False)
    return fig


def _prueba_1(sem) -> html.Div:

    corr = nucleo.clima.correlaciones_semanales(sem)
    d = corr.sort_values("r (Pearson)")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=d.Variable, x=d["r (Pearson)"], orientation="h",
        marker={"color": [ROJO if s else GRIS for s in d.Significativa]},
        error_x={
            "type": "data", "symmetric": False,
            "array": d["IC 95% superior"] - d["r (Pearson)"],
            "arrayminus": d["r (Pearson)"] - d["IC 95% inferior"],
            "color": "#888", "thickness": 1.4,
        },
        hovertemplate="%{y}<br>r = %{x:+.3f}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#888")
    fig.update_layout(xaxis_title="correlación con el kg/ha", xaxis_range=[-1, 1])
    _estilo_figura(fig, 340)
    return html.Div(
        className="space-y-3",
        children=[
            ui.parrafo(
                "El primer vistazo busca qué variables suben o bajan junto con el "
                "rendimiento semanal. **Es una señal para investigar, no una conclusión "
                "agronómica:** todavía no separa el clima del momento de la campaña."
            ),
            ui.escala_correlacion(),
            dcc.Graph(figure=fig, config={"displaylogo": False}),
            ui.plegable(
                "Cómo leerlo y ver el detalle estadístico",
                ui.parrafo(
                    "Cada barra es una variable; su largo muestra la fuerza de la "
                    "asociación. Las **rojas** son estadísticamente significativas y las "
                    "**grises**, no. La línea fina es el intervalo de confianza. Se calcula "
                    f"sobre **{len(sem)} semanas** —las mediciones climáticas distintas—, "
                    "no sobre las celdas repetidas entre módulos."
                ),
                ui.tabla_desde_df(
                    corr, ocultar=["clave"],
                    formato={
                        "r (Pearson)": "{:+.3f}", "p": "{:.4f}",
                        "IC 95% inferior": "{:+.3f}", "IC 95% superior": "{:+.3f}",
                        "Spearman": "{:+.3f}", "p Spearman": "{:.4f}",
                        "Varianza explicada": "{:.1%}",
                    },
                ),
            ),
        ],
    )


def _prueba_2(sem) -> html.Div:

    parcial = nucleo.clima.correlacion_parcial(sem)
    d = parcial.sort_values("r sin controlar")
    fig = go.Figure()
    fig.add_trace(go.Bar(y=d.Variable, x=d["r sin controlar"], orientation="h",
                         name="Sin controlar", marker_color=ROJO, opacity=0.85))
    fig.add_trace(go.Bar(y=d.Variable, x=d["r control no lineal"], orientation="h",
                         name="Descontando el calendario", marker_color=AZUL))
    fig.add_vline(x=0, line_color="#888")
    fig.update_layout(barmode="group", xaxis_title="correlación con el kg/ha",
                      xaxis_range=[-1, 1], legend={"orientation": "h", "y": 1.16})
    _estilo_figura(fig, 380)

    sobreviven = parcial.loc[parcial.Sobrevive, "Variable"].tolist()
    peor = parcial.iloc[0]
    if sobreviven:
        respuesta = f"Sí, en {', '.join(sobreviven)}."
        estado = "ok"
    else:
        respuesta = (
            f"No. {peor.Variable} pasa de r = {peor['r sin controlar']:+.3f} a "
            f"{peor['r control no lineal']:+.3f} (p = {peor['p no lineal']:.2f}), que es "
            "indistinguible de cero."
        )
        estado = "error"

    return html.Div(
        className="space-y-3",
        children=[
            ui.parrafo(
                "La campaña arranca en invierno y termina en verano. La cosecha sube y "
                "baja siguiendo la poda; la temperatura sube y baja siguiendo la "
                "estación. Dos curvas que se mueven juntas correlacionan aunque no tengan "
                "nada que ver entre sí. **La prueba consiste en descontar la forma de la "
                "campaña y ver qué queda.**"
            ),
            dcc.Graph(figure=fig, config={"displaylogo": False}),
            ui.semaforo(estado, f"**Respuesta:** {respuesta}"),
            ui.plegable(
                "Qué se descontó y ver los valores",
                ui.parrafo(
                    "Se resta de ambas series la tendencia común con el número de semana "
                    "y se vuelve a correlacionar lo que sobra. El control es **no lineal** "
                    "porque la cosecha forma una joroba: descontar solo una recta dejaría "
                    "parte de la estacionalidad y haría parecer que la relación sobrevive."
                ),
                ui.tabla_desde_df(
                    parcial, ocultar=["clave"],
                    formato={
                        "r sin controlar": "{:+.3f}", "r control lineal": "{:+.3f}",
                        "p lineal": "{:.4f}", "r control no lineal": "{:+.3f}",
                        "p no lineal": "{:.4f}", "Queda": "{:.0%}",
                    },
                ),
            ),
        ],
    )


def _prueba_4(sem) -> html.Div:

    pl = nucleo.clima.placebo(sem)
    d = pl.sort_values("r con kg/ha")
    fig = go.Figure(go.Bar(
        y=d.Serie, x=d["r con kg/ha"], orientation="h",
        marker={"color": [AZUL if real else ROJO for real in d.Real]},
        hovertemplate="%{y}<br>r = %{x:+.3f}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#888")
    fig.update_layout(xaxis_title="correlación con el kg/ha", xaxis_range=[-1, 1])
    _estilo_figura(fig, 420)

    falsas = pl[~pl.Real]
    top = falsas.loc[falsas["r con kg/ha"].abs().idxmax()]
    reales = pl[pl.Real]
    mejor_real = reales.loc[reales["r con kg/ha"].abs().idxmax()]
    gana = abs(top["r con kg/ha"]) > abs(mejor_real["r con kg/ha"])

    return html.Div(
        className="space-y-3",
        children=[
            ui.parrafo(
                "La forma más directa de mostrar el problema: inventar series que **no "
                "significan nada** y ver cuánto correlacionan. Si una onda matemática le "
                "gana a la temperatura, lo que la correlación mide es la forma de la "
                "curva, no el clima."
            ),
            dcc.Graph(figure=fig, config={"displaylogo": False}),
            html.P("Azul: variables reales medidas en campo. Rojo: series inventadas.",
                   className="text-xs text-slate-500"),
            ui.semaforo(
                "error" if gana else "ok",
                (f"**Sí, y más.** «{top.Serie}» da r = {top['r con kg/ha']:+.3f}, por "
                 f"encima de {mejor_real.Serie} ({mejor_real['r con kg/ha']:+.3f}). Una "
                 "onda que solo conoce la semana describe mejor la forma de la cosecha."
                 if gana else
                 f"**No.** La mejor serie inventada («{top.Serie}») llega a "
                 f"{top['r con kg/ha']:+.3f}, por debajo de {mejor_real.Serie}."),
            ),
            ui.plegable(
                "Qué demuestra este control",
                ui.parrafo(
                    "Las series inventadas son una onda anual, su coseno, una rampa que "
                    "solo cuenta semanas y ruido aleatorio. Ninguna toca el cultivo. Esto "
                    "no demuestra que la temperatura sea irrelevante; demuestra que **con "
                    "esta campaña no se distingue su efecto del calendario**. Para hacerlo "
                    "harían falta varias campañas comparables o calendarios desplazados."
                ),
            ),
        ],
    )


def _prueba_3_shell() -> html.Div:
    """Prueba 3 necesita un desplegable (interactivo) — se resuelve con un callback aparte."""
    return html.Div(
        className="space-y-3",
        children=[
            ui.parrafo(
                "El fruto tarda semanas en formarse, así que sería razonable que el clima "
                "de hace un mes pesara más que el de hoy. Es una hipótesis con sentido "
                "agronómico y hay que probarla."
            ),
            html.Div(
                className="max-w-sm space-y-1.5",
                children=[
                    html.Label("Variable a explorar", className=ui.ROTULO),
                    dcc.Dropdown(
                        id="evidencia-lag-variable",
                        options=[{"label": etiqueta(c), "value": c} for c in CLIMA],
                        value="TempMin",
                        clearable=False,
                    ),
                ],
            ),
            dcc.Graph(id="evidencia-lag-fig", config={"displaylogo": False}),
            html.Div(id="evidencia-lag-veredicto"),
        ],
    )


@callback(Output("evidencia-contenido", "children"), Input(PANEL_STORE, "data"))
def _render(panel):
    if panel is None:
        return ui.esqueleto_pagina()

    sem = nucleo.clima.agregar_por_semana(panel.tabla)
    return html.Div(
        children=[
            ui.encabezado_pagina(
                "¿El clima explica el rendimiento?",
                "Primero observamos las relaciones; después intentamos romperlas con "
                "controles. Solo lo que resiste merece acompañar al modelo predictivo.",
            ),
            html.Div(
                className="space-y-4",
                children=[
                    _kpis(sem, panel),
                    _respuesta_corta(sem, panel),
                    ui.panel(
                        "1 · La relación que aparece a primera vista",
                        _prueba_1(sem),
                        ayuda="Qué variables se mueven junto con el rendimiento semanal.",
                    ),
                    ui.panel(
                        "2 · Separar clima de calendario",
                        _prueba_2(sem),
                        ayuda="Si la relación permanece al descontar la forma de la campaña.",
                    ),
                    ui.panel(
                        "3 · Buscar un efecto con anticipación",
                        _prueba_3_shell(),
                        ayuda="Si el clima de semanas anteriores explica mejor el resultado.",
                    ),
                    ui.panel(
                        "4 · Control de realidad",
                        _prueba_4(sem),
                        ayuda="Comparación contra series inventadas que solo siguen el calendario.",
                    ),
                    ui.panel(
                        "Qué significa cada variable",
                        ui.glosario(list(CLIMA), plano=True),
                        plegable=True,
                        abierto=False,
                        ayuda="Definiciones en lenguaje llano de las variables comparadas.",
                    ),
                ],
            ),
        ],
    )


@callback(
    Output("evidencia-lag-fig", "figure"),
    Output("evidencia-lag-veredicto", "children"),
    Input(PANEL_STORE, "data"),
    Input("evidencia-lag-variable", "value"),
)
def _prueba_3_callback(panel, variable):

    if panel is None or variable is None:
        return go.Figure(), None
    sem = nucleo.clima.agregar_por_semana(panel.tabla)
    lags = nucleo.clima.rezagos(sem)
    d = lags[lags.clave == variable]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d.Rezago, y=d["r bruto"], mode="lines+markers",
                             name="Sin descontar la estación", line={"color": ROJO}))
    fig.add_trace(go.Scatter(x=d.Rezago, y=d["r sin tendencia"], mode="lines+markers",
                             name="Descontando la estación",
                             line={"color": AZUL, "dash": "dot"}))
    fig.add_hline(y=0, line_color="#888")
    fig.update_layout(xaxis_title="semanas de rezago",
                      yaxis_title="correlación con el kg/ha", yaxis_range=[-1, 1],
                      legend={"orientation": "h", "y": 1.16})
    _estilo_figura(fig, 380)

    bruto = d.loc[d["r bruto"].abs().idxmax()]
    limpio = d.loc[d["r sin tendencia"].abs().idxmax()]
    veredicto = html.Div(
        className="space-y-3",
        children=[
            ui.semaforo(
                "aviso",
                "**No se puede afirmar un rezago biológico.** Sin descontar la estación, "
                f"el mejor aparece a {int(bruto.Rezago)} semanas "
                f"(r = {bruto['r bruto']:+.3f}); después del control el máximo cae a "
                f"{limpio['r sin tendencia']:+.3f}.",
            ),
            ui.plegable(
                "Por qué cambia la curva",
                ui.parrafo(
                    "Cuando dos series suben y bajan con la estación, desplazarlas puede "
                    "alinear mejor sus jorobas y aumentar la correlación sin un mecanismo "
                    "físico. La curva punteada repite el cálculo después de descontar esa "
                    "forma: un pico claro allí sería evidencia más convincente."
                ),
            ),
        ],
    )
    return fig, veredicto

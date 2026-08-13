"""Página «Evidencia» de Impacto agronómico — puerto de las Pruebas 1, 2, 3 y 4 de
`dashboard/vistas/clima.py`.

Cinco pruebas encadenadas en el Streamlit; acá van cuatro (la Prueba 5, por módulo, tiene
su propia página — ver `pages/impacto/por_modulo.py`). Ninguna toca XGBoost ni SHAP: es
la capa de asociación observada, separada a propósito de «Modelo predictivo».
"""

from __future__ import annotations

import dash
import plotly.graph_objects as go
from dash import dcc, html
from dash_extensions.enrich import Input, Output, callback

import nucleo
from config import AZUL, CLIMA, GRIS, ROJO, etiqueta
from components import ui
from servicios.carga import PANEL_STORE

dash.register_page(__name__, path="/impacto/evidencia", name="Evidencia", order=1, grupo="Impacto agronómico")


def layout():
    return html.Div(id="evidencia-contenido")


def _cabecera(sem, panel) -> html.Div:
    import nucleo

    ver = nucleo.clima.veredicto(sem)
    ef = nucleo.clima.tamano_efectivo(panel.tabla)
    tarjetas = ui.tarjetas([
        ("Variable más asociada", ver.variable_mas_asociada,
         "La que tiene la correlación más fuerte con el kg/ha, al grano semanal."),
        ("Su correlación", f"{ver.r_mas_alta:+.3f}".replace(".", ","),
         "Coeficiente de Pearson. −1 y +1 son los extremos; 0 es ausencia de relación."),
        ("Sobreviven al control", f"{len(ver.sobreviven_al_control)} de {len(CLIMA)}",
         "Cuántas mantienen una asociación significativa al descontar el calendario."),
        ("Semanas analizadas", str(ef.n_semanas),
         f"El clima tiene {ef.n_semanas} valores distintos, no {ef.n_celdas}: es el "
         "tamaño de muestra real."),
    ])
    if ver.hay_relacion_robusta:
        veredicto = ui.semaforo(
            "ok", f"Tras descontar el calendario siguen en pie: "
            f"{', '.join(ver.sobreviven_al_control)}.",
        )
    else:
        veredicto = ui.semaforo(
            "error",
            "**Ninguna variable climática sobrevive al control del calendario.** La "
            f"asociación más fuerte que se observa —{ver.variable_mas_asociada}, "
            f"r = {ver.r_mas_alta:+.3f}— desaparece al descontar la estación. Y una serie "
            f"inventada sin ningún significado físico («{ver.placebo_mas_fuerte}») "
            f"correlaciona **más fuerte todavía**: r = {ver.r_placebo:+.3f}. Las pruebas "
            "de abajo muestran cómo se llega a esa conclusión.",
        )
    return html.Div([tarjetas, html.Div(veredicto, className="mt-3")])


def _prueba_1(sem) -> html.Div:
    import nucleo

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
    fig.update_layout(height=340, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      xaxis_title="correlación con el kg/ha", xaxis_range=[-1, 1])
    return html.Div(
        className="space-y-3",
        children=[
            ui.titulo_seccion("Prueba 1 · ¿Cuánto correlaciona cada variable?"),
            ui.escala_correlacion(),
            dcc.Graph(figure=fig, config={"displaylogo": False}),
            ui.como_leer(
                "Cada barra es una variable; su largo es la fuerza de la asociación con "
                "el rendimiento. Las **rojas** son estadísticamente significativas "
                "(podría descartarse que sean casualidad); las **grises**, no.\n\n"
                "La línea fina sobre cada barra es el **intervalo de confianza**: el "
                "rango donde estaría el valor real si repitiéramos la campaña. Se calcula "
                f"sobre **{len(sem)} semanas**, que es el número de mediciones climáticas "
                "distintas — no sobre las celdas del panel, porque el mismo valor de "
                "temperatura se repite en todos los módulos de una semana y contarlo "
                "varias veces fingiría una precisión que no existe."
            ),
            ui.tabla_desde_df(
                corr, ocultar=["clave"],
                formato={
                    "r (Pearson)": "{:+.3f}", "p": "{:.4f}", "IC 95% inferior": "{:+.3f}",
                    "IC 95% superior": "{:+.3f}", "Spearman": "{:+.3f}", "p Spearman": "{:.4f}",
                    "Varianza explicada": "{:.1%}",
                },
            ),
        ],
    )


def _prueba_2(sem) -> html.Div:
    import nucleo

    parcial = nucleo.clima.correlacion_parcial(sem)
    d = parcial.sort_values("r sin controlar")
    fig = go.Figure()
    fig.add_trace(go.Bar(y=d.Variable, x=d["r sin controlar"], orientation="h",
                         name="Sin controlar", marker_color=ROJO, opacity=0.85))
    fig.add_trace(go.Bar(y=d.Variable, x=d["r control no lineal"], orientation="h",
                         name="Descontando el calendario", marker_color=AZUL))
    fig.add_vline(x=0, line_color="#888")
    fig.update_layout(height=380, barmode="group",
                      margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      xaxis_title="correlación con el kg/ha", xaxis_range=[-1, 1],
                      legend={"orientation": "h", "y": 1.14})

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
            ui.titulo_seccion("Prueba 2 · ¿Es la temperatura, o es el calendario?"),
            ui.parrafo(
                "La campaña arranca en invierno y termina en verano. La cosecha sube y "
                "baja siguiendo la poda; la temperatura sube y baja siguiendo la "
                "estación. Dos curvas que se mueven juntas correlacionan aunque no tengan "
                "nada que ver entre sí. **La prueba consiste en descontar la forma de la "
                "campaña y ver qué queda.**"
            ),
            dcc.Graph(figure=fig, config={"displaylogo": False}),
            ui.veredicto_de_prueba(
                "¿Queda algo de la asociación cuando se descuenta la estación?",
                respuesta, estado,
                "Se resta de ambas series la tendencia común con el número de semana y se "
                "vuelve a correlacionar lo que sobra.\n\n"
                "**Por qué el control tiene que ser no lineal:** la cosecha no crece en "
                "línea recta, hace una joroba. Descontando solo una recta, buena parte de "
                "la forma queda sin absorber y la correlación parece sobrevivir. La tabla "
                "muestra las dos versiones justamente para que se vea la diferencia: con "
                "control lineal algunas parecen aguantar, con el control correcto ninguna "
                "lo hace.",
            ),
            ui.tabla_desde_df(
                parcial, ocultar=["clave"],
                formato={
                    "r sin controlar": "{:+.3f}", "r control lineal": "{:+.3f}",
                    "p lineal": "{:.4f}", "r control no lineal": "{:+.3f}",
                    "p no lineal": "{:.4f}", "Queda": "{:.0%}",
                },
            ),
        ],
    )


def _prueba_4(sem) -> html.Div:
    import nucleo

    pl = nucleo.clima.placebo(sem)
    d = pl.sort_values("r con kg/ha")
    fig = go.Figure(go.Bar(
        y=d.Serie, x=d["r con kg/ha"], orientation="h",
        marker={"color": [AZUL if real else ROJO for real in d.Real]},
        hovertemplate="%{y}<br>r = %{x:+.3f}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#888")
    fig.update_layout(height=420, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      xaxis_title="correlación con el kg/ha", xaxis_range=[-1, 1])

    falsas = pl[~pl.Real]
    top = falsas.loc[falsas["r con kg/ha"].abs().idxmax()]
    reales = pl[pl.Real]
    mejor_real = reales.loc[reales["r con kg/ha"].abs().idxmax()]
    gana = abs(top["r con kg/ha"]) > abs(mejor_real["r con kg/ha"])

    return html.Div(
        className="space-y-3",
        children=[
            ui.titulo_seccion("Prueba 4 · La prueba del placebo"),
            ui.parrafo(
                "La forma más directa de mostrar el problema: inventar series que **no "
                "significan nada** y ver cuánto correlacionan. Si una onda matemática le "
                "gana a la temperatura, lo que la correlación mide es la forma de la "
                "curva, no el clima."
            ),
            dcc.Graph(figure=fig, config={"displaylogo": False}),
            html.P("Azul: variables reales medidas en campo. Rojo: series inventadas.",
                   className="text-xs text-slate-500"),
            ui.veredicto_de_prueba(
                "¿Una serie sin significado correlaciona igual de fuerte?",
                (f"Sí, y más: «{top.Serie}» da r = {top['r con kg/ha']:+.3f}, por encima "
                 f"de {mejor_real.Serie} ({mejor_real['r con kg/ha']:+.3f}). Una onda que "
                 "solo conoce el número de semana describe la cosecha mejor que cualquier "
                 "medición de campo." if gana else
                 f"No: la mejor serie inventada («{top.Serie}») llega a "
                 f"{top['r con kg/ha']:+.3f}, por debajo de {mejor_real.Serie}."),
                "error" if gana else "ok",
                "Las series inventadas son: una onda senoidal de período anual, su "
                "coseno, una rampa que solo cuenta semanas, y ruido aleatorio puro. "
                "Ninguna tiene contacto con el cultivo.\n\n"
                "**Qué prueba esto.** No que la temperatura sea irrelevante para el "
                "arándano —lo es, y mucho— sino que **con estos datos no se puede "
                "distinguir su efecto del simple paso del calendario**. Para separarlos "
                "harían falta varias campañas con fechas de poda distintas, o módulos con "
                "calendarios desplazados.",
            ),
        ],
    )


def _prueba_3_shell() -> html.Div:
    """Prueba 3 necesita un desplegable (interactivo) — se resuelve con un callback aparte."""
    return html.Div(
        className="space-y-3",
        children=[
            ui.titulo_seccion("Prueba 3 · ¿El clima de hace unas semanas explica mejor?"),
            ui.parrafo(
                "El fruto tarda semanas en formarse, así que sería razonable que el clima "
                "de hace un mes pesara más que el de hoy. Es una hipótesis con sentido "
                "agronómico y hay que probarla."
            ),
            dcc.Dropdown(
                id="evidencia-lag-variable",
                options=[{"label": etiqueta(c), "value": c} for c in CLIMA],
                value="TempMin",
                clearable=False,
                className="max-w-xs",
            ),
            dcc.Graph(id="evidencia-lag-fig", config={"displaylogo": False}),
            html.Div(id="evidencia-lag-veredicto"),
        ],
    )


@callback(Output("evidencia-contenido", "children"), Input(PANEL_STORE, "data"))
def _render(panel):
    if panel is None:
        return ui.semaforo("aviso", "Cargando el panel…")
    import nucleo

    sem = nucleo.clima.agregar_por_semana(panel.tabla)
    return html.Div(
        className="space-y-8",
        children=[
            _cabecera(sem, panel),
            ui.glosario(list(CLIMA)),
            html.Hr(className="border-slate-200"),
            _prueba_1(sem),
            html.Hr(className="border-slate-200"),
            _prueba_2(sem),
            html.Hr(className="border-slate-200"),
            _prueba_3_shell(),
            html.Hr(className="border-slate-200"),
            _prueba_4(sem),
        ],
    )


@callback(
    Output("evidencia-lag-fig", "figure"),
    Output("evidencia-lag-veredicto", "children"),
    Input(PANEL_STORE, "data"),
    Input("evidencia-lag-variable", "value"),
)
def _prueba_3_callback(panel, variable):
    import nucleo

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
    fig.update_layout(height=380, xaxis_title="semanas de rezago",
                      yaxis_title="correlación con el kg/ha", yaxis_range=[-1, 1],
                      margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      legend={"orientation": "h", "y": 1.14})

    bruto = d.loc[d["r bruto"].abs().idxmax()]
    limpio = d.loc[d["r sin tendencia"].abs().idxmax()]
    veredicto = ui.veredicto_de_prueba(
        "¿Hay un rezago con significado biológico?",
        f"No se puede afirmar. Sin descontar la estación el mejor rezago es de "
        f"{int(bruto.Rezago)} semanas (r = {bruto['r bruto']:+.3f}), pero al descontarla "
        f"el máximo cae a {limpio['r sin tendencia']:+.3f}.",
        "aviso",
        "**Por qué la curva roja engaña.** Cuando dos series suben y bajan con la "
        "estación, desplazar una contra la otra puede alinear mejor las jorobas y subir "
        "la correlación sin que exista ningún mecanismo físico. La curva azul repite el "
        "cálculo sobre las series ya descontadas: si ahí apareciera un pico claro en, "
        "digamos, 6 semanas, sería evidencia de un efecto real con rezago. No aparece.",
    )
    return fig, veredicto

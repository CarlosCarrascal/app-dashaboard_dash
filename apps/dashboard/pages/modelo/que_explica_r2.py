"""Página «Qué explica el R²».

El R² no se lee como un número suelto: primero se fija el techo de la información,
después se comprueba si el modelo generaliza y recién entonces se mira qué familias o
variables sostienen esa predicción. Las lecturas pesadas se calculan al abrir cada pestaña
y quedan guardadas en memoria para que volver a ella sea inmediato.
"""

from __future__ import annotations

from threading import Lock

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html
from dash_extensions.enrich import Input, Output, callback
from plotly.subplots import make_subplots

from analitica import nucleo
from analitica.config import AZUL, FEATURES, GRIS, NARANJA, ROJO
from analitica.visualizaciones import graficos as g
from components import ui
from servicios.carga import PANEL_STORE

dash.register_page(__name__, path="/modelo/r2", name="Qué explica el R²", order=0, grupo="Modelo predictivo")

BLOQUES = {
    "techo": "Techo",
    "grupos": "Grupos",
    "aporte": "Variables",
    "esquemas": "Validación",
}

_PESADOS = ("grupos", "aporte", "esquemas")
_R2_DATA: dict[str, dict[str, object]] = {}
_R2_LOCK = Lock()


def layout():
    return html.Div(
        className="space-y-4",
        children=[
            ui.encabezado_pagina(
                "¿Qué parte aprende el modelo y qué parte solo memoriza?",
                "El R² depende de la información disponible y de cómo se separan las semanas. "
                "Aquí distinguimos el techo, la generalización y el aporte de cada señal.",
            ),
            html.Div(id="r2-resumen"),
            dcc.Tabs(
                id="r2-tabs",
                value="techo",
                children=[dcc.Tab(label=nombre, value=clave) for clave, nombre in BLOQUES.items()],
            ),
            dcc.Loading(
                id="r2-loading",
                type="dot",
                color=AZUL,
                children=html.Div(id="r2-contenido", className="pt-4"),
            ),
        ],
    )


def _estilo_figura(fig: go.Figure, altura: int) -> go.Figure:
    fig.update_layout(
        height=altura,
        margin={"l": 8, "r": 18, "t": 28, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "ui-sans-serif, system-ui, sans-serif", "color": "#475569"},
        hoverlabel={"bgcolor": "#ffffff", "bordercolor": "#d6d3d1"},
    )
    fig.update_xaxes(gridcolor="#e7e5e4", zeroline=False)
    fig.update_yaxes(gridcolor="#f5f5f4", zeroline=False)
    return fig


def _panel_key(panel) -> str:
    tabla = panel.tabla
    columnas = [c for c in ("nsem", "celda", "KgHa") if c in tabla.columns]
    huella = int(pd.util.hash_pandas_object(tabla[columnas], index=True).sum())
    return f"{tabla.shape}:{huella}"


def _calcular_pesado(panel, bloque: str):
    calculos = {
        "grupos": lambda: nucleo.aporte_por_grupo(panel.tabla),
        "aporte": lambda: nucleo.aporte_por_variable(panel.tabla),
        # Los baselines descriptivos de tabla_validacion se calculan sobre toda la
        # muestra y no son comparables con las filas fuera de muestra. La página muestra
        # solo los siete cruces del plan, que sí comparten una pregunta de validación.
        "esquemas": lambda: nucleo.tabla_validacion(panel.tabla, referencias=()),
    }
    key = _panel_key(panel)
    with _R2_LOCK:
        dato = _R2_DATA.get(key, {}).get(bloque)
    if dato is not None:
        return dato, None

    try:
        resultado = calculos[bloque]()
    except Exception as exc:  # pragma: no cover - salvaguarda de la interfaz
        return None, str(exc)

    with _R2_LOCK:
        _R2_DATA.setdefault(key, {})[bloque] = resultado
    return resultado, None


def _dato_pesado(panel, bloque: str):
    if bloque not in _PESADOS:
        return None, f"Bloque desconocido: {bloque}"
    return _calcular_pesado(panel, bloque)


def _kpis(pct_entre: float, pct_dentro: float, n: int, semanas: int) -> html.Div:
    return ui.fila_kpi([
        ui.kpi(
            "Techo entre semanas",
            f"{pct_entre:.0f}%",
            nota="Parte de la variación que puede ver el clima semanal.",
        ),
        ui.kpi(
            "Variación semanal",
            f"{pct_dentro:.0f}%",
            nota="Diferencias entre módulos que el clima común no distingue.",
        ),
        ui.kpi(
            "Muestra comparable",
            f"{n} / {semanas}",
            nota="Filas / semanas con las 7 variables completas.",
        ),
        ui.kpi(
            "Variables predictoras",
            str(len(FEATURES)),
            nota="Señales que recibe el modelo general.",
        ),
    ])


def _respuesta_corta(pct_entre: float, pct_dentro: float) -> html.Div:
    mensaje = (
        "**El R² no se interpreta solo.** Primero se fija el techo de la información y "
        "después se valida con semanas fuera. La cifra conservadora y la comparación entre "
        "particiones están en la pestaña Validación, donde no se mezclan con el diagnóstico "
        "descriptivo."
    )
    conexion = html.Div(
        className="grid gap-4",
        children=[
            html.Div([
                html.Div("Este análisis responde", className="text-sm font-semibold text-slate-700"),
                html.P(
                    "Cuánto generaliza el modelo cuando cambia la semana y cuánto de su "
                    "rendimiento puede venir de reconocer la forma de la campaña.",
                    className="mt-1.5 text-sm leading-relaxed text-slate-600",
                ),
            ]),
            html.Div([
                html.Div("Cómo ayuda al modelo", className="text-sm font-semibold text-slate-700"),
                html.P(
                    "Fija el número que se debe reportar, separa la señal física del calendario "
                    "y evita leer SHAP o aportes marginales como si fueran efectos causales.",
                    className="mt-1.5 text-sm leading-relaxed text-slate-600",
                ),
            ]),
        ],
    )
    return ui.panel(
        "Respuesta corta",
        ui.semaforo(
            "aviso",
            mensaje + " El techo de las variables que son iguales para todo el "
            f"fundo es {pct_entre:.0f}%: el {pct_dentro:.0f}% restante ocurre entre módulos y "
            "requiere variables que los distingan, como el riego.",
        ),
        conexion,
        ayuda="Qué número resume la capacidad predictiva y qué límite tiene.",
    )


@callback(
    Output("r2-resumen", "children"),
    Input(PANEL_STORE, "data"),
)
def _render_resumen(panel):
    if panel is None:
        return ui.semaforo("aviso", "Cargando el panel…")
    pct_entre, pct_dentro = nucleo.descomposicion_varianza(panel.tabla)
    base = panel.tabla.dropna(subset=[*FEATURES, "KgHa"])
    return html.Div(
        className="space-y-4",
        children=[
            _kpis(pct_entre, pct_dentro, len(base), int(base.nsem.nunique())),
            _respuesta_corta(pct_entre, pct_dentro),
        ],
    )


def _techo(panel) -> html.Div:
    pct_entre, pct_dentro = nucleo.descomposicion_varianza(panel.tabla)
    fig = _estilo_figura(g.reparto_varianza(pct_entre, pct_dentro), 180)
    return ui.panel(
        "1 · El clima tiene un techo antes de entrenar",
        ui.parrafo(
            "Antes de mirar qué variable gana, hay que preguntar cuánta variación puede "
            "ver una medición semanal. Como el clima es un valor común para los módulos, "
            "solo puede explicar diferencias entre semanas; no las diferencias que existen "
            "entre módulos dentro de una misma semana."
        ),
        dcc.Graph(figure=fig, config={"displaylogo": False}),
        ui.semaforo(
            "aviso",
            f"**{pct_dentro:.0f}% de la variación ocurre dentro de la semana.** Ninguna "
            "variable climática semanal puede explicar ese tramo por sí sola. El riego sí "
            "varía por módulo, por eso se evalúa como una familia aparte.",
        ),
        ui.plegable(
            "Cómo leer este techo",
            ui.parrafo(
                "La barra no es el R² del modelo ni una promesa de precisión. Es una "
                "descomposición descriptiva del rendimiento: entre semanas frente a dentro "
                "de la semana. Sirve para saber qué pregunta puede responder el clima y qué "
                "pregunta exige datos por módulo —poda, suelo, variedad, edad o manejo."
            ),
        ),
        ayuda="Límite informativo de las variables que son constantes dentro de cada semana.",
    )


def _grupos(grupos) -> html.Div:
    orden = grupos.sort_values("Aporte marginal del grupo")
    fig = go.Figure(go.Bar(
        x=orden["Aporte marginal del grupo"],
        y=orden.Familia,
        orientation="h",
        marker_color=AZUL,
        text=[f"{v:+.3f}" for v in orden["Aporte marginal del grupo"]],
        textposition="outside",
        hovertemplate="%{y}<br>aporte marginal = %{x:+.3f}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#94a3b8")
    fig.update_layout(
        xaxis_title="pérdida de R² al retirar la familia",
        xaxis_range=[0, max(0.45, float(orden["Aporte marginal del grupo"].max()) * 1.2)],
    )
    _estilo_figura(fig, 300)
    mejor = grupos.iloc[0]
    return ui.panel(
        "2 · La familia explica más que una columna aislada",
        ui.parrafo(
            "Las variables climáticas se mueven juntas. Por eso retirar una columna puede "
            "hacer que otra absorba su señal; retirar una familia completa es una lectura más "
            "estable del bloque de información que usa el modelo."
        ),
        dcc.Graph(figure=fig, config={"displaylogo": False}),
        ui.semaforo(
            "info",
            f"**La familia con mayor aporte marginal es {mejor.Familia}** "
            f"({float(mejor['Aporte marginal del grupo']):+.3f}). Esto mide cuánto pierde "
            "este modelo al quitar el bloque completo bajo la misma partición; no es un "
            "efecto agronómico de esa familia.",
        ),
        ui.plegable(
            "Ver las métricas de cada familia",
            ui.tabla_desde_df(
                grupos,
                formato={
                    "R² solo grupo": "{:+.3f}",
                    "R² del modelo sin grupo": "{:+.3f}",
                    "Aporte marginal del grupo": "{:+.3f}",
                },
            ),
            ui.parrafo(
                "Las tres columnas no responden la misma pregunta: una familia puede "
                "predecir poco por sí sola y aun así ser importante dentro del modelo "
                "porque completa la información de otra familia."
            ),
        ),
        ayuda="Ablación de familias completas con las mismas filas y semanas.",
    )


def _aporte(aporte) -> html.Div:
    orden = aporte.sort_values("R² sola")
    fig = make_subplots(
        rows=1,
        cols=2,
        shared_yaxes=True,
        horizontal_spacing=0.16,
        subplot_titles=("Predice sola", "Aporte dentro del modelo"),
    )
    fig.add_trace(
        go.Bar(
            x=orden["R² sola"],
            y=orden.Variable,
            orientation="h",
            marker_color=AZUL,
            hovertemplate="%{y}<br>R² sola = %{x:+.3f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=orden["Aporte marginal"],
            y=orden.Variable,
            orientation="h",
            marker_color=[ROJO if v < 0 else NARANJA for v in orden["Aporte marginal"]],
            hovertemplate="%{y}<br>aporte marginal = %{x:+.3f}<extra></extra>",
        ),
        row=1,
        col=2,
    )
    fig.update_xaxes(zeroline=True, zerolinecolor="#94a3b8", gridcolor="#e7e5e4")
    fig.update_layout(showlegend=False)
    _estilo_figura(fig, 410)
    mejor_sola = aporte.loc[aporte["R² sola"].idxmax()]
    mejor_aporte = aporte.iloc[0]
    return ui.panel(
        "3 · Predecir sola no es lo mismo que aportar al modelo",
        ui.parrafo(
            "Aquí se comparan dos preguntas con la misma partición y las mismas filas. "
            "La primera columna muestra qué variable predice por sí sola; la segunda, cuánto "
            "pierde el modelo completo cuando se retira esa variable. Si los órdenes cambian, "
            "la señal compartida entre variables está siendo repartida de otra manera."
        ),
        dcc.Graph(figure=fig, config={"displaylogo": False}),
        ui.semaforo(
            "aviso",
            f"**La mejor variable sola es {mejor_sola.Variable}** "
            f"(R² = {float(mejor_sola['R² sola']):+.3f}); la que más aporta dentro del "
            f"conjunto es {mejor_aporte.Variable} ({float(mejor_aporte['Aporte marginal']):+.3f}). "
            "Ninguno de los dos números es un efecto causal ni una prioridad automática de manejo.",
        ),
        ui.plegable(
            "Ver los valores estadísticos",
            ui.tabla_desde_df(
                aporte,
                formato={
                    "r (Pearson)": "{:+.3f}",
                    "r² descriptivo": "{:.1%}",
                    "R² sola": "{:+.3f}",
                    "R² del modelo sin ella": "{:+.3f}",
                    "Aporte marginal": "{:+.3f}",
                },
            ),
            ui.parrafo(
                f"La comparación usa «{aporte.attrs['particion']}» sobre las mismas "
                f"{aporte.attrs['n']} filas y {aporte.attrs['semanas']} semanas. "
                "La correlación de Pearson y el R² descriptivo no son métricas fuera de muestra."
            ),
        ),
        ayuda="Comparación entre capacidad aislada y pérdida marginal dentro del modelo.",
    )


def _esquemas(tabla) -> html.Div:
    orden = tabla.copy()
    colores = []
    for esquema in orden.Esquema:
        if esquema.startswith("(a)"):
            colores.append(ROJO)
        elif esquema.startswith("(d)"):
            colores.append(AZUL)
        elif esquema.startswith("(e)"):
            colores.append(NARANJA)
        elif esquema.startswith("(g)"):
            colores.append("#7c3aed")
        else:
            colores.append(GRIS)
    fig = go.Figure(go.Bar(
        x=orden["R²"],
        y=orden.Esquema,
        orientation="h",
        marker_color=colores,
        text=[f"{v:+.3f}" for v in orden["R²"]],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{y}<br>R² = %{x:+.3f}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#94a3b8")
    fig.update_layout(
        xaxis_title="R² fuera de muestra",
        xaxis_range=[
            min(-0.05, float(orden["R²"].min()) - 0.05),
            max(0.68, float(orden["R²"].max()) + 0.08),
        ],
        yaxis={"categoryorder": "array", "categoryarray": orden.Esquema.tolist()},
    )
    _estilo_figura(fig, 430)

    def fila(prefijo: str):
        return orden.loc[orden.Esquema.str.startswith(prefijo)].iloc[0]

    semana = fila("(c)")
    bloque = fila("(d)")
    calendario = fila("(e)")
    clima = fila("(f)")
    riego = fila("(g)")
    return ui.panel(
        "4 · El número cambia cuando cambia la pregunta",
        ui.parrafo(
            "El mismo modelo de siete variables no tiene un único R². Las filas (a)–(d) "
            "cambian la separación de las semanas; las filas (e)–(g) comparan conjuntos de "
            "variables bajo la misma partición por semana. Solo se deben comparar dentro de "
            "cada uno de esos bloques."
        ),
        dcc.Graph(figure=fig, config={"displaylogo": False}),
        ui.semaforo(
            "aviso",
            f"**La cifra conservadora es (d): R² = {float(bloque['R²']):+.3f}.** Al dejar una "
            f"semana fuera, (c) sube a {float(semana['R²']):+.3f} porque todavía puede usar "
            f"semanas vecinas. En la misma partición semanal, el calendario solo da "
            f"{float(calendario['R²']):+.3f}, el clima {float(clima['R²']):+.3f} y el riego "
            f"{float(riego['R²']):+.3f}; no son comparaciones causales, sino auditorías del "
            "conjunto de información que recibe el predictor.",
        ),
        ui.plegable(
            "Cómo leer los siete esquemas",
            ui.parrafo(
                "**(a) Aleatorio** es optimista: pone módulos de una misma semana en "
                "entrenamiento y prueba. **(b)** pregunta por un módulo nuevo. **(c)** deja "
                "una semana fuera, pero permite interpolar entre vecinas. **(d)** deja bloques "
                "contiguos de diez semanas y es la prueba más exigente de esta página. "
                "**(e)–(g)** mantienen la partición semanal y cambian las variables: sirven "
                "para ver si el calendario, el clima o el riego aportan información distinta."
            ),
            ui.tabla_desde_df(
                orden,
                formato={"R²": "{:+.3f}", "MAE (kg/ha)": "{:.0f}"},
            ),
        ),
        ayuda="Comparación de generalización y de conjuntos de variables bajo particiones explícitas.",
    )


@callback(
    Output("r2-contenido", "children"),
    Input(PANEL_STORE, "data"),
    Input("r2-tabs", "value"),
)
def _render(panel, bloque):
    if panel is None:
        return ui.semaforo("aviso", "Cargando el panel…")
    if bloque == "techo":
        return _techo(panel)
    dato, error = _dato_pesado(panel, bloque)
    if error:
        return ui.semaforo("error", f"No se pudo calcular esta lectura: {error}")
    return {"grupos": _grupos, "aporte": _aporte, "esquemas": _esquemas}[bloque](dato)

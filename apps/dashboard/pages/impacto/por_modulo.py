"""Página «Por módulo».

Pregunta guía: ¿la relación que vemos en el fundo se repite dentro de cada módulo?
La respuesta muestra por qué el calendario de cosecha puede cambiar el signo de una
correlación, y qué significa eso antes de llevar una señal al modelo predictivo.
"""

from __future__ import annotations

import dash
from dash import dcc, html
from dash_extensions.enrich import Input, Output, callback

from analitica import nucleo
from analitica.config import CLIMA, etiqueta
from analitica.visualizaciones import graficos as g
from components import ui
from servicios.carga import PANEL_STORE

dash.register_page(__name__, path="/impacto/por-modulo", name="Por módulo", order=2, grupo="Impacto agronómico")


def layout():
    return html.Div(id="por-modulo-contenido")


def _estilo_figura(fig, altura: int):
    """Acabado común de los gráficos dentro de las cards narrativas."""
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


def _formato_p(p: float) -> str:
    return "p < 0,001" if p < 0.001 else f"p = {p:.3f}".replace(".", ",")


def _kpis(porm, dep) -> html.Div:
    fila = dep.iloc[0]
    r = float(fila["r (inicio de cosecha ↔ correlación del módulo)"])
    inicio = porm.Inicio.astype(int)
    semanas = porm.Semanas.astype(int)
    return ui.fila_kpi([
        ui.kpi(
            "Módulos analizados",
            str(len(porm)),
            nota="Módulos con al menos 10 semanas de cosecha observada.",
        ),
        ui.kpi(
            "Inicio de cosecha",
            f"{inicio.min()}–{inicio.max()}",
            nota="Rango de semanas en que comienza la cosecha entre módulos.",
            serie=sorted(inicio.tolist()),
        ),
        ui.kpi(
            "Ventana por módulo",
            f"{semanas.min()}–{semanas.max()}",
            nota="Semanas observadas por módulo; la mediana es "
                 f"{int(semanas.median())}.",
            serie=sorted(semanas.tolist()),
        ),
        ui.kpi(
            "Calendario ↔ señal",
            f"{r:+.2f}".replace(".", ","),
            nota=f"{fila.Variable}; {_formato_p(float(fila.p))}.",
            serie=dep["r (inicio de cosecha ↔ correlación del módulo)"].abs(),
        ),
    ])


def _respuesta_corta(porm, dep) -> html.Div:
    fila = dep.iloc[0]
    r = float(fila["r (inicio de cosecha ↔ correlación del módulo)"])
    variable = str(fila.Variable)
    positivos = int((porm[variable] > 0).sum())
    negativos = int((porm[variable] < 0).sum())
    respuesta = (
        f"**La señal no es estable por módulo.** Para {variable}, la asociación entre "
        f"el inicio de cosecha y la correlación del módulo es **r = {r:+.2f}** "
        f"({_formato_p(float(fila.p))}). Hay {positivos} módulos con signo positivo "
        f"y {negativos} con signo negativo: el calendario cambia la lectura."
    )
    conexion = html.Div(
        className="grid gap-4",
        children=[
            html.Div(
                children=[
                    html.Div("Este análisis responde", className="text-sm font-semibold text-slate-700"),
                    html.P(
                        "Si una relación climática se repite dentro de cada módulo o si "
                        "cambia según la ventana en la que ese módulo empieza a cosechar.",
                        className="mt-1.5 text-sm leading-relaxed text-slate-600",
                    ),
                ],
            ),
            html.Div(
                children=[
                    html.Div("Cómo ayuda al modelo", className="text-sm font-semibold text-slate-700"),
                    html.P(
                        "Evita tratar una correlación aislada por módulo como un efecto "
                        "fisiológico. La señal debe acompañarse de variables de calendario "
                        "o de tiempo biológico antes de probar su aporte predictivo.",
                        className="mt-1.5 text-sm leading-relaxed text-slate-600",
                    ),
                ],
            ),
        ],
    )
    return ui.panel(
        "Respuesta corta",
        ui.semaforo("aviso", respuesta),
        conexion,
        ayuda="La conclusión ejecutiva y el límite de interpretar correlaciones por módulo.",
    )


def _detalle_dependencia(dep) -> html.Div:
    clave_r = "r (inicio de cosecha ↔ correlación del módulo)"
    detalle = dep[["Variable", clave_r, "p", "Significativa"]].copy()
    detalle["Significativa"] = detalle["Significativa"].map({True: "Sí", False: "No"})
    return ui.tabla_desde_df(
        detalle,
        formato={clave_r: "{:+.3f}", "p": "{:.4f}"},
    )


@callback(Output("por-modulo-contenido", "children"), Input(PANEL_STORE, "data"))
def _render(panel):
    if panel is None:
        return ui.semaforo("aviso", "Cargando el panel…")

    porm = nucleo.clima.por_modulo(panel.tabla)
    dep = nucleo.clima.signo_depende_de_la_ventana(porm)
    if porm.empty or dep.empty:
        return ui.semaforo("aviso", "No hay suficientes semanas para comparar los módulos.")

    columnas = [etiqueta(c) for c in CLIMA if etiqueta(c) in porm.columns]
    fila = dep.iloc[0]
    clave = str(fila.clave)
    variable = str(fila.Variable)
    r = float(fila["r (inicio de cosecha ↔ correlación del módulo)"])
    mapa = _estilo_figura(g.mapa_por_modulo(porm, columnas), max(420, 26 * len(porm)))
    ventana = _estilo_figura(g.ventana_de_cosecha(porm, clave=clave), 440)

    return html.Div(
        children=[
            ui.encabezado_pagina(
                "¿La relación se repite en todos los módulos?",
                "Una señal puede verse clara en el fundo y cambiar de signo dentro de cada "
                "módulo. Primero vemos el patrón; después comprobamos qué parte explica el "
                "calendario de cosecha.",
            ),
            html.Div(
                className="space-y-4",
                children=[
                    _kpis(porm, dep),
                    _respuesta_corta(porm, dep),
                    ui.panel(
                        "1 · La misma señal no se comporta igual en todos los módulos",
                        ui.parrafo(
                            "Cada fila es un módulo y cada columna una variable climática. "
                            "El color muestra la correlación dentro de ese módulo: si una "
                            "columna fuera uniforme, la relación sería consistente. Cuando "
                            "aparecen azules y rojos mezclados, el signo depende de la ventana "
                            "de cosecha y no basta para hablar de un efecto agronómico."
                        ),
                        dcc.Graph(figure=mapa, config={"displaylogo": False}),
                        ui.plegable(
                            "Cómo leer el mapa",
                            ui.parrafo(
                                "**Azul** significa correlación negativa: cuando la variable "
                                "sube, el kg/ha tiende a bajar dentro de ese módulo. **Rojo** "
                                "significa correlación positiva. El mapa no dice qué variable "
                                "causa el rendimiento; muestra si el mismo patrón se repite o "
                                "se invierte entre módulos."
                            ),
                        ),
                        ayuda="Comparación de las correlaciones dentro de cada módulo.",
                    ),
                    ui.panel(
                        "2 · La ventana de cosecha explica el cambio de signo",
                        ui.parrafo(
                            f"Para {variable}, el eje horizontal marca cuándo empieza a "
                            "cosechar cada módulo y el vertical muestra su correlación con "
                            f"el kg/ha. La relación entre ambos es r = {r:+.2f}: los módulos "
                            f"que empiezan más tarde tienden a ser {('más positivos' if r >= 0 else 'más negativos')} "
                            "porque se solapan con otra parte de la curva estacional."
                        ),
                        dcc.Graph(figure=ventana, config={"displaylogo": False}),
                        ui.semaforo(
                            "aviso",
                            "**No es que el mismo clima produzca efectos opuestos.** "
                            "Cada módulo observa una porción distinta de la campaña; al "
                            "correlacionar dentro de esa ventana, el calendario puede cambiar "
                            "el signo.",
                        ),
                        ui.plegable(
                            "Ver el diagnóstico completo",
                            ui.parrafo(
                                "La tabla ordena las variables por cuánto se asocia el "
                                "inicio de cosecha con su correlación dentro del módulo. "
                                "Los valores p ayudan a distinguir un patrón sistemático de "
                                "una diferencia accidental entre pocos módulos."
                            ),
                            _detalle_dependencia(dep),
                        ),
                        ayuda="Relación entre el inicio de cosecha y el signo de cada asociación.",
                    ),
                    ui.panel(
                        "3 · Qué significa para la lectura del modelo",
                        ui.parrafo(
                            "Por módulo sirve como control de realidad: muestra si una señal "
                            "es estable o si está mezclada con el calendario. No es todavía el "
                            "modelo predictivo ni una estimación causal; es el filtro que evita "
                            "entregarle al modelo una relación que solo funciona porque dos "
                            "curvas estacionales se superponen."
                        ),
                        ui.subseccion(
                            "La regla práctica",
                            ui.parrafo(
                                "Antes de usar una correlación por módulo como variable "
                                "candidata, hay que comprobar si conserva el signo al controlar "
                                "la semana de inicio, la poda o un reloj térmico como GDD."
                            ),
                        ),
                        ui.subseccion(
                            "Lo que sí puede aportar",
                            ui.parrafo(
                                "Ayuda a detectar módulos con ventanas atípicas, separar "
                                "cohortes y decidir qué variables de tiempo deben entrar en la "
                                "sección del modelo predictivo."
                            ),
                        ),
                        ayuda="Límite de interpretación y puente hacia el modelo predictivo.",
                    ),
                ],
            ),
        ],
    )

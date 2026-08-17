"""Página «Pregunta, datos y límites».

Primera pantalla del tablero: qué pregunta responde, qué no, y a qué grano está medida
cada variable. Sin gráficos propios — es la única página que no depende de `graficos.py`.
"""

from __future__ import annotations

import dash
from dash import html
from dash_extensions.enrich import Input, Output, callback

from analitica import nucleo
from components import ui
from servicios.carga import PANEL_STORE

dash.register_page(__name__, path="/", name="Pregunta, datos y límites", order=0, grupo="General")


def layout():
    return html.Div(id="pregunta-contenido")


def _kpis(tabla) -> html.Div:
    """Fila de KPIs con la forma de cada serie al lado del número.

    Las series son reales y semanales (`nsem`), calculadas acá mismo con un `groupby` sobre
    el panel ya cargado — no hay callback ni figura de plotly por tarjeta. Ninguna tarjeta
    muestra variación porcentual: 2025 es la única campaña del panel, así que un «+x % vs.
    el año pasado» no tendría con qué compararse.
    """
    por_semana = tabla.groupby("nsem")
    kgha_semanal = por_semana.KgHa.mean()
    semanas = sorted(tabla.nsem.unique())
    return ui.fila_kpi([
        ui.kpi(
            "Celdas módulo × semana",
            ui.entero(len(tabla)),
            nota="Cada fila es un módulo observado en una semana concreta.",
            serie=por_semana.size(),
        ),
        ui.kpi(
            "Módulos",
            str(tabla.celda.nunique()),
            nota="Con cosecha registrada en 2025. La serie muestra cuántos estaban "
                 "activos cada semana.",
            serie=por_semana.celda.nunique(),
        ),
        ui.kpi(
            "Semanas",
            str(tabla.nsem.nunique()),
            nota=f"Con al menos una cosecha, de la {semanas[0]} a la {semanas[-1]}.",
        ),
        ui.kpi(
            "kg/ha promedio",
            ui.entero(tabla.KgHa.mean()),
            nota=f"Promedio simple sobre las celdas. Por semana va de "
                 f"{ui.entero(kgha_semanal.min())} a {ui.entero(kgha_semanal.max())}.",
            serie=kgha_semanal,
        ),
    ])


def _que_hace() -> html.Div:
    return html.Div(
        className="space-y-4",
        children=[
            ui.parrafo(
                "La pregunta principal es: **¿qué impacto agronómico tiene cada variable "
                "climática sobre los kg/ha, los frutos y el peso del fruto?** Con la "
                "campaña 2025 el tablero cuantifica asociaciones y aporte predictivo; "
                "todavía no identifica un efecto causal por variable."
            ),
            ui.subseccion(
                "Lo que sí responde",
                ui.parrafo(
                    "Qué variables acompañan a las semanas de mayor rendimiento y cuánto de "
                    "esa relación se confunde con el calendario; qué aporta cada variable, o "
                    "cada grupo de variables, a un modelo evaluado fuera de muestra; de dónde "
                    "sale el número de una celda concreta; y qué tan confiable es cada cifra, "
                    "con qué tamaño de muestra detrás."
                ),
            ),
            ui.subseccion(
                "Lo que no responde",
                ui.parrafo(
                    "Cuántos kilos se van a cosechar la semana que viene, ni si subir el riego "
                    "aumentaría el rendimiento. Tampoco qué variable **causa** qué: son datos "
                    "observacionales de una sola campaña. Ni el efecto por fase fenológica "
                    "observada: 'M_Poda' aporta un reloj proxy, pero todavía no trae la fase "
                    "medida."
                ),
            ),
        ],
    )


def _tabla(columnas: list[str], filas: list[tuple]) -> html.Table:
    """Tabla de pocas filas con el estilo del tablero: cabecera en rótulo, filas sin marco.

    No es `ui.tabla_desde_df` porque estas dos tablas son literales escritas a mano (no
    salen de un DataFrame) y no necesitan formato por columna.
    """
    return html.Table(
        className="w-full text-left text-sm",
        children=[
            html.Thead(html.Tr([
                html.Th(c, className=f"border-b {ui.BORDE} pb-2 pr-4 {ui.ROTULO}") for c in columnas
            ])),
            html.Tbody([
                html.Tr([
                    html.Td(str(v), className="border-b border-stone-100 py-2 pr-4 text-slate-600")
                    for v in fila
                ])
                for fila in filas
            ]),
        ],
    )


def _estado_analitico() -> html.Div:
    filas = [
        ("Asociación", "¿Qué se mueve junto con el resultado?", "Sí", "Impacto agronómico"),
        ("Aporte predictivo", "¿Qué mejora un modelo fuera de muestra?", "Sí", "Qué explica el R²"),
        ("Efecto agronómico", "¿Cuánto cambiaría el resultado al intervenir la exposición?",
         "Todavía no", "Marco metodológico y referencias"),
    ]
    return html.Div(
        className="space-y-3",
        children=[
            _tabla(["Resultado", "Pregunta", "Estado", "Dónde verlo"], filas),
            ui.semaforo(
                "aviso",
                "La evidencia actual indica que la asociación climática está confundida con "
                "el calendario. M_Poda permite controlarlo con días desde poda, pero como la "
                "fecha original está a nivel de lote y se resume al módulo, el control "
                "todavía es proxy. Eso no dice que el clima no importe: dice qué parte queda "
                "identificada con estos datos.",
            ),
        ],
    )


def _granularidad(panel) -> html.Div:
    ef = nucleo.clima.tamano_efectivo(panel.tabla)
    filas = [
        ("Rendimiento (kg/ha)", "módulo × semana", "sí", len(panel.tabla)),
        ("Riego (L/planta)", "módulo × semana", "sí", len(panel.tabla)),
        ("Temp. máx / mín", "semana", "no", ef.n_semanas),
        ("Amplitud térmica", "semana", "no", ef.n_semanas),
        ("Radiación y ETo", "semana", "no", ef.n_semanas),
        ("DPV", "semana", "no", ef.n_semanas),
    ]
    return html.Div(
        className="space-y-6",
        children=[
            html.Div(
                className="space-y-3",
                children=[
                    _tabla(["Variable", "Se mide por", "¿Distingue módulos?", "Valores distintos"], filas),
                    ui.parrafo(
                        f"Las hojas de clima **Temp Max-Min**, **Rad y ET** y **DPV**, traen "
                        f"**un valor por semana**, no por módulo: el de la semana 1 se aplica a "
                        f"los {panel.n_modulos} módulos de la semana 1, el de la 2 a los de la 2, "
                        "y así."
                    ),
                ]
            ),

            # Insights numéricos anclados visualmente
            html.Div(
                className="flex flex-col sm:flex-row gap-8",
                children=[
                    html.Div(
                        className="flex-1 border-l-2 border-stone-200 pl-4",
                        children=[
                            html.Div("N APARENTE", className=ui.ROTULO),
                            html.Div(ui.entero(ef.n_celdas), className=f"mt-1 text-[1.75rem] leading-none {ui.CIFRA}"),
                            html.Div("Filas del panel.", className="mt-2 text-sm text-slate-500 leading-snug"),
                        ]
                    ),
                    html.Div(
                        className="flex-1 border-l-2 border-stone-200 pl-4",
                        children=[
                            html.Div("N EFECTIVO", className=ui.ROTULO),
                            html.Div(ui.entero(ef.n_semanas), className=f"mt-1 text-[1.75rem] leading-none {ui.CIFRA}"),
                            html.Div("Mediciones climáticas distintas.", className="mt-2 text-sm text-slate-500 leading-snug"),
                        ]
                    ),
                    html.Div(
                        className="flex-1 border-l-2 border-stone-200 pl-4",
                        children=[
                            html.Div("INFLACIÓN SI SE USA N EQUIVOCADO", className=ui.ROTULO),
                            html.Div(f"{ef.factor_inflacion:.1f}×", className=f"mt-1 text-[1.75rem] leading-none {ui.CIFRA}"),
                            html.Div("Cuánto más estrecho saldría un intervalo de confianza sobre celdas en vez de semanas.", className="mt-2 text-sm text-slate-500 leading-snug"),
                        ]
                    ),
                ]
            ),

            # El razonamiento completo se pliega
            ui.plegable(
                "Por qué importa",
                ui.parrafo(
                    "**¿Es un problema del dato?** No. Dentro de un mismo fundo la "
                    "temperatura y el déficit de presión de vapor no cambian de forma "
                    "apreciable de un módulo al de al lado: medirlos por módulo daría "
                    "el mismo número repetido. La estructura **representa bien la "
                    "realidad física**.\n\n"
                    "**¿Tiene consecuencias?** Dos, y ambas importan:\n\n"
                    f"1. **El tamaño de muestra real es {ef.n_semanas}, no "
                    f"{ef.n_celdas}.** Cada valor de clima se repite "
                    f"{ef.n_celdas / ef.n_semanas:.1f} veces en el panel. Un intervalo "
                    f"de confianza calculado sobre las celdas saldría "
                    f"**{ef.factor_inflacion:.1f} veces más estrecho** de lo correcto. "
                    "Todas las cifras de *Impacto agronómico* usan el n correcto.\n"
                    "2. **Ninguna variable climática puede explicar las diferencias "
                    "entre módulos de una misma semana**, porque vale lo mismo para "
                    "todos. Eso no es una limitación del análisis sino aritmética."
                ),
                ui.parrafo(
                    "**¿Convendría enriquecer el dato por módulo?** Para temperatura y DPV, "
                    "no: no hay variación espacial que capturar dentro del fundo. Lo que sí "
                    "falta son variables que **sí** distingan un módulo de otro — fecha de "
                    "poda, variedad, edad de planta, suelo. Ésas son las que podrían explicar "
                    "el tramo que hoy queda sin explicar."
                ),
            ),
        ],
    )


@callback(Output("pregunta-contenido", "children"), Input(PANEL_STORE, "data"))
def _render(panel):
    if panel is None:
        return ui.semaforo("aviso", "Cargando el panel…")
    tabla = panel.tabla
    return html.Div(
        children=[
            ui.encabezado_pagina(
                "Qué responde este tablero",
                "Clima, riego y rendimiento del fundo en la campaña 2025, medido por módulo "
                "y semana. Empieza por acá: define el alcance de todo lo demás.",
            ),
            html.Div(
                className="space-y-4",
                children=[
                    _kpis(tabla),
                    ui.panel(
                        "Alcance del análisis",
                        _que_hace(),
                        ayuda="Qué preguntas quedan identificadas con estos datos y cuáles no.",
                    ),
                    ui.panel(
                        "Qué está medido hoy",
                        _estado_analitico(),
                        ayuda="Asociación y aporte predictivo sí; efecto causal todavía no.",
                    ),
                    ui.panel(
                        "A qué grano se mide cada variable",
                        _granularidad(panel),
                        ayuda="El clima viene por semana, el rendimiento por módulo y semana. "
                              "Eso tiene consecuencias sobre el tamaño de muestra.",
                    ),
                    # Plegado por omisión: es material de consulta, no parte del hilo que
                    # la página cuenta de arriba a abajo.
                    ui.panel(
                        "Qué significa cada variable",
                        ui.glosario(plano=True),
                        plegable=True,
                        abierto=False,
                        ayuda="Definición en lenguaje llano de cada variable del panel.",
                    ),
                ],
            ),
        ],
    )

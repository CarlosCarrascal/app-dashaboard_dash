"""Página «Pregunta, datos y límites» — puerto de `dashboard/vistas/resumen.py::render`.

Primera pantalla del tablero: qué pregunta responde, qué no, y a qué grano está medida
cada variable. Sin gráficos propios — es la única página que no depende de `graficos.py`.
"""

from __future__ import annotations

import dash
from dash import html
from dash_extensions.enrich import Input, Output, callback

import nucleo
from components import ui
from servicios.carga import PANEL_STORE

dash.register_page(__name__, path="/", name="Pregunta, datos y límites", order=0, grupo="General")


def layout():
    return html.Div(id="pregunta-contenido")


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
            html.Div(
                className="grid grid-cols-2 gap-4",
                children=[
                    ui.caja(
                        html.P("✓ Lo que sí responde", className="mb-2 font-semibold text-emerald-700"),
                        ui.parrafo(
                            "- Qué variables acompañan a las semanas de mayor rendimiento\n"
                            "- Cuánto de esa relación se confunde con el calendario\n"
                            "- Qué aporta cada variable o grupo a un modelo fuera de muestra\n"
                            "- De dónde sale el número de una celda concreta\n"
                            "- Qué tan confiable es cada cifra, y con qué tamaño de muestra"
                        ),
                    ),
                    ui.caja(
                        html.P("✕ Lo que NO responde", className="mb-2 font-semibold text-rose-700"),
                        ui.parrafo(
                            "- Cuántos kilos se van a cosechar la semana que viene\n"
                            "- Si subir el riego aumentaría el rendimiento\n"
                            "- Qué variable **causa** qué — son datos observacionales de una campaña\n"
                            "- El efecto por fase fenológica observada — M_Poda aporta un reloj "
                            "proxy, pero todavía no trae la fase fenológica medida"
                        ),
                    ),
                ],
            ),
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
            ui.titulo_seccion("Qué está medido hoy"),
            html.Table(
                className="w-full text-left text-sm",
                children=[
                    html.Thead(html.Tr([html.Th(c, className="border-b py-1 pr-4") for c in
                                        ["Resultado", "Pregunta", "Estado", "Dónde verlo"]])),
                    html.Tbody([
                        html.Tr([html.Td(v, className="border-b py-1 pr-4") for v in fila])
                        for fila in filas
                    ]),
                ],
            ),
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
        className="space-y-3",
        children=[
            ui.titulo_seccion("A qué grano se mide cada variable"),
            ui.parrafo(
                f"Las hojas de clima —**Temp Max-Min**, **Rad y ET** y **DPV**— traen "
                f"**un valor por semana**, no por módulo: el de la semana 1 se aplica a "
                f"los {panel.n_modulos} módulos de la semana 1, el de la 2 a los de la 2, "
                "y así."
            ),
            html.Table(
                className="w-full text-left text-sm",
                children=[
                    html.Thead(html.Tr([html.Th(c, className="border-b py-1 pr-4") for c in
                                        ["Variable", "Se mide por", "¿Distingue módulos?", "Valores distintos"]])),
                    html.Tbody([
                        html.Tr([html.Td(str(v), className="border-b py-1 pr-4") for v in fila])
                        for fila in filas
                    ]),
                ],
            ),
            html.Div(
                className="grid grid-cols-[3fr_2fr] gap-4",
                children=[
                    ui.semaforo(
                        "info",
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
                        "todos. Eso no es una limitación del análisis sino aritmética.",
                    ),
                    html.Div(
                        className="space-y-3",
                        children=[
                            ui.tarjetas([
                                ("n aparente", ui.entero(ef.n_celdas), "Filas del panel"),
                                ("n efectivo", ui.entero(ef.n_semanas), "Mediciones climáticas distintas"),
                            ]),
                            ui.caja(
                                html.Div("Inflación si se usa el n equivocado", className="text-xs text-slate-500"),
                                html.Div(f"{ef.factor_inflacion:.1f}×", className="mt-1 text-2xl font-semibold"),
                            ),
                        ],
                    ),
                ],
            ),
            ui.parrafo(
                "**¿Convendría enriquecer el dato por módulo?** Para temperatura y DPV, "
                "no: no hay variación espacial que capturar dentro del fundo. Lo que sí "
                "falta son variables que **sí** distingan un módulo de otro — fecha de "
                "poda, variedad, edad de planta, suelo. Ésas son las que podrían explicar "
                "el tramo que hoy queda sin explicar."
            ),
        ],
    )


@callback(Output("pregunta-contenido", "children"), Input(PANEL_STORE, "data"))
def _render(panel):
    if panel is None:
        return ui.semaforo("aviso", "Cargando el panel…")
    tabla = panel.tabla
    return html.Div(
        className="space-y-6",
        children=[
            ui.tarjetas([
                ("Celdas módulo × semana", ui.entero(len(tabla)), "Cada fila es un módulo en una semana concreta."),
                ("Módulos", str(panel.n_modulos), "Con cosecha registrada en 2025."),
                ("Semanas", str(panel.n_semanas), "Semanas del año con al menos una cosecha."),
                ("kg/ha promedio", ui.entero(tabla.KgHa.mean()), "Promedio simple sobre las celdas del panel."),
            ]),
            _que_hace(),
            _estado_analitico(),
            _granularidad(panel),
            ui.glosario(),
        ],
    )

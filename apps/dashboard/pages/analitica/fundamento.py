from __future__ import annotations

import dash
from dash import html

from components import ui
from pages.analitica._comun import datos, estado_fuente, panel_glosario, tabla

dash.register_page(
    __name__,
    path="/analitica/fundamento",
    name="Fundamento científico",
    order=8,
    grupo="Plataforma analítica",
)

# La matriz completa tiene 15 campos y no cabe legible. Se muestran los que responden
# «¿de qué cultivo habla?» y «¿me sirve acá?»; el resto vive en el catálogo versionado.
COLUMNAS_CATALOGO = [
    "id",
    "titulo",
    "anio",
    "cultivo_variedad",
    "ubicacion",
    "metodo",
    "transferibilidad",
    "uso_en_plataforma",
    "doi",
]


def layout():
    estado = datos()
    catalogo = estado["catalogo"]
    agronomicos = 0
    if not catalogo.empty and "ubicacion" in catalogo:
        agronomicos = int(catalogo.ubicacion.notna().sum())
    return html.Div(
        className="space-y-4",
        children=[
            ui.encabezado_pagina(
                "En qué literatura se apoya la plataforma",
                "Qué estudios respaldan las hipótesis y los métodos, y hasta dónde sus "
                "resultados se pueden trasladar a Sekoya Pop en Trujillo.",
            ),
            estado_fuente(estado),
            ui.semaforo(
                "info",
                "**La literatura aporta la pregunta, no el número.** Un ensayo hecho en otra "
                "variedad, otra edad de planta y otro clima puede indicar que el riego afecta "
                "el peso del fruto, y esa hipótesis vale. Lo que no se puede es copiar su "
                "coeficiente y aplicarlo acá: la magnitud tiene que salir de los datos de "
                "este fundo y comprobarse contra cosecha real."
                + (
                    f"\n\nDel total de estudios del catálogo, **{agronomicos} son ensayos "
                    "agronómicos de campo**; el resto sustenta los métodos estadísticos y de "
                    "gobierno, no afirmaciones sobre el cultivo."
                    if agronomicos
                    else ""
                ),
            ),
            ui.panel(
                "1 · Estudios del catálogo",
                tabla(
                    catalogo,
                    COLUMNAS_CATALOGO,
                    limite=30,
                    vacio="No se pudo leer el catálogo científico.",
                    como_leer=(
                        "La columna que decide es **¿se puede trasladar acá?**. Casi siempre "
                        "dice algo como «alta para el protocolo, baja para los coeficientes»: "
                        "significa que conviene copiar cómo midieron, no cuánto midieron.\n\n"
                        "**Cultivo y variedad** y **lugar del estudio** son los que permiten "
                        "juzgar esa distancia. Un ensayo en Bluetta bajo clima templado no "
                        "describe el comportamiento de Sekoya Pop en la costa peruana, por "
                        "buena que sea su metodología.\n\n"
                        "**Para qué se usa** indica qué parte de la plataforma se apoya en "
                        "ese estudio, para poder rastrear cualquier decisión hasta su fuente."
                    ),
                ),
                ayuda="Literatura versionada con su evaluación de transferibilidad.",
            ),
            ui.panel(
                "2 · El caso de CA244NI",
                ui.parrafo(
                    "Es el estudio más cercano a esta operación, y por eso conviene ser "
                    "preciso sobre qué aporta. Describe cómo estandarizar el censo, cómo "
                    "capacitar a quien mide y cómo descomponer el volumen en sus piezas, y "
                    "reporta una mejora de asertividad. Eso es lo que la plataforma toma."
                ),
                ui.parrafo(
                    "Lo que no aporta es una ecuación reproducible: no publica los cortes "
                    "temporales con que se validó ni el error separado por fundo o por plazo. "
                    "Sin eso no se puede convertir en el modelo oficial, porque no habría "
                    "forma de comprobar si sigue funcionando cuando cambian las condiciones."
                ),
                ayuda="Qué se toma y qué no se toma del estudio local de referencia.",
            ),
            panel_glosario(["transferibilidad", "clase_evidencia"]),
        ],
    )

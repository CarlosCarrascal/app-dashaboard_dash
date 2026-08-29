"""Relaciones: la evidencia de qué se mueve junto a qué, y de cuánto.

Esta página es el **taller**: la matriz completa de cruces, cómo cambia cada relación al
mover el desfase, el tamaño de los efectos en unidades reales y el recuento de todo lo que
se descartó. Lo que se puede **afirmar** con esa evidencia —y hasta dónde llega cada
afirmación— se publica en Descubrimientos; duplicarlo acá haría que las dos páginas se
contradijeran al primer cambio.

El contenido vive en `_relaciones/`: textos, formato, análisis, gráficos y paneles por
separado. Acá solo queda el orden en que se presentan.
"""

from __future__ import annotations

import dash
from dash import html

from components import ui
from pages.analitica._comun import datos, estado_fuente, panel_glosario
from pages.analitica._relaciones import paneles
from pages.analitica._relaciones.analisis import hallazgos, matriz_completa, resumen_barrido

dash.register_page(
    __name__,
    path="/analitica/relaciones",
    name="Relaciones",
    order=1,
    grupo="Plataforma analítica",
)


def _seccion(numero: str, titulo: str, subtitulo: str) -> html.Div:
    return html.Div(
        className="mt-8 border-t-2 border-slate-300 pt-5",
        children=[
            html.H2(
                f"{numero} · {titulo}",
                className="text-xl font-semibold tracking-tight text-slate-900",
            ),
            html.P(subtitulo, className="mt-1 max-w-3xl text-sm text-slate-500"),
        ],
    )


def layout():
    estado = datos()
    encontrados = hallazgos(estado)
    matriz = matriz_completa(estado)
    barrido = resumen_barrido(estado)
    return html.Div(
        className="space-y-4",
        children=[
            ui.encabezado_pagina(
                "Relaciones",
                "Qué se mueve junto a qué en el cultivo, con cuánto desfase y de qué tamaño "
                "es el efecto. La evidencia detrás de lo que se publica en Descubrimientos.",
            ),
            estado_fuente(estado),
            paneles.kpis(encontrados, barrido),
            paneles.sintesis(encontrados),
            _seccion(
                "1",
                "Todo contra todo",
                "La matriz completa: cada variable medida contra cada resultado, en nueve "
                "desfases. Lo que sobrevivió a los filtros y lo que no.",
            ),
            ui.panel(
                "Mapa de relaciones",
                paneles.panel_matriz(matriz),
                ayuda="Correlación del mejor desfase de cada par que superó los filtros.",
            ),
            ui.panel(
                "Cuándo se nota cada relación",
                paneles.panel_desfases(matriz),
                ayuda="Perfil de la correlación al mover el desfase semana a semana.",
            ),
            _seccion(
                "2",
                "De qué tamaño es cada efecto",
                "Las mismas relaciones traducidas a kilos, gramos y puntos de descarte. Una "
                "correlación no dice si algo importa; una magnitud sí.",
            ),
            ui.panel(
                "Efectos en unidades reales",
                paneles.panel_efectos(encontrados),
                ayuda="Cambio al pasar del cuarto más bajo al más alto del predictor.",
            ),
            paneles.tabla_solidos(encontrados),
            paneles.tabla_hipotesis(encontrados),
            # Las tres lecciones hablan de correlaciones y de magnitudes, que es justo lo
            # que se acaba de ver. Estaban detrás del embudo, donde no venían a cuento.
            ui.panel(
                "Cómo no leer mal estos números",
                paneles.panel_lecciones(),
                ayuda="Casos concretos de interpretación equivocada y por qué lo son.",
            ),
            _seccion(
                "3",
                "Cuánto se descartó",
                "El recuento del filtrado. Sin esto no se puede juzgar si lo hallado es "
                "señal o casualidad.",
            ),
            ui.panel(
                "El embudo de filtros",
                paneles.panel_filtrado(barrido),
                ayuda="Cuántos cruces caen en cada etapa, contra los esperados por azar.",
            ),
            _seccion(
                "4",
                "Qué necesita el pronóstico",
                "Pregunta distinta de la matriz: no qué se mueve junto a qué, sino qué "
                "grupos de variables hacen que el modelo acierte.",
            ),
            ui.panel(
                "Aporte real de cada grupo",
                paneles.panel_importancia(estado),
                ayuda="Importancia medida quitándole información al modelo.",
            ),
            _seccion(
                "5",
                "Qué cambiar en la forma de medir",
                "Los límites de arriba, leídos al derecho: dónde invertir para responder lo "
                "que hoy no se puede.",
            ),
            ui.panel(
                "Prioridades de medición",
                paneles.panel_medicion(),
                ayuda="Qué invertir para responder mejor las preguntas del negocio.",
            ),
            ui.panel(
                "Inventario de lo que se mide",
                paneles.panel_inventario(),
                plegable=True,
                abierto=False,
                ayuda="Lo que entra al análisis y lo que no existe.",
            ),
            panel_glosario(
                [
                    "estimacion",
                    "n_efectivo",
                    "clase_evidencia",
                    "plantas",
                    "frutos_por_planta",
                    "peso_baya_g",
                    "mae_kg",
                ]
            ),
        ],
    )

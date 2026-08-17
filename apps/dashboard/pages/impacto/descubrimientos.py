"""Página «Descubrimientos» — contenido a definir.

Es la página narrativa estilo `Analisis_Sekoya_Pop_Presentacion.pptx` (pregunta →
hallazgo → gráfico → implicación) que le gusta a los directivos. A diferencia de las
demás páginas pendientes, acá el contenido mismo — no solo la interfaz — está por
decidirse: qué preguntas del Sekoya Pop se pueden responder hoy con los datos y el
pipeline honesto (`nucleo/clima.py`, partición `por_bloque`), y cuáles quedan pendientes
por falta de datos. Ver la conversación de diseño para el porqué de no copiar los R²
del Sekoya Pop (0,75-0,90) tal cual — ese análisis no usa la partición honesta.
"""

from __future__ import annotations

import dash
from dash import html

from components import ui

dash.register_page(
    __name__, path="/impacto/descubrimientos", name="Descubrimientos",
    order=4, grupo="Impacto agronómico",
)


def layout():
    return html.Div(
        ui.semaforo(
            "info",
            "**Contenido pendiente de definir**, no solo de portar. Antes de escribir "
            "esta página hay que decidir, pregunta por pregunta del Sekoya Pop "
            "(paradoja del agua, estrés combinado, fotosíntesis, concentración de "
            "nutrientes, reloj térmico), qué responde hoy el pipeline honesto de este "
            "tablero y con qué número — no reusar los R² del multi-agente sin pasar por "
            "la partición `por_bloque`.",
        ),
        className="space-y-4",
    )

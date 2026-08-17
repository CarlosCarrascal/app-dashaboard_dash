"""Página «Por módulo».

¿Pasa lo mismo en todos los módulos? Revela que el signo de la correlación lo fija el
calendario de cosecha de cada módulo, no la fisiología.
"""

from __future__ import annotations

import dash
from dash import dcc, html
from dash_extensions.enrich import Input, Output, callback

from analitica.visualizaciones import graficos as g
from analitica import nucleo
from analitica.config import CLIMA, etiqueta
from components import ui
from servicios.carga import PANEL_STORE

dash.register_page(__name__, path="/impacto/por-modulo", name="Por módulo", order=2, grupo="Impacto agronómico")


def layout():
    return html.Div(id="por-modulo-contenido")


@callback(Output("por-modulo-contenido", "children"), Input(PANEL_STORE, "data"))
def _render(panel):
    if panel is None:
        return ui.semaforo("aviso", "Cargando el panel…")

    porm = nucleo.clima.por_modulo(panel.tabla)
    dep = nucleo.clima.signo_depende_de_la_ventana(porm)
    columnas = [etiqueta(c) for c in CLIMA if etiqueta(c) in porm.columns]

    contenido = [
        ui.parrafo(
            "Si la relación fuera fisiológica, debería repetirse en cada módulo por "
            "separado. Y en gran medida se repite… salvo en unos pocos, que son los que "
            "delatan el mecanismo."
        ),
        dcc.Graph(figure=g.mapa_por_modulo(porm, columnas), config={"displaylogo": False}),
        ui.como_leer(
            "Cada fila es un módulo y cada columna una variable. **Azul** = correlación "
            "negativa (cuando la variable sube, el rendimiento baja); **rojo** = "
            "positiva. Si una columna fuera del mismo color de arriba abajo, la relación "
            "sería consistente en todo el fundo."
        ),
        dcc.Graph(figure=g.ventana_de_cosecha(porm), config={"displaylogo": False}),
    ]

    if len(dep):
        fila = dep.iloc[0]
        r = fila["r (inicio de cosecha ↔ correlación del módulo)"]
        contenido.append(
            ui.veredicto_de_prueba(
                "¿Qué decide el signo de la correlación en cada módulo?",
                f"Cuándo empieza a cosechar. La correlación entre «semana de inicio» y "
                f"«correlación del módulo» es r = {r:+.3f} (p = {fila.p:.4f}) para "
                f"{fila.Variable}: los módulos que arrancan tarde tienden a invertir el "
                "signo.",
                "error" if fila.p < 0.05 else "aviso",
                "**El razonamiento.** Los módulos que arrancan tarde cosechan mientras la "
                "temperatura sube, así que en ellos temperatura y cosecha suben juntas: "
                "correlación positiva. Los que arrancan temprano cosechan mientras la "
                "temperatura baja: correlación negativa.\n\n"
                "Mismo fundo, mismo termómetro, misma semana — y el signo se invierte "
                "según el calendario del módulo. Si la temperatura fuera la causa, un "
                "módulo que cosecha con más calor debería rendir **menos**, no más.",
            )
        )
    contenido.append(
        ui.tabla_desde_df(
            dep, ocultar=["clave"],
            formato={"r (inicio de cosecha ↔ correlación del módulo)": "{:+.3f}", "p": "{:.4f}"},
        )
    )
    return html.Div(contenido, className="space-y-4")

"""Página «Qué explica el R²» — puerto completo de `dashboard/vistas/validacion.py`.

Cuatro bloques detrás de una pestaña, igual que el Streamlit: el barato (techo) se
calcula siempre; los tres que entrenan varios modelos solo se calculan cuando esa pestaña
está activa, no las cuatro de una — antes esta sección tardaba medio minuto en aparecer
aunque alguien solo quisiera ver el reparto de varianza.
"""

from __future__ import annotations

import dash
from dash import dcc, html
from dash_extensions.enrich import Input, Output, callback

import graficos as g
import nucleo
from config import FEATURES
from components import ui
from servicios.carga import PANEL_STORE

dash.register_page(__name__, path="/modelo/r2", name="Qué explica el R²", order=0, grupo="Modelo predictivo")

BLOQUES = {
    "techo": "Techo estructural",
    "grupos": "Importancia por grupos",
    "aporte": "Aporte de cada variable",
    "esquemas": "Esquemas de validación",
}


def layout():
    return html.Div(
        className="space-y-4",
        children=[
            dcc.Tabs(
                id="r2-tabs", value="techo",
                children=[dcc.Tab(label=v, value=k) for k, v in BLOQUES.items()],
            ),
            html.Div(id="r2-contenido", className="pt-4"),
        ],
    )


def _techo(panel) -> html.Div:
    pct_entre, pct_dentro = nucleo.descomposicion_varianza(panel.tabla)
    ef = nucleo.clima.tamano_efectivo(panel.tabla)
    return html.Div(
        className="space-y-3",
        children=[
            ui.titulo_seccion("Cuánto puede explicar el clima, como máximo"),
            ui.tarjetas([
                ("Variación entre semanas", f"{pct_entre:.0f}%", "La parte que una variable semanal podría llegar a explicar."),
                ("Variación entre módulos", f"{pct_dentro:.0f}%", "Ocurre dentro de una misma semana. El clima no la puede tocar."),
                ("Mediciones de clima", str(ef.n_semanas), f"Frente a {ef.n_celdas} celdas en el panel."),
            ]),
            dcc.Graph(figure=g.reparto_varianza(pct_entre, pct_dentro), config={"displaylogo": False}),
            ui.semaforo(
                "aviso",
                f"El clima es un solo valor por semana, igual para los {panel.n_modulos} "
                "módulos — y así corresponde, porque la temperatura y el DPV no varían "
                "de forma apreciable dentro del fundo. La consecuencia es aritmética, no "
                "un defecto de medición: **ninguna variable climática puede explicar el "
                f"{pct_dentro:.0f}% de la variación que ocurre entre módulos en la misma "
                "semana.** Ese tramo solo lo puede explicar algo que distinga un módulo "
                "de otro — fecha de poda, variedad, edad de planta, suelo, manejo.",
            ),
            ui.como_leer(
                "La barra reparte toda la variación del rendimiento en dos partes.\n\n"
                "- **Entre semanas:** cuánto se debe a que unas semanas rinden más que "
                "otras. Es el techo de cualquier variable que valga lo mismo para todo "
                "el fundo.\n"
                "- **Entre módulos:** cuánto se debe a que, en la misma semana, unos "
                "módulos rinden más que otros. Para explicar esto hace falta una "
                "variable que distinga módulos, y la única disponible es el riego.\n\n"
                "No es una limitación del análisis: es aritmética. Una variable "
                "constante dentro de un grupo no puede explicar diferencias dentro de "
                "ese grupo."
            ),
        ],
    )


def _aporte(panel) -> html.Div:
    aporte = nucleo.aporte_por_variable(panel.tabla)
    mejor = aporte.iloc[0]
    return html.Div(
        className="space-y-3",
        children=[
            ui.titulo_seccion("El R² es del modelo entero, no de cada variable"),
            ui.caja(
                html.Div(f"R² del modelo con las {len(FEATURES)} variables juntas", className="text-xs text-slate-500"),
                html.Div(f"{aporte.attrs['completo']:+.3f}", className="mt-1 text-2xl font-semibold"),
            ),
            html.P(
                "El R² **no se reparte** entre variables: no es aditivo, y la suma de "
                f"los individuales no da el total. Medido con «{aporte.attrs['particion']}» "
                f"sobre las mismas {aporte.attrs['n']} filas y {aporte.attrs['semanas']} semanas.",
                className="text-xs text-slate-500",
            ),
            ui.tabla_desde_df(aporte, formato={
                "r (Pearson)": "{:+.3f}", "r² descriptivo": "{:.1%}", "R² sola": "{:+.3f}",
                "R² del modelo sin ella": "{:+.3f}", "Aporte marginal": "{:+.3f}",
            }),
            ui.semaforo(
                "info",
                f"**La variable más valiosa del modelo es {mejor.Variable}** (aporte "
                f"marginal {mejor['Aporte marginal']:+.3f}), pese a tener una "
                f"correlación cruda de solo {mejor['r (Pearson)']:+.3f}. El orden por "
                "correlación y el orden por aporte son casi opuestos. Esto describe "
                "utilidad para el modelo, no una palanca causal.",
            ),
            ui.como_leer(
                "Cada columna responde una pregunta distinta:\n\n"
                "- **`r (Pearson)`** — cuánto acompaña la variable al rendimiento. Es "
                "descripción sobre los mismos datos con que se calculó.\n"
                "- **`r² descriptivo`** — el cuadrado del anterior: qué porcentaje de "
                "la variación acompaña.\n"
                "- **`R² sola`** — qué predice esa variable **por sí misma** en semanas "
                "que no vio. Negativa significa que predice peor que el simple "
                "promedio.\n"
                "- **`Aporte marginal`** — cuánto pierde el modelo completo si se le "
                "quita. Sirve para auditar este modelo, pero **no es el efecto "
                "agronómico**.\n\n"
                "Una variable puede correlacionar fuerte y no aportar nada, porque otra "
                "ya lleva esa información; y al revés."
            ),
        ],
    )


def _grupos(panel) -> html.Div:
    grupos = nucleo.aporte_por_grupo(panel.tabla)
    return html.Div(
        className="space-y-3",
        children=[
            ui.titulo_seccion("Importancia por familias de variables"),
            ui.caja(
                html.Div("R² del modelo completo", className="text-xs text-slate-500"),
                html.Div(f"{grupos.attrs['completo']:+.3f}", className="mt-1 text-2xl font-semibold"),
            ),
            html.P(
                f"Ablación con «{grupos.attrs['particion']}», usando las mismas "
                f"{grupos.attrs['n']} filas y {grupos.attrs['semanas']} semanas en todas "
                "las comparaciones.",
                className="text-xs text-slate-500",
            ),
            ui.tabla_desde_df(grupos, formato={
                "R² solo grupo": "{:+.3f}", "R² del modelo sin grupo": "{:+.3f}",
                "Aporte marginal del grupo": "{:+.3f}",
            }),
            ui.como_leer(
                "Las variables climáticas están muy correlacionadas. Quitarlas de una "
                "en una permite que otra columna absorba la señal compartida; "
                "quitarlas como familia mide mejor cuánto dependía el modelo de ese "
                "bloque.\n\n"
                "- **R² solo grupo:** cuánto predice esa familia sin ayuda de las "
                "demás.\n"
                "- **R² sin grupo:** cuánto conserva el modelo al retirar toda la "
                "familia.\n"
                "- **Aporte marginal:** diferencia frente al modelo completo.\n\n"
                "Los grupos tampoco son efectos causales y sus aportes no se suman al "
                "R² total.",
                "Por qué mirar grupos antes que variables aisladas",
            ),
        ],
    )


def _esquemas(panel) -> html.Div:
    tabla = nucleo.tabla_validacion(panel.tabla)
    return html.Div(
        className="space-y-3",
        children=[
            ui.titulo_seccion("El mismo modelo, medido de varias maneras"),
            html.P(
                "Un R² alto medido mal no vale nada. La diferencia entre estas filas "
                "es el hallazgo, no ninguna de ellas por separado.",
                className="text-xs text-slate-500",
            ),
            ui.tabla_desde_df(tabla, formato={"R²": "{:+.3f}", "MAE (kg/ha)": "{:.0f}"}),
            ui.como_leer(
                "**Los baselines** son predictores sin modelo, y marcan el piso: si un "
                "modelo no le gana a «predecir siempre el promedio», no está midiendo "
                "nada.\n\n"
                "**Los esquemas (a) a (g)** son el mismo modelo evaluado con distintas "
                "formas de separar entrenamiento de prueba:\n"
                "- **(a) al azar** infla el resultado, porque mete módulos de la misma "
                "semana en los dos lados y al modelo le alcanza con recordar el "
                "promedio semanal.\n"
                "- **(c) dejando una semana fuera** es más honesto, pero todavía puede "
                "interpolar entre las semanas vecinas.\n"
                "- **(d) dejando un bloque de diez semanas** es el exigente: sin "
                "vecinas, no hay nada que interpolar. **Es el número que hay que "
                "mirar.**\n"
                "- **(e) solo el número de semana** no usa ninguna medición física. Si "
                "le gana al clima, el clima no está aportando nada que el almanaque no "
                "diga.\n\n"
                "**MAE** es el error medio en kg/ha: cuánto se equivoca en promedio."
            ),
        ],
    )


@callback(Output("r2-contenido", "children"), Input(PANEL_STORE, "data"), Input("r2-tabs", "value"))
def _render(panel, bloque):
    if panel is None:
        return ui.semaforo("aviso", "Cargando el panel…")
    return {
        "techo": _techo, "grupos": _grupos, "aporte": _aporte, "esquemas": _esquemas,
    }.get(bloque, _techo)(panel)

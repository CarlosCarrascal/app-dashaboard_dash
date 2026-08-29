from __future__ import annotations

import dash
import plotly.express as px
from dash import dcc, html

from components import ui
from pages.analitica._comun import datos, estado_fuente, panel_glosario, tabla

dash.register_page(
    __name__,
    path="/analitica/backtesting",
    name="Backtesting",
    order=6,
    grupo="Plataforma analítica",
)

# Se muestran en dos tandas: primero lo que responde «¿cuánto se equivoca?», después lo
# que responde «¿es creíble el rango?». Las 18 columnas juntas eran ilegibles.
COLUMNAS_ERROR = [
    "modelo",
    "banda_horizonte",
    "n",
    "wape",
    "mase",
    "mae_kg",
    "sesgo_pct",
    "rmsse",
    "r2",
]
COLUMNAS_RANGO = [
    "modelo",
    "banda_horizonte",
    "cobertura_80",
    "ancho_intervalo_kg",
    "interval_score_80",
    "pinball_p10",
    "pinball_p50",
    "pinball_p90",
]
# `base_plantas_evaluada` no va acá: es texto, así que se persiste como contexto de la
# métrica y no como métrica, y su valor es el mismo en todas las filas. Se explica una vez
# en el `como_leer` del panel en lugar de repetirse por fila.
COLUMNAS_COMPONENTES = [
    "modelo",
    "banda_horizonte",
    "mae_frutos_por_planta",
    "sesgo_pct_frutos_por_planta",
    "n_frutos_por_planta",
    "mae_peso_baya_g",
    "sesgo_pct_peso_baya_g",
    "n_peso_baya_g",
    "residuo_identidad_pct",
]


def layout():
    estado = datos()
    metricas = estado["metricas"].copy()
    figura = px.bar()
    if not metricas.empty and "mase" in metricas:
        figura = px.bar(
            metricas,
            x="modelo",
            y="mase",
            color="banda_horizonte",
            barmode="group",
            labels={
                "mase": "Error frente al método simple",
                "modelo": "Modelo",
                "banda_horizonte": "Uso previsto",
            },
        )
        figura.add_hline(y=1, line_dash="dot", line_color="#94a3b8")
    figura.update_layout(
        template="plotly_white", height=380, margin={"l": 30, "r": 20, "t": 20, "b": 80}
    )
    return html.Div(
        className="space-y-4",
        children=[
            ui.encabezado_pagina(
                "Cómo se ha equivocado el pronóstico",
                "Cada modelo se pone a pronosticar semanas del pasado sin dejarle ver lo que "
                "vino después, y se compara con lo que realmente se cosechó.",
            ),
            estado_fuente(estado),
            ui.semaforo(
                "info",
                "**Qué es esta prueba.** Se retrocede en el tiempo, se le pide a cada modelo "
                "que pronostique una semana que todavía no había ocurrido, y recién después "
                "se compara contra la cosecha real. Ningún modelo ve el resultado que tiene "
                "que adivinar. Es la única forma de saber si sirve para la próxima campaña y "
                "no solo para explicar la que ya pasó.",
            ),
            ui.panel(
                "1 · ¿Vale más que repetir la semana anterior?",
                dcc.Graph(figure=figura, config={"displayModeBar": False}),
                ui.como_leer(
                    "La barra compara cada modelo contra la regla más simple que existe: "
                    "suponer que esta semana se cosechará lo mismo que la anterior. **Por "
                    "debajo de la línea punteada** el modelo aporta algo; **en la línea o por "
                    "encima**, no vale más que esa regla simple.\n\n"
                    "Cada color es un plazo distinto: cuanto más lejos está la semana que se "
                    "pronostica, más difícil es acertar, así que las barras suelen crecer "
                    "hacia los plazos largos.\n\n"
                    "Ganar en esta barra **no basta** para cambiar el modelo en uso: también "
                    "tienen que cuadrar el volumen, el sesgo, el rango, los fundos y las "
                    "campañas. Esa decisión completa está en la página del modelo.",
                    "Cómo se lee este gráfico",
                ),
                ayuda="Comparación contra el método más simple posible, por modelo y plazo.",
            ),
            ui.panel(
                "2 · Cuánto se equivoca cada modelo",
                tabla(
                    metricas,
                    COLUMNAS_ERROR,
                    limite=60,
                    vacio="Todavía no se ha ejecutado una comparación de modelos.",
                    como_leer=(
                        "**Error de volumen** es el más directo: de cada 100 kg cosechados, "
                        "cuántos erró el pronóstico. **Sesgo** dice hacia qué lado se "
                        "equivoca — positivo significa que promete más kilos de los que "
                        "llegan, y es el error que más molesta en packing.\n\n"
                        "**Casos comparados** importa tanto como el error: una diferencia "
                        "calculada sobre veinte semanas no es comparable con una calculada "
                        "sobre miles.\n\n"
                        "**R²** aparece solo como diagnóstico. Un R² alto se puede conseguir "
                        "aprendiéndose el pasado, así que acá no decide nada."
                    ),
                ),
                ayuda="Error de volumen, sesgo y magnitud del error de cada modelo.",
            ),
            ui.panel(
                "3 · ¿Es creíble el rango que anuncia?",
                tabla(
                    metricas,
                    COLUMNAS_RANGO,
                    limite=60,
                    vacio="Todavía no se ha ejecutado una comparación de modelos.",
                    como_leer=(
                        "Un pronóstico no da solo un número: da un rango entre un escenario "
                        "bajo y uno alto. **Aciertos dentro del rango** debería rondar el "
                        "80 %. Mucho menos significa que el rango miente y no se puede "
                        "planificar con él; mucho más, que es tan ancho que no dice nada.\n\n"
                        "Por eso se mira junto al **ancho medio del rango**: un rango angosto "
                        "solo es bueno si además acierta. La **penalización del rango** "
                        "combina las dos cosas en un solo número, donde más bajo es mejor."
                    ),
                ),
                ayuda="Si el margen anunciado se corresponde con lo que después ocurre.",
            ),
            ui.panel(
                "4 · Error en las piezas del rendimiento",
                tabla(
                    metricas,
                    COLUMNAS_COMPONENTES,
                    limite=60,
                    vacio="Todavía no se ha ejecutado una comparación de modelos.",
                    como_leer=(
                        "Los kilos salen de tres piezas: cuántas plantas hay, cuántos frutos "
                        "da cada planta y cuánto pesa cada fruto. Acá se ve cuánto se "
                        "equivoca cada modelo en cada pieza por separado, que es lo que "
                        "permite juzgar si el pronóstico tiene sentido agronómico o si "
                        "acierta el total por compensación entre errores.\n\n"
                        "**El sesgo importa más que la magnitud.** Un modelo que estima de "
                        "más los frutos y de menos el peso puede dar el total correcto por "
                        "la razón equivocada; los dos sesgos juntos lo delatan.\n\n"
                        "Los frutos por planta están calculados sobre las plantas del maestro "
                        "del lote, que no varían dentro de la campaña. Todos los modelos se "
                        "comparan contra esa misma base; si no, la cifra recogería la "
                        "diferencia entre definiciones en vez del error del modelo.\n\n"
                        "**Desvío del producto** debe ser prácticamente cero en un modelo que "
                        "publica sus tres piezas: significa que el kilaje mostrado es "
                        "exactamente el que producen esas piezas."
                    ),
                ),
                ayuda="Error en plantas, frutos por planta y peso de baya.",
                aside=ui.semaforo(
                    "aviso",
                    "**La mayoría de los modelos comparte estas cifras, y eso es esperable.** "
                    "Solo los que estiman las piezas por su cuenta tienen un error propio; "
                    "el resto arrastra las que publica el pronóstico base, así que su error "
                    "sale idéntico entre sí. La familia de componentes es la que las estima "
                    "de forma independiente.",
                ),
            ),
            ui.semaforo(
                "info",
                "**Por qué esta comparación es lenta a propósito.** Las semanas seguidas se "
                "parecen entre sí, así que el margen de las diferencias se calcula "
                "remuestreando tramos completos de tiempo y no semanas sueltas. Y los cortes "
                "siempre respetan el calendario: nunca se entrena con semanas posteriores a "
                "la que se está pronosticando, aunque hacerlo daría números mucho mejores.",
            ),
            panel_glosario(
                [
                    "wape",
                    "mase",
                    "rmsse",
                    "mae_kg",
                    "sesgo_pct",
                    "r2",
                    "n",
                    "cobertura_80",
                    "ancho_intervalo_kg",
                    "interval_score_80",
                    "pinball_p10",
                    "pinball_p50",
                    "pinball_p90",
                    "mae_plantas",
                    "mae_frutos_por_planta",
                    "mae_peso_baya_g",
                    "banda_horizonte",
                ]
            ),
        ],
    )

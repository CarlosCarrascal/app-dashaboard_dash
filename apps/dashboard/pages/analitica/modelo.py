from __future__ import annotations

import dash
from dash import html

from analitica.config import VALORES_ANALITICOS
from components import ui
from pages.analitica._comun import (
    datos,
    estado_fuente,
    frase_legible,
    indicador_precision,
    panel_glosario,
    tabla,
    valor_legible,
)

dash.register_page(
    __name__, path="/analitica/modelo", name="Modelo", order=3, grupo="Plataforma analítica"
)


def _veredicto(fila) -> html.Div:
    """La decisión de una banda, dicha como se le diría a alguien en el fundo."""
    plazo = VALORES_ANALITICOS["banda_horizonte"].get(fila.banda_horizonte, fila.banda_horizonte)
    campeon = valor_legible("modelo", fila.campeon)
    retador = valor_legible("modelo", fila.challenger) if fila.challenger else None
    justificacion = frase_legible(fila.justificacion or "")
    if fila.resultado == "promover":
        return ui.semaforo("ok", f"**{plazo}: pasa a usarse {campeon}.** {justificacion}")
    if not retador:
        return ui.semaforo(
            "aviso",
            f"**{plazo}: sigue {campeon}.** Ningún modelo alternativo reunió casos "
            "suficientes para competir en este plazo, así que no hubo comparación que "
            "resolver.",
        )
    return ui.semaforo(
        "aviso",
        f"**{plazo}: sigue {campeon}.** El modelo que compitió fue {retador} y no "
        f"reunió las condiciones para reemplazarlo. {justificacion}",
    )


def layout():
    estado = datos()
    decisiones = estado["decisiones"]
    metricas = estado["metricas"]
    veredictos = [_veredicto(f) for f in decisiones.itertuples(index=False)]
    if not veredictos:
        veredictos = [
            ui.semaforo(
                "aviso",
                "Todavía no se ha comparado ningún modelo alternativo contra el que está en "
                "uso, así que no hay decisión que mostrar.",
            )
        ]
    return html.Div(
        className="space-y-4",
        children=[
            ui.encabezado_pagina(
                "Qué modelo produce los números y por qué",
                "Los modelos compiten pronosticando las mismas semanas del pasado. El que "
                "está en uso solo se reemplaza si el retador gana en todo lo que importa, no "
                "en una métrica suelta.",
            ),
            estado_fuente(estado),
            ui.panel(
                "Qué tan fiable es el pronóstico que se está usando",
                indicador_precision(estado),
                ayuda="Precisión medida del modelo vigente sobre semanas ya cosechadas.",
            ),
            ui.semaforo(
                "info",
                "**R09** es el pronóstico de cosecha que el fundo ya venía publicando. Es el "
                "punto de partida y el que hay que superar: cualquier modelo nuevo tiene que "
                "demostrar que lo hace mejor antes de reemplazarlo, no al revés.",
            ),
            ui.panel(
                "1 · Qué se decidió",
                *veredictos,
                ayuda="Modelo en uso por plazo y resultado de la última comparación.",
            ),
            ui.panel(
                "2 · Las condiciones que tuvo que cumplir el retador",
                ui.parrafo(
                    "Reemplazar el modelo que produce los compromisos de cosecha no es una "
                    "decisión que deba tomarse por un promedio mejor. El retador tiene que "
                    "cumplir **todas** estas condiciones a la vez, y basta con que falle una "
                    "para que se mantenga el actual."
                ),
                tabla(
                    decisiones,
                    [
                        "banda_horizonte",
                        "campeon",
                        "challenger",
                        "resultado",
                        "decision_mejora_wape",
                        "decision_mejora_mase",
                        "decision_porcentaje_lotes_ganados",
                        "decision_diferencia_wape_ic_inferior",
                        "decision_diferencia_wape_ic_superior",
                        "decision_cobertura_volumen",
                        "decision_campanias_ganadas",
                        "decision_deterioro_fundo_max",
                    ],
                    limite=10,
                    vacio="Todavía no hay una comparación de modelos registrada.",
                    como_leer=(
                        "Las dos columnas de **diferencia de error** son las que más pesan. "
                        "Marcan hasta dónde podría llegar la ventaja del retador si se "
                        "repitiera el ejercicio con otras semanas. **Si una es negativa y la "
                        "otra positiva, la ventaja no está resuelta**: puede ser una "
                        "particularidad de las semanas que tocó evaluar, y no se promueve.\n\n"
                        "**Lotes donde ganó el retador** distingue una mejora repartida de "
                        "una que viene de unos pocos lotes grandes. **Volumen cubierto** "
                        "evita promover a un modelo que solo funciona en un rincón del fundo. "
                        "**Peor empeoramiento en un fundo** frena las mejoras promedio que "
                        "arruinan un fundo concreto.\n\n"
                        "**Campañas ganadas** exige que la ventaja se repita en más de un "
                        "año: ganar en una sola campaña puede ser una particularidad de ese "
                        "año, no una mejora del modelo."
                    ),
                    titulo_lectura="Cómo se lee esta auditoría",
                ),
                ayuda="Cada condición de promoción con el valor que alcanzó el retador.",
            ),
            ui.panel(
                "3 · Cómo le fue a cada modelo",
                tabla(
                    metricas,
                    [
                        "modelo",
                        "banda_horizonte",
                        "n",
                        "wape",
                        "mase",
                        "mae_kg",
                        "sesgo_pct",
                        "cobertura_80",
                        "rmsse",
                        "r2",
                    ],
                    limite=40,
                    vacio="Todavía no se ha ejecutado una comparación de modelos.",
                    como_leer=(
                        "Todos los modelos se evaluaron sobre exactamente las mismas semanas "
                        "y los mismos lotes; si no, la comparación no valdría.\n\n"
                        "**Error de volumen** es el que traduce mejor a kilos. **Error frente "
                        "al método simple** dice si el modelo aporta algo por encima de "
                        "suponer que se repite la semana anterior. **R²** está solo como "
                        "diagnóstico y no participa en la decisión."
                    ),
                ),
                ayuda="Desempeño de cada modelo sobre las mismas semanas evaluadas.",
            ),
            ui.panel(
                "4 · Qué es cada modelo",
                ui.parrafo(
                    "**R09** es el pronóstico que el fundo ya publicaba, construido con el "
                    "criterio agronómico del equipo. **R09 corregido** es ese mismo "
                    "pronóstico al que se le descuenta el sesgo que viene mostrando: si "
                    "vino prometiendo de más, se le resta esa diferencia."
                ),
                ui.parrafo(
                    "**Random Forest** y **XGBoost** aprenden de los datos combinaciones que "
                    "una fórmula lineal no captura, como que el efecto del calor dependa de "
                    "en qué fase esté la planta. Aciertan sin explicar por qué: sirven para "
                    "pronosticar, no para decidir qué cambiar en el manejo. **Ridge** prueba "
                    "si con una corrección lineal simple alcanzaba."
                ),
                ui.parrafo(
                    "Los **métodos de serie** (repetir la semana anterior, repetir la misma "
                    "semana de la campaña pasada, promediar el histórico) están para tener "
                    "contra qué comparar: un modelo que no les gana no justifica su "
                    "complejidad. El **de componentes** arma los kilos multiplicando plantas "
                    "por frutos por planta y por peso de baya."
                ),
                ui.semaforo(
                    "aviso",
                    "**Lo que ningún modelo de esta lista puede decir.** Que una variable "
                    "ayude a pronosticar no significa que actuar sobre ella cambie el "
                    "resultado. El riego puede aparecer asociado a menor peso simplemente "
                    "porque se riega más cuando el lote viene flojo. Para afirmar que algo "
                    "causa otra cosa hace falta un ensayo diseñado, no un modelo que acierta.",
                ),
                ayuda="Qué hace cada familia de modelos y para qué sirve.",
            ),
            ui.panel(
                "5 · Sobre qué se apoya y qué le falta",
                ui.parrafo(
                    "**Se apoya en** que las condiciones no cambien de forma brusca respecto "
                    "de lo observado, en que la identidad de cada lote se mantenga "
                    "consistente entre sistemas, y en que ningún cálculo use información "
                    "posterior a la fecha en que se emite el pronóstico."
                ),
                ui.parrafo(
                    "**Le falta** historia fenológica de varias campañas, variables de "
                    "polinización, suelo y nutrición, y pronóstico meteorológico futuro. "
                    "Además, el clima es común a varios módulos, así que aporta menos "
                    "información independiente de lo que sugiere el número de filas, y las "
                    "variables de temperatura se mueven juntas: sus posiciones relativas en "
                    "cualquier ranking no deben leerse como efectos separados."
                ),
                ayuda="Supuestos y limitaciones declarados de la comparación.",
            ),
            panel_glosario(
                [
                    "campeon",
                    "challenger",
                    "resultado",
                    "wape",
                    "mase",
                    "sesgo_pct",
                    "cobertura_80",
                    "r2",
                    "n",
                    "banda_horizonte",
                    "decision_mejora_wape",
                    "decision_porcentaje_lotes_ganados",
                    "decision_diferencia_wape_ic_inferior",
                    "decision_diferencia_wape_ic_superior",
                    "decision_cobertura_volumen",
                    "decision_campanias_ganadas",
                    "decision_deterioro_fundo_max",
                ]
            ),
        ],
    )

from __future__ import annotations

import dash
from dash import html

from components import ui
from pages.analitica._comun import datos, estado_fuente, panel_glosario

dash.register_page(
    __name__,
    path="/analitica/explicacion",
    name="Explicación",
    order=4,
    grupo="Plataforma analítica",
)


def layout():
    estado = datos()
    return html.Div(
        className="space-y-4",
        children=[
            ui.encabezado_pagina(
                "Por qué el modelo dice lo que dice",
                "Cómo se averigua qué información está usando el pronóstico y cuánto aporta "
                "cada grupo de variables — y por qué eso no es lo mismo que saber qué "
                "cambiar en el manejo.",
            ),
            estado_fuente(estado),
            ui.panel(
                "1 · Quitarle información y ver cuánto empeora",
                ui.parrafo(
                    "Es la lectura más honesta de todas. Se vuelve a hacer la prueba "
                    "completa, pero escondiéndole al modelo un grupo entero de variables: "
                    "primero todo el clima, después todo el riego, después la fenología, "
                    "después la estructura del lote. Lo que empeora el pronóstico es lo que "
                    "ese grupo estaba aportando de verdad."
                ),
                ui.parrafo(
                    "Se hace por grupos y no variable por variable porque muchas miden casi "
                    "lo mismo. Si se quita solo la temperatura máxima, el modelo se apoya en "
                    "la mínima y apenas empeora; parecería que la temperatura no importa, "
                    "cuando lo que ocurre es que la información seguía disponible por otro "
                    "lado."
                ),
                ayuda="Cuánto empeora el pronóstico al retirar cada familia de variables.",
            ),
            ui.panel(
                "2 · Desordenar una variable y medir el daño",
                ui.parrafo(
                    "La otra forma de preguntarle al modelo qué usa es barajar los valores de "
                    "una variable entre semanas, de modo que deje de contener información "
                    "real, y ver cuánto se degrada el pronóstico."
                ),
                ui.parrafo(
                    "Acá también se barajan **juntas** las variables que se mueven juntas — "
                    "temperatura, sequedad del aire y acumulación térmica van en el mismo "
                    "bloque. Si se barajaran por separado, cada una parecería poco importante "
                    "porque las otras dos siguen contando la misma historia, y el ranking "
                    "resultante engañaría."
                ),
                ayuda="Importancia medida degradando cada bloque de variables.",
            ),
            ui.panel(
                "3 · Qué forma tiene la relación",
                ui.parrafo(
                    "Los dos métodos anteriores dicen **cuánto** pesa una variable, no en qué "
                    "dirección ni a partir de qué valor. Para eso se dibuja cómo cambia la "
                    "predicción a lo largo del rango de la variable, cuidando de no preguntar "
                    "por combinaciones que no existen en el campo: no tiene sentido evaluar "
                    "qué pasaría con 35 °C y máxima humedad si esa combinación nunca ocurre."
                ),
                ui.parrafo(
                    "Y para una semana y un lote concretos se puede desarmar la predicción en "
                    "cuánto aportó cada variable a ese número en particular. Sirve para "
                    "entender un caso raro, no para sacar una regla general."
                ),
                ayuda="Forma de la relación y desarme de una predicción individual.",
            ),
            ui.panel(
                "4 · De dónde salen los kilos",
                html.Pre(
                    "kilos = plantas × frutos por planta × peso de la baya (g) / 1000",
                    className="overflow-x-auto rounded-lg bg-slate-50 p-3 text-sm text-slate-700",
                ),
                ui.parrafo(
                    "Separar el rendimiento en sus tres piezas permite ver si un pronóstico "
                    "acierta por las razones correctas. Dos modelos pueden dar los mismos "
                    "kilos con uno estimando muchos frutos pequeños y el otro pocos frutos "
                    "grandes: el total coincide, pero uno de los dos está entendiendo mal el "
                    "cultivo, y eso solo se ve mirando las piezas por separado."
                ),
                ui.semaforo(
                    "aviso",
                    "**Estado real de esta descomposición.** Hoy las piezas se toman tal como "
                    "las publica el pronóstico base; todavía no hay modelos que estimen por "
                    "su cuenta los frutos por planta y el peso de la baya. Las transiciones "
                    "entre estados fenológicos, el cuajado y el crecimiento de la baya se "
                    "miden y se guardan, pero **no** se proyectan hacia adelante: hacerlo "
                    "exige varias campañas comparables. Mientras tanto, los tres errores por "
                    "pieza que aparecen en la comparación de modelos son casi idénticos entre "
                    "modelos, y no deben leerse como una diferencia de calidad.",
                ),
                ayuda="La identidad que reconstruye los kilos y su estado de implementación.",
            ),
            ui.semaforo(
                "aviso",
                "**Nada de esta página identifica causas.** Todos estos métodos explican qué "
                "usa el modelo para acertar, y un modelo puede acertar apoyándose en una "
                "variable que no controla nada: si el riego sube justo cuando el lote viene "
                "flojo, aparecerá asociado a menos kilos sin ser la causa. Para afirmar que "
                "una práctica cambia el resultado hace falta un ensayo con tratamientos "
                "definidos de antemano, no una lectura del modelo por buena que sea.",
            ),
            panel_glosario(["frutos_por_planta", "peso_baya_g", "plantas", "clase_evidencia"]),
        ],
    )

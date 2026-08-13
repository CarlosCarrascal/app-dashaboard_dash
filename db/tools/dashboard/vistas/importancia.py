"""Bloque global de «Explicación del modelo»: reparto SHAP del XGBoost.

Es la sección con más riesgo de malentendido del tablero: un ranking de barras invita a
leerse como «esto es lo que hay que cambiar para producir más». No lo es. Cada bloque
lleva su instrucción de lectura y su advertencia de alcance.
"""

from __future__ import annotations

import numpy as np
import streamlit as st

from config import FEATURES, ICONO, etiqueta
from nucleo import Ajuste, Panel
from vistas import graficos as g
from vistas.comun import como_leer, glosario, selector_variable, tarjetas


def _que_es_shap(ajuste: Ajuste, etiqueta_obj: str, unidad: str) -> None:
    with st.expander(f"{ICONO['info']}  ¿Qué es SHAP y qué significan estos números?"):
        st.markdown(
            "**SHAP** (*SHapley Additive exPlanations*) responde a una pregunta concreta: "
            f"de la diferencia entre {etiqueta_obj} de esta celda y el promedio de todas, "
            "¿cuánto le toca a cada variable?\n\n"
            "La idea viene de la teoría de juegos: si varios jugadores cooperan y ganan un "
            "premio, ¿cómo se reparte de forma justa? El valor de Shapley es la única "
            "forma de repartirlo que cumple ciertas reglas razonables — entre ellas, que "
            "**las partes sumen exactamente el total**.\n\n"
            f"Acá el «premio» es {etiqueta_obj.lower()}, el promedio general es "
            f"**{ajuste.base_value:,.2f} {unidad}**".replace(",", ".") +
            f", y los {len(FEATURES)} jugadores son las variables."
        )
        st.markdown(
            "**Cómo leer el signo:**\n"
            "- Un valor SHAP **positivo** significa que esa variable, con el valor que "
            f"tomó en esa semana, empujó {etiqueta_obj.lower()} **por encima** del promedio.\n"
            "- **Negativo**: lo empujó **por debajo**.\n"
            "- Cerca de **cero**: esa variable no movió la aguja en esa celda.\n\n"
            "El signo describe **el comportamiento del modelo**, no una ley agronómica. "
            "Que una variable tenga efecto negativo significa que en esta campaña sus "
            "semanas altas acompañaron valores bajos de este objetivo — no que subirla en "
            "el campo lo reduzca. La sección **Impacto agronómico** desarma esa lectura "
            "con cinco pruebas."
        )


def _ranking(ajuste: Ajuste, etiqueta_obj: str, unidad: str) -> None:
    st.subheader("Cuánto mueve cada variable")
    imp = ajuste.importancia
    tarjetas([
        ("La que más pesa", etiqueta(imp.index[0]),
         f"Mayor efecto absoluto promedio sobre {etiqueta_obj.lower()}."),
        ("Cuánto mueve", f"±{imp.iloc[0]:,.2f} {unidad}".replace(",", "."),
         "Promedio del valor absoluto de su efecto en todas las celdas."),
        ("La que menos pesa", etiqueta(imp.index[-1]), None),
        ("Cuánto mueve", f"±{imp.iloc[-1]:,.2f} {unidad}".replace(",", "."), None),
    ])
    st.plotly_chart(g.barras_importancia(imp), width="stretch")

    def _etiqueta_ventana(clave: str, ventana: int) -> str:
        return f"{clave} (actual)" if ventana == 1 else f"{clave} ({ventana} sem.)"

    lags = st.session_state.get("lags_config", {})
    ventanas = ", ".join(_etiqueta_ventana(k, v) for k, v in lags.items())
    st.info(
        f"**Objetivo explicado:** {etiqueta_obj}. **Configuración de desfase vigente:** "
        f"`{ventanas}` — se ve y se cambia en el menú lateral, expandiendo «Ventanas del "
        "modelo». Este gráfico muestra cómo XGBoost reparte el crédito en conjunto bajo "
        "estas ventanas — cambiarlas vuelve a entrenar el modelo y este ranking puede "
        "reordenarse.\n\n"
        "La configuración de referencia (riego = 1 semana, clima = 7 semanas) fue la que "
        "mejor funcionó como configuración predictiva **para kg/ha** bajo la partición "
        "temporal usada; Frutos y Peso reusan la misma ventana, no tienen una calibración "
        "propia todavía. Eso no demuestra que el riego tenga exactamente un efecto de una "
        "semana ni que el clima actúe por acumulación: son ventanas seleccionadas para "
        "predecir y deben validarse con fases fenológicas. Ver el detalle en **Modelo "
        "predictivo**.",
        icon=ICONO["info"],
    )
    como_leer(
        "Cada barra es el **promedio del valor absoluto** del efecto de esa variable, en "
        f"{unidad}. Se toma el valor absoluto porque a veces empuja hacia arriba y a veces "
        "hacia abajo: lo que mide la barra es **cuánto mueve**, no en qué dirección.\n\n"
        "**Ojo con la lectura fácil.** Que una variable encabece el ranking no significa "
        "que sea la palanca a accionar. Significa que el modelo la usa mucho — y el modelo "
        "puede estar usándola como marcador del calendario. La sección **Qué explica el R²** "
        "distingue las dos cosas con la columna de *aporte marginal*.",
        "Cómo se lee este ranking",
    )


def _summary(panel: Panel, ajuste: Ajuste, unidad: str = "kg/ha") -> None:
    st.subheader("Efecto celda por celda")
    orden = list(ajuste.importancia.index)[::-1]
    # `ajuste.X` puede tener menos filas que el panel (se descartan las sin ventana de
    # rezago completa): `.loc[ajuste.X.index]` alinea el panel a esas mismas filas.
    tabla_alineada = panel.tabla.loc[ajuste.X.index]
    st.plotly_chart(
        g.summary_shap(ajuste.shap_values, ajuste.X, orden, tabla_alineada, unidad),
        width="stretch",
    )
    como_leer(
        "Cada **punto** es una de las celdas módulo × semana del panel.\n\n"
        "- **Eje horizontal:** cuánto aportó esa variable en esa celda. A la "
        "derecha del cero empujó hacia arriba; a la izquierda, hacia abajo.\n"
        "- **Color:** si el valor de la variable era alto (rojo) o bajo (azul) en esa "
        "celda.\n"
        "- **Ancho de la nube:** cuánto varía el efecto. Una nube ancha significa que la "
        "variable a veces suma mucho y a veces resta mucho; una nube apretada en el cero "
        "significa que casi nunca importa.\n\n"
        "**El patrón que hay que buscar:** si los puntos rojos están todos de un lado y "
        "los azules del otro, la relación es consistente y direccional. Si están "
        "mezclados, el efecto depende de otras variables."
    )


def _dependencia(panel: Panel, ajuste: Ajuste, etiqueta_obj: str, unidad: str) -> None:
    st.subheader("Dependencia SHAP")
    st.markdown(
        "Este gráfico responde: **a medida que una variable sube, ¿cómo cambia su propio "
        f"efecto sobre {etiqueta_obj.lower()}?** Es la forma de la relación tal como la "
        "aprendió el modelo, sin suponer que sea una recta."
    )
    var = selector_variable(FEATURES, "dep")
    j = list(ajuste.X.columns).index(var)
    valores = ajuste.X[var].to_numpy()
    efectos = ajuste.shap_values[:, j]
    n_unicos = int(np.unique(valores).size)

    st.plotly_chart(
        g.dependencia_shap(ajuste.shap_values, ajuste.X, var,
                           panel.tabla.loc[ajuste.X.index, "nsem"], unidad),
        width="stretch",
    )
    if n_unicos <= ajuste.X.shape[0] // 3:
        st.info(
            f"{etiqueta(var)} solo toma **{n_unicos} valores distintos** en las "
            f"{ajuste.X.shape[0]} celdas del ajuste — normal en las variables climáticas: "
            "se miden una vez por semana y ese mismo valor se repite en todos los módulos "
            "de esa semana (ver «A qué grano se mide cada variable» en Pregunta, datos y "
            "límites). Por eso el gráfico se ve como columnas verticales apiladas y no como "
            "una nube continua: cada columna es una semana, y los puntos dentro de ella son "
            "los distintos módulos con el mismo clima pero un SHAP distinto porque el resto "
            "de sus variables difiere. **No es un error** — cambiar la ventana de desfase "
            "cambia cuáles semanas comparten valor, pero no puede eliminar el apilamiento "
            "mientras el clima siga siendo un dato semanal y no por módulo.",
            icon=ICONO["info"],
        )

    corte = float(np.median(valores))
    bajo = float(efectos[valores <= corte].mean())
    alto = float(efectos[valores > corte].mean())
    tarjetas([
        (f"Efecto medio con {etiqueta(var)} baja",
         f"{bajo:+,.2f} {unidad}".replace(",", "."),
         f"Celdas por debajo de la mediana ({corte:.2f})."),
        (f"Efecto medio con {etiqueta(var)} alta",
         f"{alto:+,.2f} {unidad}".replace(",", "."),
         f"Celdas por encima de la mediana ({corte:.2f})."),
        ("Diferencia", f"{alto - bajo:+,.2f} {unidad}".replace(",", "."),
         "Cuánto cambia el efecto al pasar de valores bajos a altos."),
    ])

    como_leer(
        "**Qué es cada eje.**\n"
        f"- **Horizontal:** el valor de {etiqueta(var)} en cada celda.\n"
        f"- **Vertical:** cuánto le atribuyó SHAP a {etiqueta(var)}, en {unidad}, en esa "
        "misma celda.\n"
        "- **Color:** la semana del año, para que se vea si el patrón sigue al calendario.\n\n"
        "**Cómo se interpreta la forma.**\n"
        "- Una nube que **baja de izquierda a derecha** significa que valores altos de la "
        f"variable acompañan {etiqueta_obj.lower()} por debajo del promedio.\n"
        "- Una nube **plana** significa que el modelo apenas usa esa variable.\n"
        "- Un **quiebre** —plana y de golpe cae— sugiere un umbral: el efecto aparece solo "
        "pasado cierto valor.\n"
        "- **Dispersión vertical** a un mismo valor de X indica interacción: el efecto de "
        "esta variable depende de lo que valgan las otras — o, si esa X es climática, de "
        "que todos los módulos de esa semana compartieron el mismo valor y solo se "
        "diferencian por las demás variables.\n\n"
        "**Advertencia de lectura.** Si los colores se ordenan de izquierda a derecha, lo "
        "que estás viendo es el calendario disfrazado de variable: las semanas tempranas a "
        "un lado y las tardías al otro. Ése es exactamente el problema que la sección "
        "**Impacto agronómico** cuantifica.",
        "Cómo se lee la dependencia SHAP",
    )


def render(
    panel: Panel, ajuste: Ajuste, etiqueta_obj: str = "kg/ha", unidad: str = "kg/ha",
) -> None:
    _que_es_shap(ajuste, etiqueta_obj, unidad)
    _ranking(ajuste, etiqueta_obj, unidad)
    st.divider()
    _summary(panel, ajuste, unidad)
    st.divider()
    _dependencia(panel, ajuste, etiqueta_obj, unidad)
    glosario(list(FEATURES))

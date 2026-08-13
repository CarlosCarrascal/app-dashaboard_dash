"""Sección «Qué explica el R²»: techo, grupos, variables y validación temporal.

Los bloques con modelo se cargan **a demanda**, con un
selector: lo barato se pinta al instante y lo caro solo si alguien lo pide. Antes esta
sección tardaba medio minuto en aparecer aunque el visitante solo quisiera ver el reparto
de varianza, que se calcula en milisegundos.
"""

from __future__ import annotations

import streamlit as st

import servicios as sv
from config import FEATURES, ICONO
from nucleo import Panel
from vistas import graficos as g
from vistas.comun import como_leer, semaforo, tarjetas

BLOQUES = {
    "techo": "Techo estructural",
    "grupos": "Importancia por grupos",
    "aporte": "Aporte de cada variable",
    "esquemas": "Esquemas de validación",
}


def _techo(panel: Panel) -> None:
    st.subheader("Cuánto puede explicar el clima, como máximo")
    pct_entre, pct_dentro = sv.descomposicion_varianza(panel.tabla)
    ef = sv.tamano_efectivo(panel.tabla)

    tarjetas([
        ("Variación entre semanas", f"{pct_entre:.0f}%",
         "La parte que una variable semanal podría llegar a explicar."),
        ("Variación entre módulos", f"{pct_dentro:.0f}%",
         "Ocurre dentro de una misma semana. El clima no la puede tocar."),
        ("Mediciones de clima", str(ef.n_semanas),
         f"Frente a {ef.n_celdas} celdas en el panel."),
    ])
    st.plotly_chart(g.reparto_varianza(pct_entre, pct_dentro), width="stretch")

    st.warning(
        f"El clima es un solo valor por semana, igual para los {panel.n_modulos} módulos "
        "— y así corresponde, porque la temperatura y el DPV no varían de forma apreciable "
        "dentro del fundo. La consecuencia es aritmética, no un defecto de medición: "
        f"**ninguna variable climática puede explicar el {pct_dentro:.0f}% de la variación "
        "que ocurre entre módulos en la misma semana.** Ese tramo solo lo puede explicar "
        "algo que distinga un módulo de otro — fecha de poda, variedad, edad de planta, "
        "suelo, manejo.",
        icon=ICONO["aviso"],
    )
    como_leer(
        "La barra reparte toda la variación del rendimiento en dos partes.\n\n"
        "- **Entre semanas:** cuánto se debe a que unas semanas rinden más que otras. "
        "Es el techo de cualquier variable que valga lo mismo para todo el fundo.\n"
        "- **Entre módulos:** cuánto se debe a que, en la misma semana, unos módulos "
        "rinden más que otros. Para explicar esto hace falta una variable que distinga "
        "módulos, y la única disponible es el riego.\n\n"
        "No es una limitación del análisis: es aritmética. Una variable constante dentro "
        "de un grupo no puede explicar diferencias dentro de ese grupo."
    )


def _aporte(panel: Panel) -> None:
    st.subheader("El R² es del modelo entero, no de cada variable")
    aporte = sv.aporte_por_variable(panel.tabla)
    st.metric(
        f"R² del modelo con las {len(FEATURES)} variables juntas",
        f"{aporte.attrs['completo']:+.3f}",
        help="Medido dejando una semana fuera del entrenamiento por vez.",
    )
    st.caption(
        "El R² **no se reparte** entre variables: no es aditivo, y la suma de los "
        f"individuales no da el total. Medido con «{aporte.attrs['particion']}» sobre "
        f"las mismas {aporte.attrs['n']} filas y {aporte.attrs['semanas']} semanas."
    )
    st.dataframe(
        aporte.style.format({
            "r (Pearson)": "{:+.3f}", "r² descriptivo": "{:.1%}", "R² sola": "{:+.3f}",
            "R² del modelo sin ella": "{:+.3f}", "Aporte marginal": "{:+.3f}",
        }).background_gradient(cmap="RdYlGn", subset=["Aporte marginal"],
                               vmin=-0.05, vmax=0.2),
        width="stretch", hide_index=True,
    )

    mejor = aporte.iloc[0]
    semaforo(
        "info",
        f"**La variable más valiosa del modelo es {mejor.Variable}** (aporte marginal "
        f"{mejor['Aporte marginal']:+.3f}), pese a tener una correlación cruda de solo "
        f"{mejor['r (Pearson)']:+.3f}. El orden por correlación y el orden por aporte son "
        "casi opuestos. Esto describe utilidad para el modelo, no una palanca causal.",
    )
    como_leer(
        "Cada columna responde una pregunta distinta:\n\n"
        "- **`r (Pearson)`** — cuánto acompaña la variable al rendimiento. Es descripción "
        "sobre los mismos datos con que se calculó.\n"
        "- **`r² descriptivo`** — el cuadrado del anterior: qué porcentaje de la variación "
        "acompaña.\n"
        "- **`R² sola`** — qué predice esa variable **por sí misma** en semanas que no "
        "vio. Negativa significa que predice peor que el simple promedio.\n"
        "- **`Aporte marginal`** — cuánto pierde el modelo completo si se le quita. "
        "Sirve para auditar este modelo, pero **no es el efecto agronómico**.\n\n"
        "Una variable puede correlacionar fuerte y no aportar nada, porque otra ya lleva "
        "esa información; y al revés."
    )


def _grupos(panel: Panel) -> None:
    st.subheader("Importancia por familias de variables")
    grupos = sv.aporte_por_grupo(panel.tabla)
    st.metric("R² del modelo completo", f"{grupos.attrs['completo']:+.3f}")
    st.caption(
        f"Ablación con «{grupos.attrs['particion']}», usando las mismas "
        f"{grupos.attrs['n']} filas y {grupos.attrs['semanas']} semanas en todas las "
        "comparaciones."
    )
    st.dataframe(
        grupos.style.format({
            "R² solo grupo": "{:+.3f}",
            "R² del modelo sin grupo": "{:+.3f}",
            "Aporte marginal del grupo": "{:+.3f}",
        }).background_gradient(
            cmap="RdYlGn", subset=["Aporte marginal del grupo"], vmin=-0.1, vmax=0.4
        ),
        width="stretch",
        hide_index=True,
    )
    como_leer(
        "Las variables climáticas están muy correlacionadas. Quitarlas de una en una "
        "permite que otra columna absorba la señal compartida; quitarlas como familia "
        "mide mejor cuánto dependía el modelo de ese bloque.\n\n"
        "- **R² solo grupo:** cuánto predice esa familia sin ayuda de las demás.\n"
        "- **R² sin grupo:** cuánto conserva el modelo al retirar toda la familia.\n"
        "- **Aporte marginal:** diferencia frente al modelo completo.\n\n"
        "Los grupos tampoco son efectos causales y sus aportes no se suman al R² total.",
        "Por qué mirar grupos antes que variables aisladas",
    )


def _esquemas(panel: Panel) -> None:
    st.subheader("El mismo modelo, medido de varias maneras")
    st.caption(
        "Un R² alto medido mal no vale nada. La diferencia entre estas filas es el "
        "hallazgo, no ninguna de ellas por separado."
    )
    st.dataframe(
        sv.tabla_validacion(panel.tabla)
        .style.format({"R²": "{:+.3f}", "MAE (kg/ha)": "{:.0f}"})
        .background_gradient(cmap="RdYlGn", subset=["R²"], vmin=-0.2, vmax=0.6),
        width="stretch", hide_index=True,
    )
    como_leer(
        "**Los baselines** son predictores sin modelo, y marcan el piso: si un modelo no "
        "le gana a «predecir siempre el promedio», no está midiendo nada.\n\n"
        "**Los esquemas (a) a (g)** son el mismo modelo evaluado con distintas formas de "
        "separar entrenamiento de prueba:\n"
        "- **(a) al azar** infla el resultado, porque mete módulos de la misma semana en "
        "los dos lados y al modelo le alcanza con recordar el promedio semanal.\n"
        "- **(c) dejando una semana fuera** es más honesto, pero todavía puede interpolar "
        "entre las semanas vecinas.\n"
        "- **(d) dejando un bloque de diez semanas** es el exigente: sin vecinas, no hay "
        "nada que interpolar. **Es el número que hay que mirar.**\n"
        "- **(e) solo el número de semana** no usa ninguna medición física. Si le gana al "
        "clima, el clima no está aportando nada que el almanaque no diga.\n\n"
        "**MAE** es el error medio en kg/ha: cuánto se equivoca en promedio."
    )


@st.fragment
def render(panel: Panel) -> None:
    # Radio horizontal y no `segmented_control` porque éste no es accesible desde
    # `AppTest`, y un control que decide qué se calcula tiene que poder probarse.
    bloque = st.radio(
        "Qué mostrar",
        options=list(BLOQUES),
        format_func=lambda b: BLOQUES[b],
        horizontal=True,
        key="bloque_validacion",
        help="Los tres últimos entrenan varios modelos y quedan guardados en caché.",
    )
    st.divider()

    if bloque == "grupos":
        _grupos(panel)
    elif bloque == "aporte":
        _aporte(panel)
    elif bloque == "esquemas":
        _esquemas(panel)
    else:
        _techo(panel)

"""Sección «Modelo predictivo»: por qué XGBoost y cómo está ajustado.

Elegir un modelo complejo sin comprobar que le gana a uno simple es una decisión tomada
por costumbre. Acá se comprueba, con las mismas particiones y los mismos datos.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import servicios as sv
from config import FEATURES, ICONO, PARAMS, etiqueta
from nucleo import Panel


def _que_hace(panel: Panel) -> None:
    st.subheader("Qué hace el modelo, y para qué se usa acá")
    st.markdown(
        "XGBoost ajusta árboles de decisión **en secuencia**: el primero predice el "
        "kg/ha, el segundo predice el error que dejó el primero, el tercero el que dejó "
        "el segundo, y así. Cada uno aporta una fracción pequeña —la tasa de "
        "aprendizaje— para que ninguno domine. La suma de todos es el modelo."
    )
    st.latex(r"\hat{y}(x) \;=\; \sum_{k=1}^{K} \eta \, f_k(x)")
    st.markdown(
        f"Acá **K = {PARAMS['n_estimators']}** árboles y **η = {PARAMS['learning_rate']}**. "
        "El modelo se evalúa como **instrumento predictivo**: primero se comprueba si "
        "generaliza a semanas no vistas y después se explica cómo usa sus "
        f"**{len(FEATURES)} variables**. No es todavía un pronóstico operativo ni un "
        "estimador causal. Sus métricas comparables están en **Qué explica el R²** y el "
        "reparto SHAP está en **Explicación del modelo**."
    )


def _por_que_xgboost(panel: Panel) -> None:
    st.subheader("¿Por qué XGBoost y no algo más simple?")
    st.caption(
        "Mismos datos, mismas particiones. Si la regresión lineal empatara, la no "
        "linealidad no compraría nada y sí costaría opacidad."
    )
    # Doce ajustes: se calculan solo si alguien los pide, para que la sección abra rápido.
    if not st.toggle("Calcular la comparación", value=False, key="comparar_familias",
                     help="Entrena seis familias de modelo con dos particiones cada una. "
                          "Tarda unos segundos."):
        st.info("Activá el interruptor para entrenar y comparar las seis familias.",
                icon=ICONO["info"])
        return
    comparacion = sv.comparar_familias(panel.tabla)
    st.dataframe(
        comparacion.style.format(
            {"R² deja-una-semana": "{:+.3f}", "R² deja-un-bloque": "{:+.3f}",
             "MAE bloque (kg/ha)": "{:.0f}"}
        ).background_gradient(cmap="RdYlGn", subset=["R² deja-un-bloque"],
                              vmin=-0.6, vmax=0.1),
        width="stretch", hide_index=True,
    )

    piso = comparacion.loc[comparacion.Modelo == "Predecir la media",
                           "R² deja-un-bloque"].iloc[0]
    xgb_r2 = comparacion.loc[comparacion.Modelo == "XGBoost (el del tablero)",
                             "R² deja-un-bloque"].iloc[0]
    lineal = comparacion.loc[comparacion.Modelo == "Regresión lineal",
                             "R² deja-un-bloque"].iloc[0]
    st.info(
        f"**Lo que dice la tabla.** Bajo la partición honesta, la regresión lineal da "
        f"{lineal:+.3f}: mucho **peor** que no usar ninguna variable ({piso:+.3f}). No es "
        "que no encuentre el patrón — lo encuentra y lo extrapola fuera del rango que vio, "
        "y como el bloque retenido cae en otra estación, se dispara. Los árboles no "
        "extrapolan: se quedan en el rango de entrenamiento, y acá eso los salva.\n\n"
        f"XGBoost es el único que queda por encima del piso ({xgb_r2:+.3f} contra "
        f"{piso:+.3f}). Ésa es la justificación de usarlo — no que sea preciso, sino que "
        "es el único que no se degrada por debajo de no hacer nada.",
        icon=ICONO["info"],
    )


def _como_esta_ajustado() -> None:
    st.subheader("Cómo está ajustado, y contra qué se decidió")
    st.markdown(
        "La calibración tuvo dos etapas: **108 combinaciones** sobre la formulación "
        "inicial y un re-barrido de **264 configuraciones** después de incorporar las "
        "siete variables y sus ventanas. La regla que se respetó: **se elige mirando "
        "«deja-una-semana-fuera» y se reporta «deja-un-bloque-fuera»**. Elegir mirando la "
        "métrica que después se publica la infla. El re-barrido no encontró una "
        "configuración que mejorara de forma estable a la vigente."
    )


    with st.expander("Historial de la calibración inicial"):
        st.caption(
            "Estas cifras pertenecen a la etapa anterior a la formulación vigente de "
            "ventanas. Se conservan como trazabilidad, no como resultado actual."
        )
        st.dataframe(
            pd.DataFrame(
                {
                    "Configuración histórica": ["Anterior (prof. 3, η 0,03)",
                                                 "Prof. 6, η 0,01, hoja ≥ 10, λ 5",
                                                 "Piso: predecir la media"],
                    "R² selección": [0.344, 0.402, None],
                    "R² honesto": [-0.116, 0.053, -0.147],
                    "MAE honesto (kg/ha)": [757, 686, 756],
                }
            ).style.format({"R² selección": "{:+.3f}", "R² honesto": "{:+.3f}",
                            "MAE honesto (kg/ha)": "{:.0f}"}, na_rep="—"),
            width="stretch", hide_index=True,
        )
        st.markdown(
            "La mejora histórica se comprobó con ocho semillas. Las métricas del modelo "
            "vigente se recalculan con el archivo y las ventanas activas en **Qué explica "
            "el R²**; por eso no se fijan aquí como constantes."
        )

    with st.expander("Los hiperparámetros, uno por uno"):
        st.dataframe(
            pd.DataFrame(
                {
                    "Parámetro": ["n_estimators", "max_depth", "learning_rate",
                                  "min_child_weight", "reg_lambda", "subsample",
                                  "colsample_bytree"],
                    "Valor": [PARAMS["n_estimators"], PARAMS["max_depth"],
                              PARAMS["learning_rate"], PARAMS["min_child_weight"],
                              PARAMS["reg_lambda"], PARAMS["subsample"],
                              PARAMS["colsample_bytree"]],
                    "Qué controla": [
                        "Cuántos árboles se encadenan.",
                        "Profundidad de cada árbol: cuántas interacciones puede capturar.",
                        "Cuánto aporta cada árbol. Bajo = aprendizaje lento y estable.",
                        "Mínimo de observaciones por hoja. Es el freno principal.",
                        "Penalización L2 sobre el valor de las hojas.",
                        "Fracción de filas que ve cada árbol.",
                        "Fracción de variables que ve cada árbol.",
                    ],
                }
            ),
            width="stretch", hide_index=True,
        )
        st.markdown(
            "**Por qué árboles profundos con aprendizaje muy lento.** La intuición "
            "habitual —pocos datos, árboles chicos— no ganó acá. Con profundidad 6 el "
            "modelo puede capturar interacciones entre clima y riego que la profundidad 3 "
            "no alcanza; el sobreajuste se frena por el otro lado, exigiendo al menos 10 "
            "observaciones por hoja y penalizando hojas extremas, en vez de amputar el "
            "árbol. Con 452 filas eso resultó mejor que la receta conservadora."
        )

    st.warning(
        "**Lo que este ajuste no arregla.** La mejora registrada durante la calibración "
        "fortalece el instrumento predictivo, pero no cambia el diagnóstico causal. Un R² positivo bajo "
        "partición temporal indica señal aprovechable, pero no dice qué variable produce "
        "el cambio en campo. Ese resultado debe leerse junto con el control del calendario.",
        icon=ICONO["aviso"],
    )


def _auditar_ventanas(panel: Panel) -> None:
    """Hace visible el desfase que realmente entra a XGBoost."""
    st.subheader("Auditoría de desfases: qué ve realmente el modelo")
    st.markdown(
        "Una ventana de 7 semanas **no es una fase fenológica**: es un promedio de semanas "
        "de calendario. Esta tabla permite comprobar que cada variable se haya construido "
        "en su grano correcto y cuántas observaciones quedan disponibles."
    )
    cfg = st.session_state.get(
        "lags_config", {"riego": 7, "Rad": 3, "ETo": 2, "DPV": 6, "gdd": 7}
    )
    diagnostico = sv.diagnostico_ventanas(panel.tabla, cfg).copy()
    diagnostico.insert(0, "Variable", diagnostico["Columna modelo"].map(etiqueta))
    diagnostico = diagnostico.drop(columns=["Columna modelo"])
    st.dataframe(diagnostico, width="stretch", hide_index=True)
    st.warning(
        "**Desfase actual:** las medias móviles son inclusivas. Por ejemplo, una ventana "
        "de 7 semanas en la fila `t` usa `t-6 a t`, y `riego = 1` usa el riego de `t`. "
        "Esto sirve para evaluar una señal predictiva contemporánea, pero no prueba "
        "precedencia causal: parte de la exposición coincide con la semana cosechada. "
        "Un análisis agronómico pre-cosecha tendría que comparar `t-7 a t-1` (o fases "
        "definidas desde poda) y volver a entrenar y validar el modelo.",
        icon=ICONO["aviso"],
    )

    clima = panel.tabla[
        ["nsem", "gdd_semana", "TempMax", "TempMin"]
    ].drop_duplicates("nsem").copy()
    clima["Temperatura media"] = (clima.TempMax + clima.TempMin) / 2
    corr_gdd = float(clima["gdd_semana"].corr(clima["Temperatura media"]))
    if corr_gdd > 0.98 and clima.gdd_semana.min() > 0:
        st.warning(
            f"**Redundancia detectada en esta campaña.** GDD semanal y temperatura media "
            f"tienen una correlación de {corr_gdd:+.3f}, porque prácticamente todas las "
            "semanas están por encima de la temperatura base. `gdd_lag` no aporta una "
            "señal independiente clara frente a las temperaturas; puede conservarse como "
            "diagnóstico de desarrollo, pero no debe presentarse como una variable distinta "
            "sin una fase definida desde poda.",
            icon=ICONO["aviso"],
        )
    st.info(
        "**Veredicto del desfase.** La implementación es técnicamente consistente: clima "
        "se calcula una vez por semana y riego por Fundo–Módulo, sin rellenar ventanas "
        "incompletas. Lo que todavía no está demostrado es que 7 semanas represente el "
        "tiempo biológico de cada variable. Para eso faltan poda, días desde poda y fase "
        "fenológica por módulo.",
        icon=ICONO["info"],
    )


def render(panel: Panel) -> None:
    _que_hace(panel)
    st.divider()
    _auditar_ventanas(panel)
    st.divider()
    _por_que_xgboost(panel)
    st.divider()
    _como_esta_ajustado()

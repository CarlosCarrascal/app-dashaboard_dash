"""Página «Modelo predictivo» — puerto completo de `dashboard/vistas/modelo.py`.

Qué hace XGBoost acá, por qué se prefirió sobre algo más simple (comparación bajo
demanda, entrena seis familias), cómo está ajustado, y una auditoría de qué ventana de
desfase ve realmente el modelo.
"""

from __future__ import annotations

import dash
import pandas as pd
from dash import dcc, html
from dash_extensions.enrich import Input, Output, callback

import nucleo
from config import FEATURES, PARAMS, etiqueta
from components import ui
from servicios.carga import LAGS_POR_DEFECTO, PANEL_STORE

dash.register_page(__name__, path="/modelo/modelo", name="Modelo predictivo", order=1, grupo="Modelo predictivo")


def _que_hace() -> html.Div:
    """100% estático: no depende del panel, así que se arma una sola vez en `layout()`."""
    return html.Div(
        className="space-y-3",
        children=[
            ui.titulo_seccion("Qué hace el modelo, y para qué se usa acá"),
            ui.parrafo(
                "XGBoost ajusta árboles de decisión **en secuencia**: el primero predice "
                "el kg/ha, el segundo predice el error que dejó el primero, el tercero el "
                "que dejó el segundo, y así. Cada uno aporta una fracción pequeña —la "
                "tasa de aprendizaje— para que ninguno domine. La suma de todos es el "
                "modelo."
            ),
            html.Pre("ŷ(x) = Σ η · f_k(x)   (k = 1..K)", className="rounded bg-slate-50 p-3 text-sm"),
            ui.parrafo(
                f"Acá **K = {PARAMS['n_estimators']}** árboles y **η = {PARAMS['learning_rate']}**. "
                "El modelo se evalúa como **instrumento predictivo**: primero se comprueba "
                "si generaliza a semanas no vistas y después se explica cómo usa sus "
                f"**{len(FEATURES)} variables**. No es todavía un pronóstico operativo ni "
                "un estimador causal. Sus métricas comparables están en **Qué explica el "
                "R²** y el reparto SHAP está en **Explicación del modelo**."
            ),
        ],
    )


def _como_esta_ajustado() -> html.Div:
    """También estático — mismos textos que el Streamlit, sin dependencia del panel."""
    historico = pd.DataFrame({
        "Configuración histórica": ["Anterior (prof. 3, η 0,03)", "Prof. 6, η 0,01, hoja ≥ 10, λ 5",
                                     "Piso: predecir la media"],
        "R² selección": [0.344, 0.402, None],
        "R² honesto": [-0.116, 0.053, -0.147],
        "MAE honesto (kg/ha)": [757, 686, 756],
    })
    hiperparams = pd.DataFrame({
        "Parámetro": ["n_estimators", "max_depth", "learning_rate", "min_child_weight",
                      "reg_lambda", "subsample", "colsample_bytree"],
        "Valor": [PARAMS["n_estimators"], PARAMS["max_depth"], PARAMS["learning_rate"],
                  PARAMS["min_child_weight"], PARAMS["reg_lambda"], PARAMS["subsample"],
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
    })
    return html.Div(
        className="space-y-4",
        children=[
            ui.titulo_seccion("Cómo está ajustado, y contra qué se decidió"),
            ui.parrafo(
                "La calibración tuvo dos etapas: **108 combinaciones** sobre la "
                "formulación inicial y un re-barrido de **264 configuraciones** después "
                "de incorporar las siete variables y sus ventanas. La regla que se "
                "respetó: **se elige mirando «deja-una-semana-fuera» y se reporta "
                "«deja-un-bloque-fuera»**. Elegir mirando la métrica que después se "
                "publica la infla. El re-barrido no encontró una configuración que "
                "mejorara de forma estable a la vigente."
            ),
            html.Details(className="rounded-lg border border-slate-200 p-3", children=[
                html.Summary("Historial de la calibración inicial", className="cursor-pointer text-sm font-medium text-slate-600"),
                html.Div(className="mt-2 space-y-2", children=[
                    ui.parrafo(
                        "Estas cifras pertenecen a la etapa anterior a la formulación "
                        "vigente de ventanas. Se conservan como trazabilidad, no como "
                        "resultado actual."
                    ),
                    ui.tabla_desde_df(historico, formato={
                        "R² selección": "{:+.3f}", "R² honesto": "{:+.3f}", "MAE honesto (kg/ha)": "{:.0f}",
                    }),
                ]),
            ]),
            html.Details(className="rounded-lg border border-slate-200 p-3", children=[
                html.Summary("Los hiperparámetros, uno por uno", className="cursor-pointer text-sm font-medium text-slate-600"),
                html.Div(className="mt-2", children=ui.tabla_desde_df(hiperparams)),
            ]),
            ui.semaforo(
                "aviso",
                "**Lo que este ajuste no arregla.** La mejora registrada durante la "
                "calibración fortalece el instrumento predictivo, pero no cambia el "
                "diagnóstico causal. Un R² positivo bajo partición temporal indica señal "
                "aprovechable, pero no dice qué variable produce el cambio en campo. Ese "
                "resultado debe leerse junto con el control del calendario.",
            ),
        ],
    )


def layout():
    return html.Div(
        className="space-y-8",
        children=[
            _que_hace(),
            html.Hr(className="border-slate-200"),
            html.Div(id="modelo-auditoria-ventanas"),
            html.Hr(className="border-slate-200"),
            html.Div(
                className="space-y-3",
                children=[
                    ui.titulo_seccion("¿Por qué XGBoost y no algo más simple?"),
                    ui.parrafo(
                        "Mismos datos, mismas particiones. Si la regresión lineal "
                        "empatara, la no linealidad no compraría nada y sí costaría "
                        "opacidad."
                    ),
                    dcc.Checklist(
                        id="modelo-comparar-familias",
                        options=[{"label": " Calcular la comparación (entrena seis familias, tarda unos segundos)", "value": "on"}],
                        value=[],
                        className="text-sm",
                    ),
                    html.Div(id="modelo-comparacion-familias"),
                ],
            ),
            html.Hr(className="border-slate-200"),
            _como_esta_ajustado(),
        ],
    )


@callback(Output("modelo-auditoria-ventanas", "children"), Input(PANEL_STORE, "data"))
def _auditar_ventanas(panel):
    if panel is None:
        return ui.semaforo("aviso", "Cargando el panel…")
    # La ventana todavía no es configurable desde esta interfaz (el control del sidebar
    # del Streamlit no se portó — cambiarla implica rearmar el panel completo). Se usa
    # siempre `LAGS_POR_DEFECTO` de `servicios/carga.py`.
    diagnostico = nucleo.diagnostico_ventanas(panel.tabla, LAGS_POR_DEFECTO).copy()
    diagnostico.insert(0, "Variable", diagnostico["Columna modelo"].map(etiqueta))
    diagnostico = diagnostico.drop(columns=["Columna modelo"])

    clima = panel.tabla[["nsem", "gdd_semana", "TempMax", "TempMin"]].drop_duplicates("nsem").copy()
    clima["Temperatura media"] = (clima.TempMax + clima.TempMin) / 2
    corr_gdd = float(clima["gdd_semana"].corr(clima["Temperatura media"]))

    bloques = [
        ui.titulo_seccion("Auditoría de desfases: qué ve realmente el modelo"),
        ui.parrafo(
            "Una ventana de 7 semanas **no es una fase fenológica**: es un promedio de "
            "semanas de calendario. Esta tabla permite comprobar que cada variable se "
            "haya construido en su grano correcto y cuántas observaciones quedan "
            "disponibles."
        ),
        ui.tabla_desde_df(diagnostico),
        ui.semaforo(
            "aviso",
            "**Desfase actual:** las medias móviles son inclusivas. Por ejemplo, una "
            "ventana de 7 semanas en la fila `t` usa `t-6 a t`, y `riego = 1` usa el "
            "riego de `t`. Esto sirve para evaluar una señal predictiva contemporánea, "
            "pero no prueba precedencia causal: parte de la exposición coincide con la "
            "semana cosechada. Un análisis agronómico pre-cosecha tendría que comparar "
            "`t-7 a t-1` (o fases definidas desde poda) y volver a entrenar y validar el "
            "modelo.",
        ),
    ]
    if corr_gdd > 0.98 and clima.gdd_semana.min() > 0:
        bloques.append(
            ui.semaforo(
                "aviso",
                f"**Redundancia detectada en esta campaña.** GDD semanal y temperatura "
                f"media tienen una correlación de {corr_gdd:+.3f}, porque prácticamente "
                "todas las semanas están por encima de la temperatura base. `gdd_lag` no "
                "aporta una señal independiente clara frente a las temperaturas; puede "
                "conservarse como diagnóstico de desarrollo, pero no debe presentarse "
                "como una variable distinta sin una fase definida desde poda.",
            )
        )
    bloques.append(
        ui.semaforo(
            "info",
            "**Veredicto del desfase.** La implementación es técnicamente consistente: "
            "clima se calcula una vez por semana y riego por Fundo–Módulo, sin rellenar "
            "ventanas incompletas. Lo que todavía no está demostrado es que 7 semanas "
            "represente el tiempo biológico de cada variable. Para eso faltan poda, días "
            "desde poda y fase fenológica por módulo.",
        )
    )
    return html.Div(bloques, className="space-y-3")


@callback(
    Output("modelo-comparacion-familias", "children"),
    Input(PANEL_STORE, "data"),
    Input("modelo-comparar-familias", "value"),
)
def _comparar_familias(panel, activo):
    if not activo:
        return ui.parrafo("_Activá el interruptor para entrenar y comparar las seis familias._")
    if panel is None:
        return ui.semaforo("aviso", "Cargando el panel…")
    comparacion = nucleo.comparar_familias(panel.tabla)
    piso = comparacion.loc[comparacion.Modelo == "Predecir la media", "R² deja-un-bloque"].iloc[0]
    xgb_r2 = comparacion.loc[comparacion.Modelo == "XGBoost (el del tablero)", "R² deja-un-bloque"].iloc[0]
    lineal = comparacion.loc[comparacion.Modelo == "Regresión lineal", "R² deja-un-bloque"].iloc[0]
    return html.Div(
        className="space-y-3",
        children=[
            ui.tabla_desde_df(comparacion, formato={
                "R² deja-una-semana": "{:+.3f}", "R² deja-un-bloque": "{:+.3f}", "MAE bloque (kg/ha)": "{:.0f}",
            }),
            ui.semaforo(
                "info",
                f"**Lo que dice la tabla.** Bajo la partición honesta, la regresión "
                f"lineal da {lineal:+.3f}: mucho **peor** que no usar ninguna variable "
                f"({piso:+.3f}). No es que no encuentre el patrón — lo encuentra y lo "
                "extrapola fuera del rango que vio, y como el bloque retenido cae en "
                "otra estación, se dispara. Los árboles no extrapolan: se quedan en el "
                "rango de entrenamiento, y acá eso los salva.\n\n"
                f"XGBoost es el único que queda por encima del piso ({xgb_r2:+.3f} "
                f"contra {piso:+.3f}). Ésa es la justificación de usarlo — no que sea "
                "preciso, sino que es el único que no se degrada por debajo de no hacer "
                "nada.",
            ),
        ],
    )

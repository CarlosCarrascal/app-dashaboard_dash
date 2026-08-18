"""Página «Modelo predictivo».

Esta página audita el instrumento antes de interpretar sus salidas: qué recibe, qué
significa la ventana temporal, cómo se ajustó y si la elección de XGBoost sigue siendo
defendible frente a familias más simples. La capacidad de generalización vive en «Qué
explica el R²» y la lectura interna de una predicción en «Explicación del modelo».
"""

from __future__ import annotations

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html
from dash_extensions.enrich import Input, Output, callback

from analitica import nucleo
from analitica.config import FEATURES, PARAMS, etiqueta
from components import ui
from servicios.cache_analisis import obtener, precargar
from servicios.carga import LAGS_POR_DEFECTO, PANEL_STORE

dash.register_page(
    __name__, path="/modelo/modelo", name="Modelo predictivo", order=1,
    grupo="Modelo predictivo",
)

_VENTANAS_CACHE = "modelo:ventanas"
_FAMILIAS_CACHE = "modelo:familias"


def layout():
    """Deja las dos salidas en el layout inicial para que ambas carguen sin clic."""
    return html.Div(
        className="space-y-4",
        children=[
            html.Div(id="modelo-principal", children=ui.esqueleto_pagina()),
            html.Div(id="modelo-familias", children=ui.esqueleto_seccion("h-64")),
        ],
    )


def _diagnostico(panel) -> pd.DataFrame:
    return obtener(
        panel,
        _VENTANAS_CACHE,
        lambda: nucleo.diagnostico_ventanas(panel.tabla, LAGS_POR_DEFECTO),
    ).copy()


def _comparacion(panel) -> pd.DataFrame:
    return obtener(
        panel,
        _FAMILIAS_CACHE,
        lambda: nucleo.comparar_familias(panel.tabla),
    ).copy()


def _kpis(panel) -> html.Div:
    base = panel.tabla.dropna(subset=[*FEATURES, "KgHa"])
    semanas = int(base.nsem.nunique()) if not base.empty else 0
    filas_por_semana = base.groupby("nsem").size().tolist() if not base.empty else None
    ventana_max = max(LAGS_POR_DEFECTO.values())
    return ui.fila_kpi([
        ui.kpi(
            "Muestra comparable",
            f"{len(base)}\u00a0/\u00a0{semanas}",
            nota="Filas / semanas con las 7 variables completas y Kg/ha observado.",
            serie=filas_por_semana,
        ),
        ui.kpi(
            "Variables predictoras",
            str(len(FEATURES)),
            nota="Señales que recibe el modelo general; clima, riego y ventanas móviles.",
        ),
        ui.kpi(
            "Árboles encadenados",
            str(PARAMS["n_estimators"]),
            nota=f"Profundidad {PARAMS['max_depth']} · η = {PARAMS['learning_rate']}.",
        ),
        ui.kpi(
            "Ventana más larga",
            f"{ventana_max} sem.",
            nota="Es un desfase de calendario, no una fase fenológica medida.",
            serie=sorted(LAGS_POR_DEFECTO.values()),
        ),
    ])


def _respuesta_corta() -> html.Div:
    """Conclusión ejecutiva antes de entrar en la configuración."""
    conexion = html.Div(
        className="grid gap-4 sm:grid-cols-2",
        children=[
            html.Div([
                html.Div("Este análisis responde", className="text-sm font-semibold text-slate-700"),
                html.P(
                    "Qué recibe el predictor, qué límites tiene esa señal y si la familia "
                    "elegida merece compararse con alternativas bajo la misma partición.",
                    className="mt-1.5 text-sm leading-relaxed text-slate-600",
                ),
            ]),
            html.Div([
                html.Div("Cómo ayuda al modelo", className="text-sm font-semibold text-slate-700"),
                html.P(
                    "Separa el instrumento predictivo del análisis agronómico: aquí se "
                    "audita la entrada y la elección del algoritmo; el R² mide si generaliza "
                    "y SHAP describe cómo reparte una predicción.",
                    className="mt-1.5 text-sm leading-relaxed text-slate-600",
                ),
            ]),
        ],
    )
    return ui.panel(
        "Respuesta corta",
        ui.semaforo(
            "aviso",
            "**El modelo puede encontrar señal, pero todavía no es una explicación del "
            "campo.** Sus ventanas incluyen la semana objetivo y GDD prácticamente repite "
            "la temperatura en esta campaña; por eso el resultado predictivo debe leerse "
            "con la validación temporal y no como una recomendación causal.",
        ),
        conexion,
        ayuda="La conclusión ejecutiva y la relación entre este módulo y las otras lecturas.",
    )


def _que_hace() -> html.Div:
    return ui.panel(
        "1 · Qué hace XGBoost aquí",
        ui.parrafo(
            "XGBoost ajusta árboles de decisión **en secuencia**: cada árbol corrige una "
            "parte del error que dejaron los anteriores. La tasa de aprendizaje hace que "
            "cada corrección sea pequeña; la predicción final es la suma de todas. Es una "
            "forma de capturar umbrales e interacciones sin obligar a que la relación sea "
            "una recta."
        ),
        html.Pre(
            "ŷ(x) = Σ η · fₖ(x)   (k = 1..K)",
            className="overflow-x-auto rounded-lg bg-slate-50 p-3 text-sm text-slate-700",
        ),
        ui.subseccion(
            "Lo que sí se evalúa",
            ui.parrafo(
                f"El ajuste actual usa **{PARAMS['n_estimators']} árboles**, profundidad "
                f"**{PARAMS['max_depth']}** y **{len(FEATURES)} variables**. Primero se "
                "comprueba si generaliza a semanas que no vio; después se describe cómo "
                "reparte una predicción. Esas dos lecturas están separadas en **Qué explica "
                "el R²** y **Explicación del modelo**."
            ),
        ),
        ui.subseccion(
            "Lo que no se puede concluir aquí",
            ui.parrafo(
                "Que el modelo use mucho una variable no prueba que moverla cambie el "
                "rendimiento. El algoritmo aprende asociaciones del panel observado; no es "
                "un experimento ni un pronóstico operativo listo para decidir manejo."
            ),
        ),
        ayuda="La función del algoritmo y el límite entre predicción y explicación agronómica.",
    )


def _ventanas(panel) -> html.Div:
    diagnostico = _diagnostico(panel)
    resumen = diagnostico[[
        "Columna modelo", "Ventana (sem)", "Cobertura temporal", "Ámbito", "Filas con valor",
    ]].copy()
    resumen["Columna modelo"] = resumen["Columna modelo"].map(etiqueta)
    resumen = resumen.rename(columns={
        "Columna modelo": "Variable",
        "Ventana (sem)": "Ventana",
        "Cobertura temporal": "Semanas incluidas",
        "Filas con valor": "Filas válidas",
    })

    clima = panel.tabla[["nsem", "gdd_semana", "TempMax", "TempMin"]].drop_duplicates("nsem").copy()
    clima["Temperatura media"] = (clima.TempMax + clima.TempMin) / 2
    corr_gdd = float(clima["gdd_semana"].corr(clima["Temperatura media"]))

    detalles = diagnostico.copy()
    detalles.insert(0, "Variable", detalles["Columna modelo"].map(etiqueta))
    detalles = detalles.drop(columns=["Columna modelo"])
    return ui.panel(
        "2 · Qué señal recibe realmente",
        ui.parrafo(
            "La entrada no son fases del cultivo: son valores semanales y medias móviles "
            "que se calculan antes de entrenar. Esta vista resume el grano, la ventana y "
            "cuántas filas sobreviven; la auditoría completa queda plegada para no obligar "
            "al lector a empezar por una tabla técnica."
        ),
        ui.tabla_desde_df(resumen),
        ui.semaforo(
            "aviso",
            "**Las ventanas actuales son inclusivas.** Una ventana de 7 semanas en `t` usa "
            "`t-6 a t` y el riego incluye el valor de `t`. Eso sirve para una señal "
            "predictiva contemporánea, pero no prueba precedencia causal. Una pregunta "
            "pre-cosecha tendría que usar `t-7 a t-1` o fases definidas desde poda y "
            "volver a entrenar y validar.",
        ),
        ui.semaforo(
            "aviso",
            f"**GDD y temperatura están prácticamente duplicados aquí:** correlación "
            f"{corr_gdd:+.3f}. GDD puede conservarse como indicador de desarrollo, pero no "
            "debe presentarse como una señal independiente mientras no exista un reloj "
            "térmico definido desde poda.",
        ) if corr_gdd > 0.98 and clima.gdd_semana.min() > 0 else ui.semaforo(
            "info",
            "**No aparece una redundancia extrema entre GDD y temperatura** bajo este "
            "control; aun así, ambas variables pueden compartir parte del calendario.",
        ),
        ui.plegable(
            "Ver la auditoría completa de cada ventana",
            ui.tabla_desde_df(detalles),
            ui.parrafo(
                "La implementación es técnicamente consistente: el clima se calcula una "
                "vez por semana y el riego por Fundo–Módulo, sin rellenar ventanas "
                "incompletas. Lo que todavía no está demostrado es que 2–7 semanas "
                "represente el tiempo biológico de cada variable."
            ),
        ),
        ayuda="Cómo se construyeron las siete entradas y qué límites tienen antes de interpretar el modelo.",
    )


def _como_esta_ajustado() -> html.Div:
    historico = pd.DataFrame({
        "Configuración histórica": [
            "Anterior (prof. 3, η 0,03)",
            "Prof. 6, η 0,01, hoja ≥ 10, λ 5",
            "Piso: predecir la media",
        ],
        "R² selección": [0.344, 0.402, None],
        "R² honesto": [-0.116, 0.053, -0.147],
        "MAE honesto (kg/ha)": [757, 686, 756],
    })
    hiperparams = pd.DataFrame({
        "Parámetro": [
            "n_estimators", "max_depth", "learning_rate", "min_child_weight",
            "reg_lambda", "subsample", "colsample_bytree",
        ],
        "Valor": [
            PARAMS["n_estimators"], PARAMS["max_depth"], PARAMS["learning_rate"],
            PARAMS["min_child_weight"], PARAMS["reg_lambda"], PARAMS["subsample"],
            PARAMS["colsample_bytree"],
        ],
        "Qué controla": [
            "Cuántos árboles se encadenan.",
            "Profundidad de cada árbol.",
            "Cuánto aporta cada árbol.",
            "Mínimo de observaciones por hoja.",
            "Penalización L2 sobre el valor de las hojas.",
            "Fracción de filas que ve cada árbol.",
            "Fracción de variables que ve cada árbol.",
        ],
    })
    return ui.panel(
        "4 · Cómo está ajustado",
        ui.parrafo(
            "La calibración tuvo dos etapas: **108 combinaciones** sobre la formulación "
            "inicial y un re-barrido de **264 configuraciones** después de incorporar las "
            "siete variables y sus ventanas. La regla fue elegir mirando «deja-una-semana "
            "fuera» y reportar «deja-un-bloque-fuera»; elegir mirando la métrica que luego "
            "se publica la infla."
        ),
        ui.plegable(
            "Historial de la calibración inicial",
            ui.parrafo(
                "Estas cifras pertenecen a la etapa anterior a la formulación vigente de "
                "ventanas. Se conservan como trazabilidad, no como resultado actual."
            ),
            ui.tabla_desde_df(historico, formato={
                "R² selección": "{:+.3f}",
                "R² honesto": "{:+.3f}",
                "MAE honesto (kg/ha)": "{:.0f}",
            }),
        ),
        ui.plegable(
            "Los hiperparámetros, uno por uno",
            ui.tabla_desde_df(hiperparams),
        ),
        ui.semaforo(
            "aviso",
            "**Ajustar el algoritmo no arregla la pregunta de fondo.** La mejora de una "
            "configuración fortalece el instrumento predictivo; no convierte una ventana "
            "de calendario en una fase biológica ni cambia una asociación observacional en "
            "un efecto causal.",
        ),
        ayuda="Trazabilidad de la calibración y límites que ningún hiperparámetro resuelve.",
    )


def _figura_comparacion(comparacion: pd.DataFrame) -> go.Figure:
    orden = comparacion.sort_values("R² deja-un-bloque")
    colores = [
        "#3B7DD8" if modelo == "XGBoost (el del tablero)"
        else "#D9822B" if modelo == "Random Forest"
        else "#94a3b8"
        for modelo in orden.Modelo
    ]
    fig = go.Figure(go.Bar(
        x=orden["R² deja-un-bloque"],
        y=orden.Modelo,
        orientation="h",
        marker_color=colores,
        text=[f"{valor:+.3f}" for valor in orden["R² deja-un-bloque"]],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{y}<br>R² deja-un-bloque = %{x:+.3f}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#94a3b8")
    fig.update_layout(
        height=360,
        margin={"l": 8, "r": 48, "t": 18, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "ui-sans-serif, system-ui, sans-serif", "color": "#475569"},
        xaxis={"title": "R² fuera de muestra · bloque temporal", "gridcolor": "#e7e5e4"},
        yaxis={"gridcolor": "#f5f5f4"},
        hoverlabel={"bgcolor": "#ffffff", "bordercolor": "#d6d3d1"},
    )
    fig.add_annotation(
        x=1, y=1.08, xref="paper", yref="paper", xanchor="right",
        text="Azul: referencia actual · naranja: alternativa sin calibrar",
        showarrow=False, font={"size": 11, "color": "#64748b"},
    )
    return fig


def _render_comparacion(panel) -> html.Div:
    try:
        comparacion = _comparacion(panel)
    except Exception as exc:  # pragma: no cover - protección de la UI ante datos inválidos
        return ui.semaforo("error", f"No se pudo comparar las familias: {exc}")

    piso = float(comparacion.loc[comparacion.Modelo == "Predecir la media", "R² deja-un-bloque"].iloc[0])
    xgb = float(comparacion.loc[comparacion.Modelo == "XGBoost (el del tablero)", "R² deja-un-bloque"].iloc[0])
    mejor = comparacion.loc[comparacion["R² deja-un-bloque"].idxmax()]
    lineal = float(comparacion.loc[comparacion.Modelo == "Regresión lineal", "R² deja-un-bloque"].iloc[0])
    ganador = str(mejor.Modelo)
    if ganador == "XGBoost (el del tablero)":
        veredicto = (
            f"**XGBoost queda arriba en esta comparación:** {xgb:+.3f} frente al piso "
            f"({piso:+.3f}). La ventaja es predictiva bajo esta partición, no causal."
        )
        estado = "ok"
    else:
        veredicto = (
            f"**Random Forest aparece por encima en esta comparación puntual:** "
            f"{float(mejor['R² deja-un-bloque']):+.3f} frente a XGBoost ({xgb:+.3f}). "
            "Eso no basta para cambiar el modelo de referencia: Random Forest está aquí "
            "con una configuración fija y todavía no pasó por el mismo barrido de "
            "hiperparámetros, semillas y criterio de estabilidad."
        )
        estado = "aviso"

    return ui.panel(
        "3 · Por qué el tablero conserva XGBoost",
        ui.parrafo(
            "La gráfica responde primero una pregunta de control: ¿una familia no lineal "
            "aporta algo frente a predecir siempre la media? Se comparan los mismos datos, "
            "las mismas variables y las mismas particiones; la métrica principal es "
            "«deja-un-bloque-fuera», porque retiene un tramo temporal que el modelo no vio."
        ),
        dcc.Graph(figure=_figura_comparacion(comparacion), config={"displaylogo": False}),
        ui.semaforo(estado, veredicto),
        ui.subseccion(
            "Qué sí demuestra esta gráfica",
            ui.parrafo(
                f"Las familias de árboles quedan por encima del piso ({piso:+.3f}), mientras "
                f"la regresión lineal cae a {lineal:+.3f}. La estructura no lineal —umbrales "
                "e interacciones— sí es necesaria para esta base. La gráfica no demuestra, "
                "por sí sola, que XGBoost sea superior a Random Forest."
            ),
        ),
        ui.subseccion(
            "Por qué se conserva XGBoost como referencia",
            ui.parrafo(
                "XGBoost es el modelo que se calibró y versionó para el tablero: se probaron "
                "las ventanas temporales y los hiperparámetros con partición temporal, y la "
                "configuración vigente se mantuvo después de verificar su estabilidad entre "
                "semillas. Random Forest es una alternativa prometedora que esta gráfica "
                "pone sobre la mesa, pero no una sustitución validada todavía. Cambiarlo "
                "exigiría repetir esa misma disciplina antes de presentarlo como el modelo "
                "oficial."
            ),
        ),
        ui.semaforo(
            "info",
            f"**La regresión lineal queda por debajo del piso:** {lineal:+.3f} frente a "
            f"{piso:+.3f}. Eso indica que una recta extrapola mal este bloque temporal; no "
            "demuestra por sí solo que XGBoost sea una explicación agronómica.",
        ),
        ui.plegable(
            "Ver las dos particiones y el MAE",
            ui.tabla_desde_df(comparacion, formato={
                "R² deja-una-semana": "{:+.3f}",
                "R² deja-un-bloque": "{:+.3f}",
                "MAE bloque (kg/ha)": "{:.0f}",
            }),
            ui.como_leer(
                "La barra muestra solo R² deja-un-bloque: cuanto más a la derecha, mejor "
                "generaliza en ese tramo retenido. El valor puede ser negativo cuando el "
                "modelo predice peor que la media. «Deja-una-semana» es una prueba más "
                "cercana a interpolar y por eso no reemplaza al bloque temporal. El azul es "
                "la referencia actual del tablero; el naranja es una alternativa que aún "
                "no tiene una calibración equivalente.",
            ),
        ),
        ayuda="Comparación honesta de familias predictivas antes de justificar la elección del algoritmo.",
    )


@callback(Output("modelo-principal", "children"), Input(PANEL_STORE, "data"))
def _render_principal(panel):
    if panel is None:
        return ui.esqueleto_pagina()
    # La comparación empieza al abrir la página, pero queda en su propia salida: el primer
    # viewport no espera a las seis familias y volver al módulo reutiliza la misma Future.
    precargar(panel, {_FAMILIAS_CACHE: lambda: nucleo.comparar_familias(panel.tabla)})
    return html.Div(
        className="space-y-4",
        children=[
            ui.encabezado_pagina(
                "¿El modelo aprende una señal útil sin confundirse con el calendario?",
                "Aquí auditamos el instrumento predictivo: qué recibe, cómo se ajustó y si "
                "la familia elegida merece sostenerse. La generalización y la explicación "
                "interna tienen páginas propias.",
            ),
            _kpis(panel),
            _respuesta_corta(),
            _que_hace(),
            _ventanas(panel),
            _como_esta_ajustado(),
        ],
    )


@callback(Output("modelo-familias", "children"), Input(PANEL_STORE, "data"))
def _render_familias(panel):
    if panel is None:
        return ui.esqueleto_seccion("h-64")
    return _render_comparacion(panel)

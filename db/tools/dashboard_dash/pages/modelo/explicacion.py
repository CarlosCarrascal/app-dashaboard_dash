"""Página «Explicación del modelo» — puerto completo de `dashboard/vistas/explicacion.py`
(= `importancia.py` + `auditoria.py`).

SHAP global (ranking, nube de efectos, dependencia por variable) y auditoría de una
celda concreta (waterfall + demostración de que la suma cierra). Sin lectura causal en
ningún lado: SHAP reparte lo que el modelo ya aprendió, no mide un efecto de campo.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import dash
from dash import dcc, html
from dash_extensions.enrich import Input, Output, callback

import graficos as g
import nucleo
from config import FEATURES, PARAMS, etiqueta
from components import ui
from servicios.carga import PANEL_STORE
from servicios.modelo import entrenar

dash.register_page(__name__, path="/modelo/explicacion", name="Explicación del modelo", order=2, grupo="Modelo predictivo")

BLOQUES = {"global": "Comportamiento global (SHAP)", "celda": "Auditoría de una celda"}

# clave interna → (etiqueta corta, unidad) — igual que `OBJETIVOS_SHAP` del Streamlit.
OBJETIVOS_SHAP: dict[str, tuple[str, str]] = {
    "KgHa": ("kg/ha", "kg/ha"),
    "Frutos": ("Frutos", "frutos/planta"),
    "Peso": ("Peso", "g"),
    "flores_promedio": ("Floración", "flores/turno"),
}


def layout():
    return html.Div(
        className="space-y-4",
        children=[
            ui.semaforo(
                "info",
                "Esta sección explica **cómo XGBoost usa las variables**. SHAP reparte "
                "una predicción del modelo; no estima cuánto cambiaría el campo al "
                "intervenir una variable climática.",
            ),
            dcc.RadioItems(
                id="explicacion-bloque",
                options=[{"label": v, "value": k} for k, v in BLOQUES.items()],
                value="global", inline=True, className="flex gap-4 text-sm",
            ),
            html.Div(id="explicacion-contenido", className="pt-2"),
        ],
    )


@callback(
    Output("explicacion-contenido", "children"),
    Input(PANEL_STORE, "data"),
    Input("explicacion-bloque", "value"),
)
def _shell(panel, bloque):
    if panel is None:
        return ui.semaforo("aviso", "Cargando el panel…")

    if bloque == "celda":
        modulos = sorted(panel.tabla.celda.unique())
        return html.Div(
            className="space-y-4",
            children=[
                html.Div(
                    className="grid grid-cols-2 gap-3",
                    children=[
                        html.Div([
                            html.Label("Módulo", className="text-xs font-medium text-slate-500"),
                            dcc.Dropdown(id="celda-modulo", options=modulos, value=modulos[0], clearable=False),
                        ]),
                        html.Div([
                            html.Label("Semana", className="text-xs font-medium text-slate-500"),
                            dcc.Dropdown(id="celda-semana", clearable=False),
                        ]),
                    ],
                ),
                html.Div(id="celda-contenido"),
            ],
        )

    disponibles = [
        o for o in OBJETIVOS_SHAP
        if o in panel.tabla.columns and panel.tabla[o].notna().sum() >= 30
    ]
    return html.Div(
        className="space-y-4",
        children=[
            html.Div([
                html.Label("Objetivo a explicar", className="text-xs font-medium text-slate-500"),
                dcc.Dropdown(
                    id="explicacion-objetivo",
                    options=[{"label": OBJETIVOS_SHAP[o][0], "value": o} for o in disponibles],
                    value=disponibles[0] if disponibles else None,
                    clearable=False, className="max-w-xs",
                ),
            ]),
            html.Div(id="explicacion-global-body"),
        ],
    )


@callback(
    Output("celda-semana", "options"), Output("celda-semana", "value"),
    Input(PANEL_STORE, "data"), Input("celda-modulo", "value"),
)
def _opciones_semana(panel, modulo):
    if panel is None or modulo is None:
        return [], None
    semanas = panel.tabla.loc[panel.tabla.celda == modulo].sort_values("nsem")
    kg_por_semana = dict(zip(semanas.Semana, semanas.KgHa, strict=True))
    opciones = [{"label": f"{s}  ·  {ui.miles(kg_por_semana[s])} kg/ha", "value": s} for s in semanas.Semana]
    return opciones, (semanas.Semana.iloc[0] if len(semanas) else None)


def _ranking(ajuste, etiqueta_obj: str, unidad: str) -> html.Div:
    imp = ajuste.importancia
    return html.Div(
        className="space-y-3",
        children=[
            ui.titulo_seccion("Cuánto mueve cada variable"),
            ui.tarjetas([
                ("La que más pesa", etiqueta(imp.index[0]), f"Mayor efecto absoluto promedio sobre {etiqueta_obj.lower()}."),
                ("Cuánto mueve", f"±{imp.iloc[0]:,.2f} {unidad}".replace(",", "."), "Promedio del valor absoluto de su efecto en todas las celdas."),
                ("La que menos pesa", etiqueta(imp.index[-1]), None),
                ("Cuánto mueve", f"±{imp.iloc[-1]:,.2f} {unidad}".replace(",", "."), None),
            ]),
            dcc.Graph(figure=g.barras_importancia(imp), config={"displaylogo": False}),
            ui.semaforo(
                "info",
                f"**Objetivo explicado:** {etiqueta_obj}. Este gráfico muestra cómo "
                "XGBoost reparte el crédito en conjunto bajo la ventana de desfase "
                "vigente (ver «Modelo predictivo → Auditoría de desfases»). La "
                "configuración de referencia (riego = 7 sem., clima 2-7 sem. según la "
                "variable) fue la que mejor funcionó como configuración predictiva "
                "**para kg/ha**; Frutos, Peso y Floración reusan la misma ventana, no "
                "tienen una calibración propia todavía. Eso no demuestra que el riego o "
                "el clima actúen exactamente con ese desfase: son ventanas elegidas "
                "para predecir, no fases fenológicas medidas.",
            ),
            ui.como_leer(
                "Cada barra es el **promedio del valor absoluto** del efecto de esa "
                f"variable, en {unidad}. Se toma el valor absoluto porque a veces "
                "empuja hacia arriba y a veces hacia abajo: lo que mide la barra es "
                "**cuánto mueve**, no en qué dirección.\n\n"
                "**Ojo con la lectura fácil.** Que una variable encabece el ranking no "
                "significa que sea la palanca a accionar. Significa que el modelo la "
                "usa mucho — y el modelo puede estar usándola como marcador del "
                "calendario. La sección **Qué explica el R²** distingue las dos cosas "
                "con la columna de *aporte marginal*.",
                "Cómo se lee este ranking",
            ),
        ],
    )


def _summary(panel, ajuste, unidad: str) -> html.Div:
    orden = list(ajuste.importancia.index)[::-1]
    tabla_alineada = panel.tabla.loc[ajuste.X.index]
    return html.Div(
        className="space-y-3",
        children=[
            ui.titulo_seccion("Efecto celda por celda"),
            dcc.Graph(figure=g.summary_shap(ajuste.shap_values, ajuste.X, orden, tabla_alineada, unidad),
                     config={"displaylogo": False}),
            ui.como_leer(
                "Cada **punto** es una de las celdas módulo × semana del panel.\n\n"
                "- **Eje horizontal:** cuánto aportó esa variable en esa celda. A la "
                "derecha del cero empujó hacia arriba; a la izquierda, hacia abajo.\n"
                "- **Color:** si el valor de la variable era alto (rojo) o bajo (azul) "
                "en esa celda.\n"
                "- **Ancho de la nube:** cuánto varía el efecto. Una nube ancha "
                "significa que la variable a veces suma mucho y a veces resta mucho; "
                "una nube apretada en el cero significa que casi nunca importa.\n\n"
                "**El patrón que hay que buscar:** si los puntos rojos están todos de "
                "un lado y los azules del otro, la relación es consistente y "
                "direccional. Si están mezclados, el efecto depende de otras "
                "variables."
            ),
        ],
    )


@callback(
    Output("explicacion-global-body", "children"),
    Input(PANEL_STORE, "data"), Input("explicacion-objetivo", "value"),
)
def _render_global(panel, objetivo):
    if panel is None or objetivo is None:
        return None
    ajuste = entrenar(panel.tabla, objetivo=objetivo)
    etiqueta_obj, unidad = OBJETIVOS_SHAP[objetivo]
    return html.Div(
        className="space-y-6",
        children=[
            html.Details(className="rounded-lg border border-slate-200 p-3", children=[
                html.Summary("¿Qué es SHAP y qué significan estos números?", className="cursor-pointer text-sm font-medium text-slate-600"),
                html.Div(className="mt-2 space-y-2", children=[
                    ui.parrafo(
                        "**SHAP** (*SHapley Additive exPlanations*) responde a una "
                        f"pregunta concreta: de la diferencia entre {etiqueta_obj} de "
                        "esta celda y el promedio de todas, ¿cuánto le toca a cada "
                        "variable?\n\n"
                        "La idea viene de la teoría de juegos: si varios jugadores "
                        "cooperan y ganan un premio, ¿cómo se reparte de forma justa? "
                        "El valor de Shapley es la única forma de repartirlo que cumple "
                        "ciertas reglas razonables — entre ellas, que **las partes "
                        "sumen exactamente el total**.\n\n"
                        f"Acá el «premio» es {etiqueta_obj.lower()}, el promedio "
                        f"general es **{ajuste.base_value:,.2f} {unidad}**".replace(",", ".")
                        + f", y los {len(FEATURES)} jugadores son las variables."
                    ),
                    ui.parrafo(
                        "**Cómo leer el signo:**\n"
                        "- Un valor SHAP **positivo** significa que esa variable, con "
                        f"el valor que tomó en esa semana, empujó {etiqueta_obj.lower()} "
                        "**por encima** del promedio.\n"
                        "- **Negativo**: lo empujó **por debajo**.\n"
                        "- Cerca de **cero**: esa variable no movió la aguja en esa "
                        "celda.\n\n"
                        "El signo describe **el comportamiento del modelo**, no una "
                        "ley agronómica. Que una variable tenga efecto negativo "
                        "significa que en esta campaña sus semanas altas acompañaron "
                        "valores bajos de este objetivo — no que subirla en el campo "
                        "lo reduzca. La sección **Impacto agronómico** desarma esa "
                        "lectura con las pruebas de Evidencia."
                    ),
                ]),
            ]),
            _ranking(ajuste, etiqueta_obj, unidad),
            _summary(panel, ajuste, unidad),
            html.Div(
                className="space-y-3",
                children=[
                    ui.titulo_seccion("Dependencia SHAP"),
                    ui.parrafo(
                        "Este gráfico responde: **a medida que una variable sube, "
                        f"¿cómo cambia su propio efecto sobre {etiqueta_obj.lower()}?** "
                        "Es la forma de la relación tal como la aprendió el modelo, sin "
                        "suponer que sea una recta."
                    ),
                    dcc.Dropdown(
                        id="explicacion-dep-var",
                        options=[{"label": etiqueta(c), "value": c} for c in FEATURES],
                        value=FEATURES[0], clearable=False, className="max-w-xs",
                    ),
                    html.Div(id="explicacion-dep-body"),
                ],
            ),
            ui.glosario(list(FEATURES)),
        ],
    )


@callback(
    Output("explicacion-dep-body", "children"),
    Input(PANEL_STORE, "data"), Input("explicacion-objetivo", "value"), Input("explicacion-dep-var", "value"),
)
def _render_dependencia(panel, objetivo, var):
    if panel is None or objetivo is None or var is None:
        return None
    ajuste = entrenar(panel.tabla, objetivo=objetivo)
    etiqueta_obj, unidad = OBJETIVOS_SHAP[objetivo]
    j = list(ajuste.X.columns).index(var)
    valores = ajuste.X[var].to_numpy()
    efectos = ajuste.shap_values[:, j]
    n_unicos = int(np.unique(valores).size)

    bloques = [
        dcc.Graph(
            figure=g.dependencia_shap(ajuste.shap_values, ajuste.X, var, panel.tabla.loc[ajuste.X.index, "nsem"], unidad),
            config={"displaylogo": False},
        ),
    ]
    if n_unicos <= ajuste.X.shape[0] // 3:
        bloques.append(ui.semaforo(
            "info",
            f"{etiqueta(var)} solo toma **{n_unicos} valores distintos** en las "
            f"{ajuste.X.shape[0]} celdas del ajuste — normal en las variables "
            "climáticas: se miden una vez por semana y ese mismo valor se repite en "
            "todos los módulos de esa semana. Por eso el gráfico se ve como columnas "
            "verticales apiladas y no como una nube continua. **No es un error.**",
        ))

    corte = float(np.median(valores))
    bajo = float(efectos[valores <= corte].mean())
    alto = float(efectos[valores > corte].mean())
    bloques.append(ui.tarjetas([
        (f"Efecto medio con {etiqueta(var)} baja", f"{bajo:+,.2f} {unidad}".replace(",", "."), f"Celdas por debajo de la mediana ({corte:.2f})."),
        (f"Efecto medio con {etiqueta(var)} alta", f"{alto:+,.2f} {unidad}".replace(",", "."), f"Celdas por encima de la mediana ({corte:.2f})."),
        ("Diferencia", f"{alto - bajo:+,.2f} {unidad}".replace(",", "."), "Cuánto cambia el efecto al pasar de valores bajos a altos."),
    ]))
    bloques.append(ui.como_leer(
        "**Qué es cada eje.**\n"
        f"- **Horizontal:** el valor de {etiqueta(var)} en cada celda.\n"
        f"- **Vertical:** cuánto le atribuyó SHAP a {etiqueta(var)}, en {unidad}, en "
        "esa misma celda.\n"
        "- **Color:** la semana del año, para que se vea si el patrón sigue al "
        "calendario.\n\n"
        "**Cómo se interpreta la forma.**\n"
        "- Una nube que **baja de izquierda a derecha** significa que valores altos "
        f"de la variable acompañan {etiqueta_obj.lower()} por debajo del promedio.\n"
        "- Una nube **plana** significa que el modelo apenas usa esa variable.\n"
        "- Un **quiebre** sugiere un umbral: el efecto aparece solo pasado cierto "
        "valor.\n"
        "- **Dispersión vertical** a un mismo valor de X indica interacción.\n\n"
        "**Advertencia de lectura.** Si los colores se ordenan de izquierda a "
        "derecha, lo que estás viendo es el calendario disfrazado de variable. Ése es "
        "exactamente el problema que la sección **Impacto agronómico** cuantifica.",
        "Cómo se lee la dependencia SHAP",
    ))
    return html.Div(bloques, className="space-y-3")


def _ecuacion(base: float, contribuciones: pd.Series, prediccion: float) -> str:
    orden = contribuciones.reindex(contribuciones.abs().sort_values(ascending=False).index)
    ancho = max(len(etiqueta(v)) for v in orden.index)
    lineas = [f"    {ui.miles(base, '{:,.1f}'):>10}   valor base (promedio del panel)"]
    for var, valor in orden.items():
        signo = "+" if valor >= 0 else "−"
        lineas.append(f"{signo}   {ui.miles(abs(valor), '{:,.1f}'):>10}   {etiqueta(var):<{ancho}}")
    lineas.append("    " + "─" * 16)
    lineas.append(f"  = {ui.miles(prediccion, '{:,.1f}'):>10}   kg/ha del modelo (suma exacta)")
    return "\n".join(lineas)


@callback(
    Output("celda-contenido", "children"),
    Input(PANEL_STORE, "data"), Input("celda-modulo", "value"), Input("celda-semana", "value"),
)
def _render_celda(panel, modulo, semana):
    if panel is None or modulo is None or semana is None:
        return None

    tabla = panel.tabla
    indice = tabla.index[(tabla.celda == modulo) & (tabla.Semana == semana)][0]
    fila = tabla.loc[indice]
    ajuste = entrenar(tabla, objetivo="KgHa")

    if not ajuste.tiene(indice):
        return html.Div([
            ui.semaforo(
                "aviso",
                f"**{modulo} · {semana} no tiene ventana de rezago completa** (el "
                "módulo empezó a cosechar hace menos semanas que la ventana "
                "configurada, o tuvo un hueco justo antes). El modelo se entrenó sin "
                "esta celda — no hay «kg/ha del modelo» que mostrar para ella. Elegí "
                "otra semana.",
            ),
            ui.caja(
                html.Div("kg/ha real", className="text-xs text-slate-500"),
                html.Div(ui.miles(fila.KgHa), className="mt-1 text-2xl font-semibold"),
            ),
        ], className="space-y-3")

    contribuciones = ajuste.contribuciones(indice)
    prediccion = ajuste.prediccion(indice)
    consistencia = nucleo.verificar_consistencia(ajuste)

    detalle = pd.DataFrame({
        "Variable": [etiqueta(f) for f in FEATURES],
        "Valor": [fila[f] for f in FEATURES],
        "Efecto (kg/ha)": [contribuciones[f] for f in FEATURES],
    }).sort_values("Efecto (kg/ha)", key=abs, ascending=False)

    serie = tabla[tabla.celda == modulo].sort_values("nsem")

    return html.Div(
        className="space-y-4",
        children=[
            html.Div(
                className="grid grid-cols-3 gap-3",
                children=[
                    ui.caja(html.Div("kg/ha real", className="text-xs text-slate-500"),
                           html.Div(ui.miles(fila.KgHa), className="mt-1 text-xl font-semibold")),
                    ui.caja(html.Div("kg/ha del modelo", className="text-xs text-slate-500"),
                           html.Div(ui.miles(prediccion), className="mt-1 text-xl font-semibold"),
                           html.Div(f"{ui.miles(prediccion - fila.KgHa, '{:+,.0f}')} vs real", className="text-xs text-slate-400")),
                    ui.caja(html.Div("Riego esa semana", className="text-xs text-slate-500"),
                           html.Div(f"{ui.miles(fila.riego_lt_planta, '{:,.2f}')} L/planta", className="mt-1 text-xl font-semibold")),
                ],
            ),
            ui.titulo_seccion("SHAP Waterfall", "h4"),
            dcc.Graph(figure=g.waterfall(ajuste.base_value, contribuciones, prediccion, f"{modulo} · {semana}"),
                     config={"displaylogo": False}),
            html.Details(className="rounded-lg border border-slate-200 p-3", children=[
                html.Summary("¿En qué cálculo se basa el «kg/ha del modelo»? Ver la demostración",
                            className="cursor-pointer text-sm font-medium text-slate-600"),
                html.Div(className="mt-2 space-y-2", children=[
                    ui.parrafo(
                        f"**Paso 1 — el modelo.** XGBoost ajustó {PARAMS['n_estimators']} "
                        f"árboles de decisión (profundidad {PARAMS['max_depth']}) sobre "
                        f"las {len(ajuste.X)} celdas del panel, cada uno corrigiendo el "
                        "error que dejó el anterior (*gradient boosting*)."
                    ),
                    ui.parrafo(
                        f"**Paso 2 — repartir ese número entre las {len(FEATURES)} "
                        "variables.** SHAP reparte la diferencia entre la predicción de "
                        "esta celda y el promedio general del panel, de forma que la "
                        "suma sea exacta, no aproximada. Para un modelo de árboles, "
                        "`TreeExplainer` no estima esa suma por muestreo: recorre la "
                        "estructura exacta de los árboles y calcula el valor de Shapley "
                        "de forma cerrada."
                    ),
                    html.P(f"La demostración, con los números de {modulo} · {semana}:", className="font-medium"),
                    html.Pre(_ecuacion(ajuste.base_value, contribuciones, prediccion),
                            className="overflow-x-auto rounded bg-slate-50 p-3 text-xs"),
                    ui.semaforo(
                        "ok" if consistencia.todas_coinciden else "error",
                        (f"**Verificado, no asumido:** la misma igualdad se comprobó para "
                         f"las {consistencia.n_filas} filas del panel, no solo para ésta. "
                         f"Coincide en {consistencia.coinciden} de {consistencia.n_filas} "
                         f"(diferencia máxima: {consistencia.diferencia_maxima:.4f} kg/ha, "
                         "redondeo de punto flotante).") if consistencia.todas_coinciden else
                        (f"La igualdad NO se cumple en {consistencia.n_filas - consistencia.coinciden} "
                         f"de {consistencia.n_filas} filas — hay un error de cálculo en "
                         "esta versión del tablero, no en la teoría."),
                    ),
                    ui.semaforo(
                        "aviso",
                        "**Qué NO demuestra esto.** Que la suma cierre exactamente "
                        "prueba que el reparto está bien calculado — no prueba que el "
                        "modelo generalice a datos nuevos ni que exista una relación "
                        "causal. Lo primero se mide en **Qué explica el R²**. Lo "
                        "segundo no lo puede probar ningún reparto interno de un modelo "
                        "observacional.",
                    ),
                ]),
            ]),
            ui.titulo_seccion("Valores de esa semana", "h4"),
            ui.tabla_desde_df(detalle, formato={"Valor": "{:.2f}", "Efecto (kg/ha)": "{:+.0f}"}),
            ui.titulo_seccion("El módulo a lo largo de la campaña", "h4"),
            dcc.Graph(figure=g.serie_del_modulo(serie, int(fila.nsem)), config={"displaylogo": False}),
        ],
    )

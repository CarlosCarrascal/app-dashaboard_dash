"""Página «Explicación del modelo».

La vista global muestra cómo XGBoost reparte sus predicciones entre las variables. La
vista de una celda demuestra la suma completa, desde el valor base hasta el kg/ha
predicho. SHAP describe el comportamiento del modelo; no estima un efecto de campo.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import dash
from dash import dcc, html
from dash_extensions.enrich import Input, Output, callback

from analitica import nucleo
from analitica.config import FEATURES, PARAMS, etiqueta
from analitica.visualizaciones import graficos as g
from components import ui
from servicios.cache_analisis import precargar
from servicios.carga import PANEL_STORE
from servicios.modelo import entrenar

dash.register_page(
    __name__, path="/modelo/explicacion", name="Explicación del modelo", order=2,
    grupo="Modelo predictivo",
)

BLOQUES = {"global": "Global (SHAP)", "celda": "Una celda"}

OBJETIVOS_SHAP: dict[str, tuple[str, str]] = {
    "KgHa": ("kg/ha", "kg/ha"),
    "Frutos": ("Frutos", "frutos/planta"),
    "Peso": ("Peso", "g"),
    "flores_promedio": ("Floración", "flores/turno"),
}

_TAB_STYLE = {
    "padding": "0.7rem 1rem",
    "border": "none",
    "borderBottom": "2px solid transparent",
    "backgroundColor": "transparent",
    "color": "#64748b",
    "fontSize": "0.9rem",
    "fontWeight": "500",
}
_TAB_SELECTED_STYLE = {
    **_TAB_STYLE,
    "borderBottom": "2px solid #3B7DD8",
    "color": "#0f172a",
    "fontWeight": "600",
}


def _estilo_figura(fig, altura: int):
    """Acabado común de las gráficas embebidas en los paneles del dashboard."""
    fig.update_layout(
        height=altura,
        margin={"l": 8, "r": 8, "t": 20, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "ui-sans-serif, system-ui, sans-serif", "color": "#475569"},
        hoverlabel={"bgcolor": "#ffffff", "bordercolor": "#d6d3d1"},
    )
    fig.update_xaxes(gridcolor="#e7e5e4", zeroline=False)
    fig.update_yaxes(gridcolor="#f5f5f4", zeroline=False)
    return fig


def _etiqueta_corta(columna: str) -> str:
    """Nombre compacto para una card; la etiqueta completa queda en la nota."""
    nombres = {
        "DPV_lag": "DPV móvil",
        "riego_lag": "Riego móvil",
        "Rad_lag": "Radiación móvil",
        "ETo_lag": "ETo móvil",
        "gdd_lag": "GDD móvil",
        "TempMax": "Temp. máxima",
        "TempMin": "Temp. mínima",
    }
    return nombres.get(columna, etiqueta(columna))


def layout():
    return html.Div(
        className="space-y-4",
        children=[
            ui.encabezado_pagina(
                "¿Cómo convierte el modelo las variables en una predicción?",
                "SHAP abre el modelo por dentro: primero vemos qué variables usa en conjunto; "
                "después comprobamos cómo se forma el valor de una celda concreta.",
            ),
            ui.panel(
                "Respuesta corta",
                ui.semaforo(
                    "info",
                    "**SHAP explica el modelo, no el campo.** Un valor positivo significa que "
                    "esa variable empujó la predicción por encima del promedio del panel; "
                    "uno negativo la empujó por debajo. La suma puede cerrar exactamente y "
                    "aun así no demostrar causalidad ni generalización.",
                ),
                html.Div(
                    className="grid gap-4 sm:grid-cols-2",
                    children=[
                        html.Div([
                            html.Div("Este análisis responde", className="text-sm font-semibold text-slate-700"),
                            html.P(
                                "Qué señales utiliza el predictor y cómo contribuyen a una "
                                "predicción individual.",
                                className="mt-1.5 text-sm leading-relaxed text-slate-600",
                            ),
                        ]),
                        html.Div([
                            html.Div("Cómo ayuda al modelo", className="text-sm font-semibold text-slate-700"),
                            html.P(
                                "Permite distinguir el comportamiento interno del algoritmo "
                                "de un efecto agronómico. La capacidad de generalizar se lee "
                                "en Qué explica el R².",
                                className="mt-1.5 text-sm leading-relaxed text-slate-600",
                            ),
                        ]),
                    ],
                ),
                ayuda="La frontera entre explicar una predicción y explicar el cultivo.",
            ),
            dcc.Tabs(
                id="explicacion-bloque",
                value="global",
                className="border-b border-stone-200",
                colors={"border": "transparent", "primary": "#3B7DD8", "background": "transparent"},
                children=[
                    dcc.Tab(
                        label=nombre, value=clave,
                        style=_TAB_STYLE, selected_style=_TAB_SELECTED_STYLE,
                    )
                    for clave, nombre in BLOQUES.items()
                ],
            ),
            html.Div(
                id="explicacion-contenido",
                className="pt-1",
                children=ui.esqueleto_pagina(),
            ),
        ],
    )


def _disponibles(panel) -> list[str]:
    return [
        objetivo for objetivo in OBJETIVOS_SHAP
        if objetivo in panel.tabla.columns and panel.tabla[objetivo].notna().sum() >= 30
    ]


def _objetivo_selector(panel) -> html.Div:
    disponibles = _disponibles(panel)
    return html.Div(
        className="max-w-sm space-y-1.5",
        children=[
            html.Label("Resultado que quieres explicar", className=ui.SUBTITULO),
            dcc.Dropdown(
                id="explicacion-objetivo",
                options=[{"label": OBJETIVOS_SHAP[o][0], "value": o} for o in disponibles],
                value=disponibles[0] if disponibles else None,
                clearable=False,
            ),
        ],
    )


def _shell_global(panel) -> html.Div:
    return html.Div(
        className="space-y-4",
        children=[
            _objetivo_selector(panel),
            html.Div(id="explicacion-global-body", children=ui.esqueleto_pagina()),
        ],
    )


def _shell_celda(panel) -> html.Div:
    modulos = sorted(panel.tabla.celda.unique())
    return html.Div(
        className="space-y-4",
        children=[
            ui.panel(
                "Elige la celda que quieres auditar",
                html.Div(
                    className="grid gap-3 sm:grid-cols-2",
                    children=[
                        html.Div([
                            html.Label("Módulo", className=ui.SUBTITULO),
                            dcc.Dropdown(
                                id="celda-modulo", options=modulos,
                                value=modulos[0] if modulos else None, clearable=False,
                            ),
                        ]),
                        html.Div([
                            html.Label("Semana", className=ui.SUBTITULO),
                            dcc.Dropdown(id="celda-semana", clearable=False),
                        ]),
                    ],
                ),
                ayuda="La auditoría usa una celda módulo × semana del ajuste completo.",
            ),
            html.Div(id="celda-contenido", children=ui.esqueleto_seccion("h-64")),
        ],
    )


@callback(
    Output("explicacion-contenido", "children"),
    Input(PANEL_STORE, "data"),
    Input("explicacion-bloque", "value"),
)
def _shell(panel, bloque):
    if panel is None:
        return ui.esqueleto_pagina()
    # Global y celda usan el ajuste de kg/ha. Se programa al entrar para que cambiar de
    # pestaña no inicie otro entrenamiento; el callback que llegue primero espera la misma
    # tarea y el resultado persiste por la huella del panel.
    precargar(panel, {"modelo:ajuste:KgHa": lambda: nucleo.entrenar(panel.tabla, objetivo="KgHa")})
    return _shell_celda(panel) if bloque == "celda" else _shell_global(panel)


@callback(
    Output("celda-semana", "options"), Output("celda-semana", "value"),
    Input(PANEL_STORE, "data"), Input("celda-modulo", "value"),
)
def _opciones_semana(panel, modulo):
    if panel is None or modulo is None:
        return [], None
    semanas = panel.tabla.loc[panel.tabla.celda == modulo].sort_values("nsem")
    opciones = [
        {"label": f"{fila.Semana} · {ui.miles(fila.KgHa)} kg/ha", "value": fila.Semana}
        for fila in semanas.itertuples()
    ]
    return opciones, (semanas.Semana.iloc[0] if len(semanas) else None)


def _formato_numero(valor: float, unidad: str) -> str:
    return f"{valor:+,.2f} {unidad}".replace(",", ".")


def _kpis_globales(ajuste, etiqueta_obj: str, unidad: str) -> html.Div:
    imp = ajuste.importancia
    top = imp.index[0]
    return ui.fila_kpi([
        ui.kpi(
            "Celdas explicadas",
            str(len(ajuste.X)),
            nota=f"Celdas con ventana completa para {etiqueta_obj}.",
        ),
        ui.kpi(
            "Variables explicadas",
            str(len(FEATURES)),
            nota="Las mismas 7 entradas del modelo predictivo.",
        ),
        ui.kpi(
            "Variable con más peso",
            _etiqueta_corta(top),
            nota=f"Mayor efecto absoluto promedio sobre {etiqueta_obj}.",
        ),
        ui.kpi(
            "Valor base",
            ui.miles(ajuste.base_value, "{:,.1f}"),
            nota=f"Promedio del panel antes de sumar contribuciones ({unidad}).",
        ),
    ])


def _ranking(ajuste, etiqueta_obj: str, unidad: str) -> html.Div:
    imp = ajuste.importancia
    top = imp.index[0]
    figura = _estilo_figura(g.barras_importancia(imp), 320)
    # La magnitud ya está codificada por el largo; un único azul evita una segunda
    # lectura cromática innecesaria y mantiene el mismo lenguaje de Evidencia.
    figura.update_traces(marker_color="#3B7DD8")
    return ui.panel(
        "1 · Qué variables usa más el modelo",
        ui.parrafo(
            "El ranking ordena las variables por el **promedio del valor absoluto de su "
            f"efecto SHAP** en las {len(ajuste.X)} celdas del ajuste. Es una medida de "
            "uso interno del predictor, no una clasificación de causas agronómicas."
        ),
        dcc.Graph(figure=figura, config={"displaylogo": False, "responsive": True}),
        ui.semaforo(
            "info",
            f"**Para {etiqueta_obj}, la variable que más usa el modelo es {etiqueta(top)}** "
            f"({float(imp.iloc[0]):+.2f} {unidad} de efecto absoluto medio). La ventana "
            "vigente —riego = 7 semanas; clima = 2–7 según variable— fue calibrada para "
            "kg/ha. Frutos, Peso y Floración reutilizan esa ventana y no tienen todavía "
            "una calibración propia. Esto describe el predictor; no identifica una palanca "
            "agronómica.",
        ),
        ui.como_leer(
            "Cada barra es el promedio de cuánto movió una variable la predicción, en "
            f"{unidad}. El valor absoluto oculta si a veces suma y a veces resta; para ver "
            "dirección hay que mirar el enjambre de puntos de la siguiente sección. "
            "Una variable puede encabezar el ranking porque acompaña al calendario: no "
            "significa que accionarla vaya a cambiar el rendimiento.",
            "Cómo se lee este ranking",
        ),
        ayuda="Importancia global de SHAP: magnitud media del uso de cada variable por el modelo.",
    )


def _summary(panel, ajuste, unidad: str) -> html.Div:
    orden = list(ajuste.importancia.index)[::-1]
    tabla_alineada = panel.tabla.loc[ajuste.X.index]
    figura = _estilo_figura(
        g.summary_shap(ajuste.shap_values, ajuste.X, orden, tabla_alineada, unidad),
        400,
    )
    return ui.panel(
        "2 · En qué dirección empuja cada variable",
        ui.parrafo(
            "Cada punto es una celda módulo × semana. El eje horizontal muestra cuánto "
            "empujó la variable la predicción: a la derecha la subió y a la izquierda la "
            "bajó. El color indica si el valor de la variable era alto o bajo."
        ),
        dcc.Graph(
            figure=figura,
            config={"displaylogo": False, "responsive": True},
        ),
        ui.como_leer(
            "Una nube ancha significa que el efecto cambia mucho entre celdas. Si los "
            "puntos rojos y azules quedan mezclados, la relación depende de otras "
            "variables. Si se ordenan con la semana, puede haber calendario disfrazado de "
            "señal climática. El gráfico describe al modelo; no estima un efecto causal.",
        ),
        ayuda="Distribución y dirección de los efectos SHAP celda por celda.",
    )


def _dependencia_shell() -> html.Div:
    return ui.panel(
        "3 · Cómo cambia el efecto cuando cambia una variable",
        ui.parrafo(
            "Esta lectura sigue una variable concreta: a medida que sube su valor, ¿cómo "
            "cambia el efecto que el modelo le asigna? Una nube plana indica poco uso; un "
            "quiebre puede señalar un umbral; una dispersión vertical sugiere interacción."
        ),
        html.Div(
            className="max-w-sm space-y-1.5",
            children=[
                html.Label("Variable a explorar", className=ui.SUBTITULO),
                dcc.Dropdown(
                    id="explicacion-dep-var",
                    options=[{"label": etiqueta(c), "value": c} for c in FEATURES],
                    value=FEATURES[0], clearable=False,
                ),
            ],
        ),
        html.Div(id="explicacion-dep-body", children=ui.esqueleto_seccion("h-64")),
        ayuda="Dependencia SHAP: forma de la relación que el modelo aprendió para una variable.",
    )


@callback(
    Output("explicacion-global-body", "children"),
    Input(PANEL_STORE, "data"), Input("explicacion-objetivo", "value"),
)
def _render_global(panel, objetivo):
    if panel is None or objetivo is None:
        return ui.esqueleto_pagina()
    try:
        ajuste = entrenar(panel, objetivo=objetivo)
    except Exception as exc:  # pragma: no cover - protección de la UI ante datos inválidos
        return ui.semaforo("error", f"No se pudo explicar este objetivo: {exc}")
    etiqueta_obj, unidad = OBJETIVOS_SHAP[objetivo]
    return html.Div(
        className="space-y-4",
        children=[
            _kpis_globales(ajuste, etiqueta_obj, unidad),
            _ranking(ajuste, etiqueta_obj, unidad),
            _summary(panel, ajuste, unidad),
            _dependencia_shell(),
            ui.panel(
                "Glosario de las variables",
                ui.glosario(list(FEATURES), plano=True),
                plegable=True, abierto=False,
                ayuda="Definiciones en lenguaje llano de las entradas que usa el modelo.",
            ),
        ],
    )


@callback(
    Output("explicacion-dep-body", "children"),
    Input(PANEL_STORE, "data"), Input("explicacion-objetivo", "value"),
    Input("explicacion-dep-var", "value"),
)
def _render_dependencia(panel, objetivo, var):
    if panel is None or objetivo is None or var is None:
        return ui.esqueleto_seccion("h-64")
    try:
        ajuste = entrenar(panel, objetivo=objetivo)
    except Exception as exc:  # pragma: no cover - protección de la UI ante datos inválidos
        return ui.semaforo("error", f"No se pudo calcular la dependencia: {exc}")
    etiqueta_obj, unidad = OBJETIVOS_SHAP[objetivo]
    if var not in ajuste.X.columns:
        return ui.semaforo("error", f"La variable {var} no está disponible en este ajuste.")

    j = list(ajuste.X.columns).index(var)
    valores = ajuste.X[var].to_numpy()
    efectos = ajuste.shap_values[:, j]
    n_unicos = int(np.unique(valores).size)
    corte = float(np.median(valores))
    bajo = float(efectos[valores <= corte].mean())
    alto = float(efectos[valores > corte].mean())
    bloques = [
        dcc.Graph(
            figure=_estilo_figura(
                g.dependencia_shap(
                    ajuste.shap_values, ajuste.X, var,
                    panel.tabla.loc[ajuste.X.index, "nsem"], unidad,
                ),
                380,
            ),
            config={"displaylogo": False, "responsive": True},
        ),
    ]
    if n_unicos <= ajuste.X.shape[0] // 3:
        bloques.append(ui.semaforo(
            "info",
            f"{etiqueta(var)} solo toma **{n_unicos} valores distintos** en las "
            f"{ajuste.X.shape[0]} celdas del ajuste. Es normal: el clima se mide una vez "
            "por semana y se repite entre módulos. Por eso aparecen columnas verticales "
            "en vez de una nube continua; **no es un error**.",
        ))
    bloques.extend([
        ui.fila_kpi([
            ui.kpi(
                "Efecto con valor bajo",
                _formato_numero(bajo, unidad),
                nota=f"Celdas por debajo de la mediana ({corte:.2f}).",
                plano=True,
            ),
            ui.kpi(
                "Efecto con valor alto",
                _formato_numero(alto, unidad),
                nota=f"Celdas por encima de la mediana ({corte:.2f}).",
                plano=True,
            ),
            ui.kpi(
                "Diferencia",
                _formato_numero(alto - bajo, unidad),
                nota="Cambio medio del efecto entre valores bajos y altos.",
                plano=True,
            ),
        ]),
        ui.como_leer(
            f"**Eje horizontal:** valor de {etiqueta(var)}. **Eje vertical:** cuánto le "
            f"atribuyó SHAP a {etiqueta(var)} en {unidad}. **Color:** semana del año. Una "
            "pendiente descendente significa que los valores altos acompañan una menor "
            f"predicción de {etiqueta_obj.lower()}; no significa que subir la variable lo "
            "cause. Si los colores se ordenan de izquierda a derecha, la variable puede "
            "estar funcionando como marcador del calendario.",
            "Cómo se lee la dependencia SHAP",
        ),
    ])
    return html.Div(bloques, className="space-y-3")


def _ecuacion(base: float, contribuciones: pd.Series, prediccion: float) -> str:
    orden = contribuciones.reindex(contribuciones.abs().sort_values(ascending=False).index)
    ancho = max(len(etiqueta(v)) for v in orden.index)
    lineas = [f"    {ui.miles(base, '{:,.1f}'):>10}   valor base (promedio del panel)"]
    for var, valor in orden.items():
        signo = "+" if valor >= 0 else "−"
        lineas.append(
            f"{signo}   {ui.miles(abs(valor), '{:,.1f}'):>10}   {etiqueta(var):<{ancho}}"
        )
    lineas.append("    " + "─" * 16)
    lineas.append(f"  = {ui.miles(prediccion, '{:,.1f}'):>10}   kg/ha del modelo (suma exacta)")
    return "\n".join(lineas)


def _kpis_celda(fila, prediccion: float) -> html.Div:
    return ui.fila_kpi([
        ui.kpi(
            "Kg/ha observado",
            ui.miles(fila.KgHa),
            nota="Rendimiento medido en esa celda.",
        ),
        ui.kpi(
            "Kg/ha del modelo",
            ui.miles(prediccion),
            nota=f"Diferencia frente a observado: {ui.miles(prediccion - fila.KgHa, '{:+,.0f}') }.",
        ),
        ui.kpi(
            "Riego de esa semana",
            f"{ui.miles(fila.riego_lt_planta, '{:,.2f}')} L/planta",
            nota="Dato observado; no es una contribución SHAP.",
        ),
        ui.kpi(
            "Error absoluto",
            ui.miles(abs(prediccion - fila.KgHa)),
            nota="Distancia entre el valor observado y la predicción.",
        ),
    ])


@callback(
    Output("celda-contenido", "children"),
    Input(PANEL_STORE, "data"), Input("celda-modulo", "value"), Input("celda-semana", "value"),
)
def _render_celda(panel, modulo, semana):
    if panel is None or modulo is None or semana is None:
        return ui.esqueleto_seccion("h-64")

    tabla = panel.tabla
    coincidencias = tabla.index[(tabla.celda == modulo) & (tabla.Semana == semana)]
    if len(coincidencias) == 0:
        return ui.semaforo("error", f"No existe la celda {modulo} · {semana} en el panel.")
    indice = coincidencias[0]
    fila = tabla.loc[indice]
    try:
        ajuste = entrenar(panel, objetivo="KgHa")
    except Exception as exc:  # pragma: no cover - protección de la UI ante datos inválidos
        return ui.semaforo("error", f"No se pudo auditar la celda: {exc}")

    if not ajuste.tiene(indice):
        return html.Div(
            className="space-y-4",
            children=[
                ui.semaforo(
                    "aviso",
                    f"**{modulo} · {semana} no tiene una ventana completa.** El modelo se "
                    "entrenó sin esta celda —no hay kg/ha predicho ni reparto SHAP que "
                    "mostrar. Elige otra semana.",
                ),
                ui.kpi("Kg/ha observado", ui.miles(fila.KgHa), nota="Dato medido en la celda."),
            ],
        )

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
            _kpis_celda(fila, prediccion),
            ui.panel(
                "1 · Del promedio del panel a esta predicción",
                ui.parrafo(
                    f"La predicción de **{ui.miles(prediccion)} kg/ha** parte del promedio "
                    f"del panel ({ui.miles(ajuste.base_value)} kg/ha) y suma los efectos "
                    f"de las {len(FEATURES)} variables en **{modulo} · {semana}**."
                ),
                dcc.Graph(
                    figure=_estilo_figura(
                        g.waterfall(
                            ajuste.base_value, contribuciones, prediccion, f"{modulo} · {semana}"
                        ),
                        400,
                    ),
                    config={"displaylogo": False, "responsive": True},
                ),
                ayuda="Descomposición de una predicción concreta mediante SHAP.",
            ),
            ui.panel(
                "2 · La suma se puede comprobar",
                ui.parrafo(
                    "SHAP no entrega una explicación aproximada: para este modelo de árboles "
                    "la suma del valor base y las contribuciones reconstruye la predicción. "
                    "La comprobación se hace sobre todas las filas del ajuste, no solo sobre "
                    "la celda seleccionada."
                ),
                ui.plegable(
                    "Ver la demostración numérica",
                    html.Pre(
                        _ecuacion(ajuste.base_value, contribuciones, prediccion),
                        className="overflow-x-auto rounded-lg bg-slate-50 p-3 text-xs",
                    ),
                    ui.semaforo(
                        "ok" if consistencia.todas_coinciden else "error",
                        (f"**Verificado:** coincide en {consistencia.coinciden} de "
                         f"{consistencia.n_filas} filas; diferencia máxima "
                         f"{consistencia.diferencia_maxima:.4f} kg/ha por redondeo.")
                        if consistencia.todas_coinciden else
                        (f"**La igualdad no cierra:** faltan "
                         f"{consistencia.n_filas - consistencia.coinciden} filas. Hay un "
                         "error de cálculo en esta versión del tablero."),
                    ),
                ),
                ui.semaforo(
                    "aviso",
                    "**Qué no demuestra:** que la suma cierre prueba que el reparto está "
                    "bien calculado; no prueba que el modelo generalice ni que una variable "
                    "cause el rendimiento.",
                ),
                ayuda="Prueba interna de consistencia de SHAP, separada de la validación predictiva.",
            ),
            ui.panel(
                "3 · Qué variables empujaron esta semana",
                ui.tabla_desde_df(detalle, formato={"Valor": "{:.2f}", "Efecto (kg/ha)": "{:+.0f}"}),
                ayuda="Valores de entrada y contribución SHAP de la celda seleccionada.",
            ),
            ui.panel(
                "4 · El módulo a lo largo de la campaña",
                ui.parrafo(
                    "Esta serie aporta contexto de calendario: permite ver si la celda "
                    "seleccionada está en una semana atípica de rendimiento o de riego. No "
                    "es otra validación del modelo."
                ),
                dcc.Graph(
                    figure=_estilo_figura(g.serie_del_modulo(serie, int(fila.nsem)), 340),
                    config={"displaylogo": False, "responsive": True},
                ),
                ayuda="Trayectoria observada del módulo y semana auditada.",
            ),
        ],
    )

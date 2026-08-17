"""Página «Frutos y peso».
(incluye `_floracion` y `_desfases_conjunto`) y la lectura integrada de resultados.
_picos_y_clima` / `_peso_y_clima`.

kg/ha no se mide directo: sale de multiplicar frutos por planta por peso del fruto. Esta
página compara clima y riego contra Frutos y Peso por separado (¿el efecto es sobre el
cuajado o sobre el tamaño?), muestra la trayectoria de cada módulo, si la floración
anticipa el cuajado, y qué desfase explica mejor cada uno de los cuatro objetivos.
"""

from __future__ import annotations

import dash
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from dash import dcc, html
from dash_extensions.enrich import Input, Output, callback

from analitica import nucleo
from analitica.config import AZUL, GRIS, ROJO, etiqueta
from components import ui
from servicios.carga import PANEL_STORE

dash.register_page(__name__, path="/impacto/frutos-peso", name="Frutos y peso", order=3, grupo="Impacto agronómico")

VARIABLES_PRE_PEAK = ["TempMin", "DPV", "Rad", "ETo", "riego_lt_planta", "gdd_semana"]
_COLUMNA_PRE_PEAK = {
    "TempMin": "TempMin 4sem pre-peak", "DPV": "DPV 4sem pre-peak", "Rad": "Rad 4sem pre-peak",
    "ETo": "ETo 4sem pre-peak", "riego_lt_planta": "Riego 4sem pre-peak", "gdd_semana": "GDD 4sem pre-peak",
}


def layout():
    return html.Div(id="fp-contenido")


@callback(Output("fp-contenido", "children"), Input(PANEL_STORE, "data"))
def _shell(panel):
    if panel is None:
        return ui.semaforo("aviso", "Cargando el panel…")

    sem = nucleo.clima.agregar_por_semana(panel.tabla)
    if sem.Frutos.notna().sum() < 10:
        return ui.semaforo(
            "aviso",
            "No hay suficientes semanas con Frutos y Peso cargados para esta sección "
            "(la hoja «Kg Reales» no está, o el formato cambió — ver Datos y calidad).",
        )

    modulos = nucleo.clima.trayectorias_frutos_peso(panel.tabla)["Módulo"].tolist()

    return html.Div(
        className="space-y-8",
        children=[
            ui.parrafo(
                "kg/ha no se mide directo: sale de multiplicar **cuántos frutos** hay "
                "por planta y **cuánto pesa cada uno**, por la densidad de plantación. "
                "La hoja «Kg Reales» trae esos dos componentes por separado. "
                "Correlacionarlos contra el clima y el riego, cada uno por su lado, "
                "responde una pregunta que kg/ha solo no puede: ¿el efecto es sobre el "
                "**cuajado** de fruta o sobre su **tamaño**?"
            ),
            ui.semaforo(
                "info",
                "**Qué representa `Frutos`.** El archivo contiene frutos por planta, "
                "no el total absoluto del módulo. Para estimar frutos totales se "
                "necesita además el número efectivo de plantas productivas por módulo "
                "y campaña; no se inventa ese total.",
            ),
            html.Div(
                className="space-y-3",
                children=[
                    ui.titulo_seccion("Cuándo aparece el peak y cómo cambia el peso"),
                    dcc.Dropdown(id="fp-modulo", options=modulos, value=modulos[0] if modulos else None,
                                clearable=False, className="max-w-sm"),
                    html.Div(id="fp-trayectoria-body"),
                ],
            ) if modulos else None,
            html.Hr(className="border-slate-200"),
            _descomposicion(sem),
            html.Hr(className="border-slate-200"),
            _floracion_shell(panel),
            html.Hr(className="border-slate-200"),
            _desfases_shell(sem, panel.tabla),
            html.Hr(className="border-slate-200"),
            _picos_shell(panel),
            html.Hr(className="border-slate-200"),
            _peso_shell(panel),
        ],
    )


@callback(Output("fp-trayectoria-body", "children"), Input(PANEL_STORE, "data"), Input("fp-modulo", "value"))
def _render_trayectoria(panel, modulo):
    if panel is None or modulo is None:
        return None
    trayectorias = nucleo.clima.trayectorias_frutos_peso(panel.tabla)
    serie = panel.tabla[panel.tabla.celda == modulo].dropna(subset=["Frutos", "Peso"]).sort_values("nsem")
    fila = trayectorias.loc[trayectorias["Módulo"] == modulo].iloc[0]
    usa_poda = "dias_desde_poda" in serie.columns and serie.dias_desde_poda.notna().any()
    eje_x = "dias_desde_poda" if usa_poda else "nsem"
    x = serie[eje_x].to_numpy(dtype=float)
    y_peso = serie.Peso.to_numpy(dtype=float)
    y_tendencia = np.polyval(np.polyfit(x, y_peso, 1), x) if len(x) >= 2 else y_peso
    peak = int(fila["Semana peak frutos"])
    huecos = int(fila["Huecos de calendario"])
    titulo_x = "días desde poda (proxy)" if usa_poda else "semana calendario"

    fig_juntas = go.Figure()
    fig_juntas.add_trace(go.Scatter(x=serie[eje_x], y=serie.Frutos, mode="lines+markers", name="Frutos/planta", line={"color": AZUL, "width": 2.5}))
    fig_juntas.add_trace(go.Scatter(x=serie[eje_x], y=serie.Peso, mode="lines+markers", name="Peso (g)", yaxis="y2", line={"color": ROJO, "width": 2.5}))
    fig_juntas.update_layout(
        height=400, xaxis_title=titulo_x, yaxis_title="frutos por planta",
        yaxis2={"title": "peso del fruto (g)", "overlaying": "y", "side": "right", "showgrid": False},
        margin={"l": 10, "r": 10, "t": 10, "b": 10}, legend={"orientation": "h", "y": 1.14},
    )

    fig_frutos = go.Figure(go.Scatter(x=serie[eje_x], y=serie.Frutos, mode="lines+markers", name="Frutos/planta", line={"color": AZUL, "width": 2.8}))
    fig_frutos.add_vline(x=float(fila["Días desde poda peak"]) if usa_poda else peak, line_dash="dash", line_color=ROJO)
    fig_frutos.add_annotation(x=float(fila["Días desde poda peak"]) if usa_poda else peak, y=float(fila["Peak frutos/planta"]),
                              text=f"peak S{peak}", showarrow=True, arrowhead=2)
    fig_frutos.update_layout(height=360, xaxis_title=titulo_x, yaxis_title="frutos por planta", margin={"l": 10, "r": 10, "t": 20, "b": 10})

    fig_peso = go.Figure()
    fig_peso.add_trace(go.Scatter(x=serie[eje_x], y=serie.Peso, mode="lines+markers", name="Peso observado", line={"color": ROJO, "width": 2.8}))
    fig_peso.add_trace(go.Scatter(x=serie[eje_x], y=y_tendencia, mode="lines", name="Tendencia lineal", line={"color": GRIS, "dash": "dash"}))
    fig_peso.update_layout(height=360, xaxis_title=titulo_x, yaxis_title="peso del fruto (g)", margin={"l": 10, "r": 10, "t": 20, "b": 10})

    bloques = [
        ui.tarjetas([
            ("Peak de frutos", f"S{peak}", f"Aparece en la posición {fila['Posición del peak'].lower()} de la ventana observada."),
            ("Frutos en el peak", f"{fila['Peak frutos/planta']:.1f}/planta", "Es un peak semanal; no es todavía el total de la campaña."),
            ("Peso: inicio → final", f"{fila['Peso inicial (g)']:.2f} → {fila['Peso final (g)']:.2f} g",
             f"La recta global es {fila['Sentido de la recta']} ({fila['Pendiente peso (g/sem)']:+.3f} g/sem)."),
            ("Frutos acumulados observados", f"{fila['Frutos acumulados observados/planta']:.1f}/planta",
             "Suma de semanas observadas; no se extrapola a semanas faltantes."),
        ]),
    ]
    if huecos:
        bloques.append(ui.semaforo(
            "aviso",
            f"Este módulo tiene **{huecos} hueco(s) de calendario**. La suma acumulada "
            "es solo la suma de semanas observadas y no debe presentarse como total "
            "anual hasta completar o justificar esos huecos.",
        ))
    bloques.append(dcc.Tabs(children=[
        dcc.Tab(label="Frutos + peso", children=dcc.Graph(figure=fig_juntas, config={"displaylogo": False})),
        dcc.Tab(label="Peak de frutos", children=dcc.Graph(figure=fig_frutos, config={"displaylogo": False})),
        dcc.Tab(label="Curva de peso", children=dcc.Graph(figure=fig_peso, config={"displaylogo": False})),
    ]))
    bloques.append(ui.tabla_desde_df(trayectorias, formato={
        "Peak frutos/planta": "{:.2f}", "Frutos acumulados observados/planta": "{:.1f}",
        "Peso inicial (g)": "{:.2f}", "Peso final (g)": "{:.2f}",
        "Cambio neto peso (g)": "{:+.2f}", "Pendiente peso (g/sem)": "{:+.3f}",
    }))
    bloques.append(ui.como_leer(
        "**Posición del peak** divide la ventana observada de cada módulo en tres "
        "partes: inicio, medio y final. Es una descripción útil, pero todavía usa "
        "semana calendario. La comparación agronómica correcta será con días desde "
        "poda o fase fenológica.\n\n"
        "**Pendiente del peso** resume el cambio neto como `des+` o `des-`. Si hay "
        "cambios de sentido, la serie tiene olas y una sola recta oculta parte del "
        "proceso; por eso se muestran también la curva y el número de giros.",
        "Cómo leer el peak y la pendiente",
    ))
    return html.Div(bloques, className="space-y-3")


def _descomposicion(sem) -> html.Div:
    tabla = nucleo.clima.descomponer_frutos_peso(sem)
    bloques = [
        ui.titulo_seccion("Relación de frutos y peso con clima y riego"),
    ]
    for objetivo, titulo in [("Frutos", "Frutos por planta"), ("Peso", "Peso del fruto")]:
        sub = tabla[tabla.Objetivo == objetivo].sort_values("r sin controlar", key=lambda s: s.abs(), ascending=False)
        fig = go.Figure()
        fig.add_trace(go.Bar(y=sub.Variable, x=sub["r sin controlar"], orientation="h", name="Sin controlar", marker_color=ROJO, opacity=0.85))
        fig.add_trace(go.Bar(y=sub.Variable, x=sub["r control no lineal"], orientation="h", name="Descontando el calendario", marker_color=AZUL))
        fig.add_vline(x=0, line_color="#888")
        fig.update_layout(height=280, barmode="group", margin={"l": 10, "r": 10, "t": 10, "b": 10},
                          xaxis_title=f"correlación con {titulo.lower()}", xaxis_range=[-1, 1],
                          legend={"orientation": "h", "y": 1.2}, showlegend=(objetivo == "Frutos"))
        bloques.append(ui.titulo_seccion(titulo, "h4"))
        bloques.append(dcc.Graph(figure=fig, config={"displaylogo": False}))

        sobreviven = sub.loc[sub.Sobrevive, "Variable"].tolist()
        bloques.append(
            ui.semaforo("ok", f"Sobreviven al control del calendario: **{', '.join(sobreviven)}**.")
            if sobreviven else
            ui.semaforo("info", f"Ninguna variable sobrevive al control del calendario para {titulo.lower()}.")
        )
        if not sub.empty:
            cruda = sub.loc[sub["r sin controlar"].abs().idxmax()]
            controlada = sub.loc[sub["r control no lineal"].abs().idxmax()]
            if bool(controlada["Sobrevive"]):
                lectura = (
                    f"**Lectura dinámica para {titulo.lower()}:** la asociación cruda "
                    f"más fuerte es {cruda['Variable']} (r = {cruda['r sin controlar']:+.3f}), "
                    "pero la señal que queda con mayor magnitud tras descontar el "
                    f"calendario es {controlada['Variable']} (r = "
                    f"{controlada['r control no lineal']:+.3f}; p = "
                    f"{controlada['p control no lineal']:.3f}). Esto sigue siendo una "
                    "asociación temporal controlada, no un efecto causal."
                )
            else:
                lectura = (
                    f"**Lectura dinámica para {titulo.lower()}:** {cruda['Variable']} "
                    f"presenta la mayor asociación cruda (r = {cruda['r sin controlar']:+.3f}), "
                    "pero ninguna señal queda estadísticamente respaldada al descontar "
                    f"el calendario; la mayor restante es {controlada['Variable']} "
                    f"(r = {controlada['r control no lineal']:+.3f}). No se puede decir "
                    "que el clima haya causado el cambio observado."
                )
            bloques.append(ui.parrafo(lectura))

        poda_sub = sub.dropna(subset=["r control poda"]) if "r control poda" in sub else sub.iloc[0:0]
        if not poda_sub.empty:
            fig_poda = go.Figure(go.Bar(
                y=poda_sub.Variable, x=poda_sub["r control poda"], orientation="h",
                marker_color=[ROJO if s else AZUL for s in poda_sub["Sobrevive poda"]],
                hovertemplate="%{y}<br>r control poda = %{x:+.3f}<extra></extra>",
            ))
            fig_poda.add_vline(x=0, line_color="#888")
            fig_poda.update_layout(height=260, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                                   xaxis_title=f"asociación con {titulo.lower()} después de controlar días desde poda", xaxis_range=[-1, 1])
            bloques.append(dcc.Graph(figure=fig_poda, config={"displaylogo": False}))
            sobreviv_poda = poda_sub.loc[poda_sub["Sobrevive poda"], "Variable"].tolist()
            bloques.append(ui.parrafo(
                f"**Lectura con poda para {titulo.lower()}:** " + (
                    f"quedan señales en {', '.join(sobreviv_poda)}; siguen siendo "
                    "asociaciones condicionadas, no efectos causales."
                    if sobreviv_poda else
                    "ninguna variable mantiene p < 0,05 después de usar días desde poda como control proxy."
                )
            ))

    bloques.append(ui.como_leer(
        "Mismo formato que la Prueba 2 de Evidencia: la barra roja es la correlación "
        "cruda y la azul es lo que queda tras descontar el tiempo. La figura adicional "
        "usa días desde poda como control proxy. Si una variable pesa distinto sobre "
        "Frutos que sobre Peso, es una pista sobre EN QUÉ ETAPA actúa — cuajado o "
        "llenado — que kg/ha por sí solo no puede distinguir.\n\n"
        "**Advertencia de siempre:** correlación, no causalidad. Y con Frutos y Peso "
        "el riesgo de leer causalidad al revés es mayor: el fundo puede estar "
        "*ajustando* el riego según cómo viene la fruta, no solo la fruta respondiendo "
        "al riego que se le dio."
    ))
    bloques.append(ui.tabla_desde_df(tabla, ocultar=["clave"], formato={
        "r sin controlar": "{:+.3f}", "p sin controlar": "{:.4f}",
        "r control no lineal": "{:+.3f}", "p control no lineal": "{:.4f}",
    }))
    return html.Div(bloques, className="space-y-3")


def _floracion_shell(panel) -> html.Div:
    if "flores_promedio" not in panel.tabla.columns or panel.tabla.flores_promedio.isna().all():
        return html.Div([
            ui.titulo_seccion("Floración: ¿anticipa el cuajado de fruta?", "h4"),
            ui.semaforo("info", "No se cargó «DAtos mes.xlsx» (hoja EvFlores) — sin esto no hay conteo real de flores para comparar contra Frutos."),
        ])
    return html.Div(
        className="space-y-3",
        children=[
            ui.titulo_seccion("Floración: ¿anticipa el cuajado de fruta?", "h4"),
            ui.parrafo(
                "A diferencia de todo lo demás en esta sección, esto no compara clima "
                "contra resultado: compara **dos mediciones biológicas reales** — "
                "flores contadas por turno y frutos por planta — para ver si la "
                "floración de hace algunas semanas anticipa el cuajado de fruta. El "
                "control es más exigente que el resto del tablero: además de "
                "descontar el calendario, se descuenta el **promedio de cada módulo** "
                "(efecto fijo)."
            ),
            dcc.RadioItems(
                id="fp-floracion-objetivo",
                options=[{"label": "Frutos (cuajado)", "value": "Frutos"}, {"label": "kg/ha (cosecha)", "value": "KgHa"}],
                value="Frutos", inline=True, className="flex gap-4 text-sm",
            ),
            html.Div(id="fp-floracion-body"),
        ],
    )


@callback(Output("fp-floracion-body", "children"), Input(PANEL_STORE, "data"), Input("fp-floracion-objetivo", "value"))
def _render_floracion(panel, objetivo_flor):
    if panel is None or objetivo_flor is None:
        return None
    rezago = nucleo.clima.rezago_floracion(panel.tabla, objetivo=objetivo_flor)
    if rezago.empty:
        return ui.semaforo("info", f"No hay suficiente solapamiento entre floración y {objetivo_flor} para esta prueba.")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rezago.Rezago, y=rezago["r bruto"], mode="lines+markers", name="Sin controlar", line={"color": GRIS}))
    fig.add_trace(go.Scatter(x=rezago.Rezago, y=rezago["r control módulo"], mode="lines+markers", name="Controlando módulo", line={"color": ROJO, "dash": "dot"}))
    fig.add_trace(go.Scatter(x=rezago.Rezago, y=rezago["r control módulo y calendario"], mode="lines+markers", name="Controlando módulo y calendario", line={"color": AZUL, "width": 2.8}))
    fig.add_hline(y=0, line_color="#888")
    nombre_obj = "Frutos" if objetivo_flor == "Frutos" else "kg/ha"
    fig.update_layout(height=380, xaxis_title=f"semanas de floración antes de {nombre_obj}", yaxis_title=f"correlación con {nombre_obj}",
                      yaxis_range=[-1, 1], margin={"l": 10, "r": 10, "t": 10, "b": 10}, legend={"orientation": "h", "y": 1.14})

    mejor = rezago.loc[rezago["r control módulo y calendario"].abs().idxmax()]
    con_mismo = (rezago.Rezago == 0).any()
    r_mismo = float(rezago.loc[rezago.Rezago == 0, "r control módulo y calendario"].iloc[0]) if con_mismo else None
    r_mejor = float(mejor["r control módulo y calendario"])
    if con_mismo:
        nota_mismo = f" (negativa: mientras el módulo florece todavía no tiene {nombre_obj.lower()})" if r_mismo < 0 else ""
        mensaje = (
            f"Sí. Con el control completo (módulo y calendario), la correlación con la "
            f"misma semana es {r_mismo:+.3f}{nota_mismo}, y sube a {r_mejor:+.3f} "
            f"(p = {mejor['p control módulo y calendario']:.1e}, n = {int(mejor.n)} "
            f"celdas de {int(mejor['módulos'])} módulos) con {int(mejor.Rezago)} semanas de anticipación."
        )
        mejora = abs(r_mejor) > abs(r_mismo)
    else:
        mensaje = f"Mejor rezago: {int(mejor.Rezago)} semanas, r = {r_mejor:+.3f} (p = {mejor['p control módulo y calendario']:.1e})."
        mejora = True

    return html.Div(
        className="space-y-3",
        children=[
            dcc.Graph(figure=fig, config={"displaylogo": False}),
            ui.veredicto_de_prueba(
                f"¿La floración de antes explica mejor {nombre_obj} que la de la misma semana?",
                mensaje, "ok" if mejora else "aviso",
                "**Por qué el control de módulo, además del de calendario.** Todo el "
                "resto del tablero compara clima (igual para todos los módulos de una "
                "semana) contra un resultado que varía por módulo. Acá las dos series "
                "varían por módulo, así que un módulo que simplemente florece y "
                "fructifica más que el resto inflaría la correlación si no se descuenta "
                "también su propio promedio.\n\n"
                "**Este resultado sobrevive controles que casi ninguna variable "
                "climática del tablero sobrevive.** Sigue siendo observacional: es una "
                "correlación controlada, no un modelo entrenado.",
            ),
            ui.tabla_desde_df(rezago, formato={
                "r bruto": "{:+.3f}", "p bruto": "{:.4f}", "r control módulo": "{:+.3f}",
                "p control módulo": "{:.4f}", "r control módulo y calendario": "{:+.3f}",
                "p control módulo y calendario": "{:.4f}",
            }),
            html.P(
                "El número de celdas y de módulos baja con el rezago porque cada "
                "semana de anticipación exige una semana más de floración observada "
                "antes: por eso ésta no se agregó como variable del modelo conjunto.",
                className="text-xs text-slate-500",
            ),
            ui.semaforo(
                "aviso",
                "**Probado y descartado: usar solo la floración (con su mejor rezago) "
                f"para predecir {nombre_obj} con XGBoost.** La correlación de arriba es "
                "real, pero un modelo entrenado únicamente con floración da R² honesto "
                "(deja-un-bloque-fuera) de **−0,04** — peor que predecir siempre el "
                "promedio. El modelo actual (las 7 variables de clima y riego) da +0,32 "
                "en el mismo test.",
            ),
        ],
    )


def _desfases_shell(sem, tabla) -> html.Div:
    resumen = nucleo.clima.mejor_rezago_por_variable(sem, tabla)
    if resumen.empty:
        return html.Div([
            ui.titulo_seccion("Qué desfase explica mejor kg/ha, Frutos, Peso y Floración", "h4"),
            ui.semaforo("info", "No hay suficientes semanas con Frutos y Peso para esta búsqueda."),
        ])
    tope = int(resumen["Mejor rezago (semanas)"].max())
    en_el_tope = resumen[resumen["Mejor rezago (semanas)"] == tope]
    bloques = [
        ui.titulo_seccion("Qué desfase explica mejor kg/ha, Frutos, Peso y Floración", "h4"),
        ui.parrafo(
            "Repite la misma búsqueda de la Prueba 3 de Evidencia —mismo rango de 0 a 8 "
            "semanas, mismo control no lineal del calendario— pero también contra "
            "**Frutos**, **Peso** y **Floración**, para decir si el riego, la "
            "temperatura o la ETo pesan en una ventana distinta sobre el cuajado que "
            "sobre el llenado."
        ),
    ]
    if len(en_el_tope) >= len(resumen) / 2:
        bloques.append(ui.semaforo(
            "aviso",
            f"**{len(en_el_tope)} de {len(resumen)} combinaciones eligen el rezago "
            f"máximo probado ({tope} semanas).** Eso es una señal de alerta, no una "
            "confirmación: con solo 50 semanas de campaña y muchas combinaciones "
            "probadas, parte de esas correlaciones altas puede ser el mejor resultado "
            "de muchos intentos, no un óptimo real dentro de la ventana probada.",
        ))
    bloques.append(ui.tabla_desde_df(resumen, ocultar=["clave"], formato={
        "r sin tendencia en el mejor rezago": "{:+.3f}", "r sin tendencia en rezago 0": "{:+.3f}",
    }))
    if "Floración" in resumen.Objetivo.values:
        bloques.append(ui.semaforo(
            "info",
            "**La fila de Floración usa un control distinto de las otras tres.** "
            "kg/ha, Frutos y Peso se miden con la serie semanal agregada del fundo; la "
            "floración varía por módulo, así que acá se descuenta ADEMÁS el promedio "
            "de cada módulo (efecto fijo).",
        ))
    bloques.append(ui.como_leer(
        "**«Mejor rezago»** es el número de semanas de promedio móvil que maximiza la "
        "correlación **ya descontado el calendario** — no la cruda. Un mejor rezago de "
        "0 semanas quiere decir que ninguna ventana desplazada superó a la señal "
        "contemporánea."
    ))

    objetivos = resumen.Objetivo.unique().tolist()
    bloques.append(html.Div(
        className="grid grid-cols-2 gap-3",
        children=[
            dcc.Dropdown(id="fp-desfase-objetivo", options=objetivos, value=objetivos[0], clearable=False),
            dcc.Dropdown(id="fp-desfase-variable", clearable=False),
        ],
    ))
    bloques.append(html.Div(id="fp-desfase-body"))
    return html.Div(bloques, className="space-y-3")


@callback(
    Output("fp-desfase-variable", "options"), Output("fp-desfase-variable", "value"),
    Input(PANEL_STORE, "data"), Input("fp-desfase-objetivo", "value"),
)
def _opciones_desfase_variable(panel, objetivo_sel):
    if panel is None or objetivo_sel is None:
        return [], None
    sem = nucleo.clima.agregar_por_semana(panel.tabla)
    resumen = nucleo.clima.mejor_rezago_por_variable(sem, panel.tabla)
    claves = resumen.loc[resumen.Objetivo == objetivo_sel, "clave"].tolist()
    opciones = [{"label": etiqueta(c), "value": c} for c in claves]
    return opciones, (claves[0] if claves else None)


@callback(
    Output("fp-desfase-body", "children"),
    Input(PANEL_STORE, "data"), Input("fp-desfase-objetivo", "value"), Input("fp-desfase-variable", "value"),
)
def _render_desfase(panel, objetivo_sel, variable_sel):
    if panel is None or objetivo_sel is None or variable_sel is None:
        return None
    sem = nucleo.clima.agregar_por_semana(panel.tabla)
    todos = nucleo.clima.rezagos_todos(sem, panel.tabla)
    d = todos[(todos.Objetivo == objetivo_sel) & (todos.clave == variable_sel)]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d.Rezago, y=d["r bruto"], mode="lines+markers", name="Sin descontar la estación", line={"color": ROJO}))
    fig.add_trace(go.Scatter(x=d.Rezago, y=d["r sin tendencia"], mode="lines+markers", name="Descontando la estación", line={"color": AZUL, "dash": "dot"}))
    fig.add_hline(y=0, line_color="#888")
    fig.update_layout(height=340, xaxis_title="semanas de rezago", yaxis_title=f"correlación con {objetivo_sel}",
                      yaxis_range=[-1, 1], margin={"l": 10, "r": 10, "t": 10, "b": 10}, legend={"orientation": "h", "y": 1.14})
    return dcc.Graph(figure=fig, config={"displaylogo": False})


def _picos_shell(panel) -> html.Div:
    tray = nucleo.clima.trayectorias_frutos_peso(panel.tabla)
    resumen = nucleo.clima.resumen_picos_frutos_peso(panel.tabla)
    if tray.empty or resumen.empty:
        return html.Div([
            ui.titulo_seccion("Por qué el peak de frutos aparece al inicio, medio o final", "h4"),
            ui.semaforo("info", "No hay suficientes pares Frutos–Peso por módulo para comparar la posición del peak."),
        ])

    conteo = tray["Posición del peak"].value_counts().reindex(["Inicio", "Medio", "Final"], fill_value=0)
    fig_conteo = px.bar(
        x=conteo.index, y=conteo.values, text=conteo.values,
        color=conteo.index, color_discrete_sequence=[AZUL, "#7f8c8d", ROJO],
        labels={"x": "posición del peak dentro de la ventana observada", "y": "módulos"},
    )
    fig_conteo.update_layout(height=330, showlegend=False, margin={"l": 10, "r": 10, "t": 10, "b": 10})

    bloques = [
        ui.titulo_seccion("Por qué el peak de frutos aparece al inicio, medio o final", "h4"),
        ui.parrafo(
            "La posición del peak se calcula dentro de la ventana observada de cada "
            "módulo. Después se compara con días desde poda, con la dispersión de poda "
            "y con el clima de las cuatro semanas observadas que preceden al peak."
        ),
        html.Div(className="grid grid-cols-2 gap-4", children=[
            dcc.Graph(figure=fig_conteo, config={"displaylogo": False}),
            html.Div([
                dcc.Dropdown(
                    id="fp-picos-clima",
                    options=[{"label": etiqueta(c), "value": c} for c in VARIABLES_PRE_PEAK],
                    value="TempMin", clearable=False,
                ),
                html.Div(id="fp-picos-body"),
            ]),
        ]),
        ui.tabla_desde_df(resumen, formato={
            "DAP peak medio": "{:.0f}", "Poda dispersion dias media": "{:.0f}", "Semana peak media": "{:.1f}",
            "Frutos peak medio": "{:.1f}", "Peso peak medio (g)": "{:.2f}", "TempMin pre-peak": "{:.2f}",
            "DPV pre-peak": "{:.2f}", "Rad pre-peak": "{:.1f}", "ETo pre-peak": "{:.1f}",
            "Riego pre-peak": "{:.2f}", "GDD pre-peak": "{:.1f}",
        }),
    ]

    columna_peak_resumen = next((c for c in resumen.columns if str(c).lower().startswith("posici") and "peak" in str(c).lower()), None)
    columna_peak_tray = next((c for c in tray.columns if str(c).lower().startswith("posici") and "peak" in str(c).lower()), None)
    if columna_peak_resumen and "Inicio" not in set(resumen[columna_peak_resumen].astype(str)):
        bloques.append(ui.semaforo(
            "info",
            "En la campaña actual no aparece un peak clasificado como Inicio: se "
            f"observan {int((tray[columna_peak_tray] == 'Medio').sum())} módulos en "
            f"Medio y {int((tray[columna_peak_tray] == 'Final').sum())} en Final. Esto "
            "describe la ventana observada disponible; no permite concluir que el "
            "cultivo nunca tenga peaks tempranos.",
        ))

    disponibles = resumen.dropna(subset=["DAP peak medio"])
    if len(disponibles) >= 2:
        temprano, tardio = disponibles.iloc[0], disponibles.iloc[-1]
        diff_dap = float(tardio["DAP peak medio"] - temprano["DAP peak medio"])
        diff_temp = float(tardio["TempMin pre-peak"] - temprano["TempMin pre-peak"])
        diff_dpv = float(tardio["DPV pre-peak"] - temprano["DPV pre-peak"])
        bloques.append(ui.parrafo(
            f"**Lectura dinámica:** los peaks del grupo **{temprano['Posición del peak']}** "
            f"ocurren en promedio a {temprano['DAP peak medio']:.0f} días desde poda y "
            f"los del grupo **{tardio['Posición del peak']}** a {tardio['DAP peak medio']:.0f} "
            f"días; la diferencia es de {diff_dap:+.0f} días. En las cuatro semanas "
            f"pre-peak, la temperatura mínima cambia {diff_temp:+.2f} °C y el DPV "
            f"{diff_dpv:+.2f} kPa entre ambos grupos. Esto permite ver si el "
            "desplazamiento del peak coincide con una exposición climática distinta, "
            "pero no demuestra causalidad."
        ))
    return html.Div(bloques, className="space-y-3")


@callback(Output("fp-picos-body", "children"), Input(PANEL_STORE, "data"), Input("fp-picos-clima", "value"))
def _render_picos(panel, variable):
    if panel is None or variable is None:
        return None
    tray = nucleo.clima.trayectorias_frutos_peso(panel.tabla)
    columna = _COLUMNA_PRE_PEAK[variable]
    x = "Días desde poda peak" if tray["Días desde poda peak"].notna().any() else "Semana peak frutos"
    fig = px.scatter(
        tray, x=x, y=columna, color="Posición del peak", hover_name="Módulo",
        category_orders={"Posición del peak": ["Inicio", "Medio", "Final"]},
        color_discrete_sequence=[AZUL, "#7f8c8d", ROJO],
    )
    fig.update_layout(height=330, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      xaxis_title="días desde poda del peak" if x.startswith("Días") else "semana del peak",
                      yaxis_title=f"{etiqueta(variable)}: promedio de 4 semanas pre-peak")
    return dcc.Graph(figure=fig, config={"displaylogo": False})


def _peso_shell(panel) -> html.Div:
    tray = nucleo.clima.trayectorias_frutos_peso(panel.tabla)
    if tray.empty:
        return None
    return html.Div(
        className="space-y-3",
        children=[
            ui.titulo_seccion("Peso del fruto: subida, bajada y olas", "h4"),
            dcc.Dropdown(
                id="fp-peso-clima",
                options=[{"label": etiqueta(c), "value": c} for c in VARIABLES_PRE_PEAK],
                value="TempMin", clearable=False, className="max-w-sm",
            ),
            html.Div(id="fp-peso-body"),
        ],
    )


@callback(Output("fp-peso-body", "children"), Input(PANEL_STORE, "data"), Input("fp-peso-clima", "value"))
def _render_peso(panel, variable):
    if panel is None or variable is None:
        return None
    tray = nucleo.clima.trayectorias_frutos_peso(panel.tabla)
    columna = _COLUMNA_PRE_PEAK[variable]
    fig = px.scatter(
        tray, x=columna, y="Cambio neto peso (g)", color="Posición del peak", hover_name="Módulo",
        category_orders={"Posición del peak": ["Inicio", "Medio", "Final"]},
        color_discrete_sequence=[AZUL, "#7f8c8d", ROJO],
    )
    fig.add_hline(y=0, line_color="#888")
    fig.update_layout(height=380, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      xaxis_title=f"{etiqueta(variable)}: promedio de 4 semanas pre-peak", yaxis_title="cambio neto del peso observado (g)")

    positivo = int((tray["Cambio neto peso (g)"] > 0).sum())
    negativo = int((tray["Cambio neto peso (g)"] < 0).sum())
    olas = int((tray["Cambios de sentido"] > 0).sum())
    return html.Div([
        dcc.Graph(figure=fig, config={"displaylogo": False}),
        ui.parrafo(
            f"**Lectura dinámica:** en los módulos con suficientes datos, el peso "
            f"termina por encima del inicio en {positivo}, por debajo en {negativo}, y "
            f"presenta al menos un cambio de sentido en {olas}. La nube permite "
            f"comprobar si esas trayectorias cambian junto con {etiqueta(variable)} "
            "antes del peak; la asociación sigue siendo observacional."
        ),
    ], className="space-y-3")

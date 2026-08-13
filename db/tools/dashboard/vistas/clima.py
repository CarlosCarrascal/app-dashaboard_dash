"""Núcleo de «Impacto agronómico»: ¿la temperatura explica el rendimiento?

Cinco pruebas encadenadas, cada una presentada como pregunta → respuesta → evidencia.
El orden importa: la primera encuentra una asociación fortísima y las siguientes la van
desarmando. Quien lea solo la primera se lleva una conclusión equivocada, así que la
interfaz numera las pruebas y adelanta el veredicto arriba de todo.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import servicios as sv
from config import AZUL, CLIMA, GRIS, ICONO, ROJO, TBASE_GDD, etiqueta
from nucleo import Panel
from vistas import graficos as g
from vistas.comun import (
    como_leer,
    escala_correlacion,
    explica_simple,
    glosario,
    semaforo,
    tarjetas,
    veredicto_de_prueba,
)


def _cabecera(sem: pd.DataFrame, panel: Panel) -> None:
    ver = sv.veredicto(sem)
    ef = sv.tamano_efectivo(panel.tabla)

    tarjetas([
        ("Variable más asociada", ver.variable_mas_asociada,
         "La que tiene la correlación más fuerte con el kg/ha, al grano semanal."),
        ("Su correlación", f"{ver.r_mas_alta:+.3f}".replace(".", ","),
         "Coeficiente de Pearson. −1 y +1 son los extremos; 0 es ausencia de relación."),
        ("Sobreviven al control", f"{len(ver.sobreviven_al_control)} de {len(CLIMA)}",
         "Cuántas mantienen una asociación significativa al descontar el calendario."),
        ("Semanas analizadas", str(ef.n_semanas),
         f"El clima tiene {ef.n_semanas} valores distintos, no {ef.n_celdas}: "
         "es el tamaño de muestra real."),
    ])

    if ver.hay_relacion_robusta:
        semaforo("ok", f"Tras descontar el calendario siguen en pie: "
                       f"{', '.join(ver.sobreviven_al_control)}.")
    else:
        semaforo(
            "error",
            "**Ninguna variable climática sobrevive al control del calendario.** La "
            f"asociación más fuerte que se observa —{ver.variable_mas_asociada}, "
            f"r = {ver.r_mas_alta:+.3f}— desaparece al descontar la estación. Y una serie "
            f"inventada sin ningún significado físico («{ver.placebo_mas_fuerte}») "
            f"correlaciona **más fuerte todavía**: r = {ver.r_placebo:+.3f}. "
            "Las cinco pruebas de abajo muestran cómo se llega a esa conclusión.",
        )


def _prueba_1(sem: pd.DataFrame) -> None:
    st.subheader("Prueba 1 · ¿Cuánto correlaciona cada variable?")
    corr = sv.correlaciones_semanales(sem)
    escala_correlacion()

    fig = go.Figure()
    d = corr.sort_values("r (Pearson)")
    fig.add_trace(go.Bar(
        y=d.Variable, x=d["r (Pearson)"], orientation="h",
        marker={"color": [ROJO if s else GRIS for s in d.Significativa]},
        error_x={
            "type": "data", "symmetric": False,
            "array": d["IC 95% superior"] - d["r (Pearson)"],
            "arrayminus": d["r (Pearson)"] - d["IC 95% inferior"],
            "color": "#888", "thickness": 1.4,
        },
        hovertemplate="%{y}<br>r = %{x:+.3f}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#888")
    fig.update_layout(height=340, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      xaxis_title="correlación con el kg/ha", xaxis_range=[-1, 1])
    st.plotly_chart(fig, width="stretch")
    explica_simple(
        "Cuanto más larga la barra, más acompaña esa variable al rendimiento. Las rojas "
        "son las que probablemente no son casualidad; las grises, sí podrían serlo."
    )

    como_leer(
        "Cada barra es una variable; su largo es la fuerza de la asociación con el "
        "rendimiento. Las **rojas** son estadísticamente significativas (podría descartarse "
        "que sean casualidad); las **grises** no.\n\n"
        "La línea fina sobre cada barra es el **intervalo de confianza**: el rango donde "
        "estaría el valor real si repitiéramos la campaña. Se calcula sobre "
        f"**{len(sem)} semanas**, que es el número de mediciones climáticas distintas — "
        "no sobre las 452 celdas del panel, porque el mismo valor de temperatura se repite "
        "en todos los módulos de una semana y contarlo varias veces fingiría una precisión "
        "que no existe."
    )
    st.dataframe(
        corr.drop(columns=["clave"]).style.format({
            "r (Pearson)": "{:+.3f}", "p": "{:.4f}", "IC 95% inferior": "{:+.3f}",
            "IC 95% superior": "{:+.3f}", "Spearman": "{:+.3f}", "p Spearman": "{:.4f}",
            "Varianza explicada": "{:.1%}",
        }).background_gradient(cmap="RdBu_r", subset=["r (Pearson)"], vmin=-1, vmax=1),
        width="stretch", hide_index=True,
    )


def _prueba_2(sem: pd.DataFrame) -> None:
    st.subheader("Prueba 2 · ¿Es la temperatura, o es el calendario?")
    st.markdown(
        "La campaña arranca en invierno y termina en verano. La cosecha sube y baja "
        "siguiendo la poda; la temperatura sube y baja siguiendo la estación. Dos curvas "
        "que se mueven juntas correlacionan aunque no tengan nada que ver entre sí. "
        "**La prueba consiste en descontar la forma de la campaña y ver qué queda.**"
    )
    parcial = sv.correlacion_parcial(sem)

    fig = go.Figure()
    d = parcial.sort_values("r sin controlar")
    fig.add_trace(go.Bar(y=d.Variable, x=d["r sin controlar"], orientation="h",
                         name="Sin controlar", marker_color=ROJO, opacity=0.85))
    fig.add_trace(go.Bar(y=d.Variable, x=d["r control no lineal"], orientation="h",
                         name="Descontando el calendario", marker_color=AZUL))
    fig.add_vline(x=0, line_color="#888")
    fig.update_layout(height=380, barmode="group",
                      margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      xaxis_title="correlación con el kg/ha", xaxis_range=[-1, 1],
                      legend={"orientation": "h", "y": 1.14})
    st.plotly_chart(fig, width="stretch")
    explica_simple(
        "La barra roja es lo que parece a primera vista; la azul es lo que queda cuando "
        "se descuenta que el año simplemente va de invierno a verano. Si la barra azul es "
        "chiquita, gran parte de lo rojo era solo el paso de las estaciones."
    )

    sobreviven = parcial.loc[parcial.Sobrevive, "Variable"].tolist()
    peor = parcial.iloc[0]
    veredicto_de_prueba(
        "¿Queda algo de la asociación cuando se descuenta la estación?",
        (f"No. {peor.Variable} pasa de r = {peor['r sin controlar']:+.3f} a "
         f"{peor['r control no lineal']:+.3f} (p = {peor['p no lineal']:.2f}), que es "
         "indistinguible de cero." if not sobreviven else
         f"Sí, en {', '.join(sobreviven)}."),
        "error" if not sobreviven else "ok",
        "Se resta de ambas series la tendencia común con el número de semana y se vuelve "
        "a correlacionar lo que sobra.\n\n"
        "**Por qué el control tiene que ser no lineal:** la cosecha no crece en línea "
        "recta, hace una joroba. Descontando solo una recta, buena parte de la forma "
        "queda sin absorber y la correlación parece sobrevivir. La tabla muestra las dos "
        "versiones justamente para que se vea la diferencia: con control lineal algunas "
        "parecen aguantar, con el control correcto ninguna lo hace.",
    )
    st.dataframe(
        parcial.drop(columns=["clave"]).style.format({
            "r sin controlar": "{:+.3f}", "r control lineal": "{:+.3f}",
            "p lineal": "{:.4f}", "r control no lineal": "{:+.3f}",
            "p no lineal": "{:.4f}", "Queda": "{:.0%}",
        }),
        width="stretch", hide_index=True,
    )


def _prueba_3(sem: pd.DataFrame) -> None:
    st.subheader("Prueba 3 · ¿El clima de hace unas semanas explica mejor?")
    st.markdown(
        "El fruto tarda semanas en formarse, así que sería razonable que el clima de hace "
        "un mes pesara más que el de hoy. Es una hipótesis con sentido agronómico y hay "
        "que probarla."
    )
    lags = sv.rezagos(sem)
    variable = st.selectbox(
        "Variable", list(CLIMA), format_func=etiqueta, key="lag_var",
        index=list(CLIMA).index("TempMin"),
    )
    d = lags[lags.clave == variable]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d.Rezago, y=d["r bruto"], mode="lines+markers",
                             name="Sin descontar la estación", line={"color": ROJO}))
    fig.add_trace(go.Scatter(x=d.Rezago, y=d["r sin tendencia"], mode="lines+markers",
                             name="Descontando la estación",
                             line={"color": AZUL, "dash": "dot"}))
    fig.add_hline(y=0, line_color="#888")
    fig.update_layout(height=380, xaxis_title="semanas de rezago",
                      yaxis_title="correlación con el kg/ha", yaxis_range=[-1, 1],
                      margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      legend={"orientation": "h", "y": 1.14})
    st.plotly_chart(fig, width="stretch")

    bruto = d.loc[d["r bruto"].abs().idxmax()]
    limpio = d.loc[d["r sin tendencia"].abs().idxmax()]
    veredicto_de_prueba(
        "¿Hay un rezago con significado biológico?",
        f"No se puede afirmar. Sin descontar la estación el mejor rezago es de "
        f"{int(bruto.Rezago)} semanas (r = {bruto['r bruto']:+.3f}), pero al descontarla "
        f"el máximo cae a {limpio['r sin tendencia']:+.3f}.",
        "aviso",
        "**Por qué la curva roja engaña.** Cuando dos series suben y bajan con la "
        "estación, desplazar una contra la otra puede alinear mejor las jorobas y subir la "
        "correlación sin que exista ningún mecanismo físico. La curva azul repite el "
        "cálculo sobre las series ya descontadas: si ahí apareciera un pico claro en, "
        "digamos, 6 semanas, sería evidencia de un efecto real con rezago. No aparece.",
    )


def _prueba_4(sem: pd.DataFrame) -> None:
    st.subheader("Prueba 4 · La prueba del placebo")
    st.markdown(
        "La forma más directa de mostrar el problema: inventar series que **no significan "
        "nada** y ver cuánto correlacionan. Si una onda matemática le gana a la "
        "temperatura, lo que la correlación mide es la forma de la curva, no el clima."
    )
    pl = sv.placebo(sem)
    d = pl.sort_values("r con kg/ha")
    fig = go.Figure(go.Bar(
        y=d.Serie, x=d["r con kg/ha"], orientation="h",
        marker={"color": [AZUL if real else ROJO for real in d.Real]},
        hovertemplate="%{y}<br>r = %{x:+.3f}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#888")
    fig.update_layout(height=420, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      xaxis_title="correlación con el kg/ha", xaxis_range=[-1, 1])
    st.plotly_chart(fig, width="stretch")
    st.caption("Azul: variables reales medidas en campo. Rojo: series inventadas.")
    explica_simple(
        "Las barras rojas son inventadas — no significan nada, son solo ondas "
        "matemáticas. Si una barra roja es tan larga como las azules (las reales), es la "
        "prueba de que gran parte de la relación es solo el calendario, no el clima."
    )

    falsas = pl[~pl.Real]
    top = falsas.loc[falsas["r con kg/ha"].abs().idxmax()]
    reales = pl[pl.Real]
    mejor_real = reales.loc[reales["r con kg/ha"].abs().idxmax()]
    gana = abs(top["r con kg/ha"]) > abs(mejor_real["r con kg/ha"])
    veredicto_de_prueba(
        "¿Una serie sin significado correlaciona igual de fuerte?",
        (f"Sí, y más: «{top.Serie}» da r = {top['r con kg/ha']:+.3f}, por encima de "
         f"{mejor_real.Serie} ({mejor_real['r con kg/ha']:+.3f}). Una onda que solo "
         "conoce el número de semana describe la cosecha mejor que cualquier medición "
         "de campo." if gana else
         f"No: la mejor serie inventada («{top.Serie}») llega a "
         f"{top['r con kg/ha']:+.3f}, por debajo de {mejor_real.Serie}."),
        "error" if gana else "ok",
        "Las series inventadas son: una onda senoidal de período anual, su coseno, una "
        "rampa que solo cuenta semanas, y ruido aleatorio puro. Ninguna tiene contacto con "
        "el cultivo.\n\n"
        "**Qué prueba esto.** No que la temperatura sea irrelevante para el arándano —lo "
        "es, y mucho— sino que **con estos datos no se puede distinguir su efecto del "
        "simple paso del calendario**. Para separarlos harían falta varias campañas con "
        "fechas de poda distintas, o módulos con calendarios desplazados.",
    )


def _prueba_5(panel: Panel) -> None:
    st.subheader("Prueba 5 · ¿Pasa lo mismo en todos los módulos?")
    st.markdown(
        "Si la relación fuera fisiológica, debería repetirse en cada módulo por separado. "
        "Y en gran medida se repite… salvo en unos pocos, que son los que delatan el "
        "mecanismo."
    )
    porm = sv.por_modulo(panel.tabla)
    dep = sv.signo_depende_de_la_ventana(porm)

    columnas = [etiqueta(c) for c in CLIMA if etiqueta(c) in porm.columns]
    st.plotly_chart(g.mapa_por_modulo(porm, columnas), width="stretch")
    como_leer(
        "Cada fila es un módulo y cada columna una variable. **Azul** = correlación "
        "negativa (cuando la variable sube, el rendimiento baja); **rojo** = positiva. "
        "Si una columna fuera del mismo color de arriba abajo, la relación sería "
        "consistente en todo el fundo."
    )

    st.plotly_chart(g.ventana_de_cosecha(porm), width="stretch")
    fila = dep.iloc[0] if len(dep) else None
    if fila is not None:
        r = fila["r (inicio de cosecha ↔ correlación del módulo)"]
        veredicto_de_prueba(
            "¿Qué decide el signo de la correlación en cada módulo?",
            f"Cuándo empieza a cosechar. La correlación entre «semana de inicio» y "
            f"«correlación del módulo» es r = {r:+.3f} (p = {fila.p:.4f}) para "
            f"{fila.Variable}: los módulos que arrancan tarde tienden a invertir el signo.",
            "error" if fila.p < 0.05 else "aviso",
            "**El razonamiento.** Los módulos que arrancan tarde cosechan mientras la "
            "temperatura sube, así que en ellos temperatura y cosecha suben juntas: "
            "correlación positiva. Los que arrancan temprano cosechan mientras la "
            "temperatura baja: correlación negativa.\n\n"
            "Mismo fundo, mismo termómetro, misma semana — y el signo se invierte según "
            "el calendario del módulo. Si la temperatura fuera la causa, un módulo que "
            "cosecha con más calor debería rendir **menos**, no más.",
        )
    st.dataframe(
        dep.drop(columns=["clave"]).style.format(
            {"r (inicio de cosecha ↔ correlación del módulo)": "{:+.3f}", "p": "{:.4f}"}
        ),
        width="stretch", hide_index=True,
    )


def _forma(sem: pd.DataFrame) -> None:
    st.subheader("La forma de la relación")
    st.markdown(
        "Aunque la asociación no resista el control del calendario, **describirla sigue "
        "siendo útil**: dice qué rendimiento acompaña a cada rango de temperatura en esta "
        "campaña. Eso es descripción, no predicción."
    )
    variable = st.selectbox("Variable", list(CLIMA), format_func=etiqueta,
                            key="forma_var", index=list(CLIMA).index("TempMin"))
    tab = sv.forma_de_la_relacion(sem, variable)
    izq, der = st.columns([3, 2])
    with izq:
        fig = px.bar(tab, x="Tramo", y="kg_ha", color="valor",
                     color_continuous_scale="RdBu_r",
                     labels={"kg_ha": "kg/ha promedio", "valor": etiqueta(variable)},
                     text=tab.kg_ha.round(0))
        fig.update_traces(textposition="outside")
        fig.update_layout(height=380, margin={"l": 10, "r": 10, "t": 10, "b": 10})
        st.plotly_chart(fig, width="stretch")
    with der:
        st.dataframe(
            tab[["Tramo", "valor", "kg_ha", "semanas"]].rename(columns={
                "valor": f"{etiqueta(variable)} medio", "kg_ha": "kg/ha", "semanas": "n",
            }).style.format({f"{etiqueta(variable)} medio": "{:.1f}", "kg/ha": "{:,.0f}"}),
            width="stretch", hide_index=True,
        )
        cuad = sv.ganancia_cuadratica(sem)
        f = cuad[cuad.clave == variable].iloc[0]
        if f.p < 0.05:
            st.info(
                f"La relación es **curva**, no recta: añadir un término cuadrático sube el "
                f"ajuste de {f['R² recta']:.2f} a {f['R² curva']:.2f} (p = {f.p:.4f}).",
                icon=ICONO["info"],
            )
        else:
            st.caption(
                f"Una curva no ajusta mejor que una recta (p = {f.p:.2f}): no hay "
                "evidencia de un óptimo dentro del rango observado."
            )

    st.plotly_chart(_serie_doble(sem, variable), width="stretch")
    como_leer(
        "Las dos curvas del tiempo, superpuestas. Si se espejan, es porque ambas siguen el "
        "calendario — la cosecha por la fecha de poda y el clima por la estación. **Que "
        "se espejen no dice cuál mueve a cuál**, y ése es justamente el problema que "
        "atacan las pruebas 2 a 5."
    )


def _serie_doble(sem: pd.DataFrame, variable: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sem.nsem, y=sem.kg_ha, mode="lines+markers",
                             name="kg/ha del fundo", line={"color": AZUL}))
    fig.add_trace(go.Scatter(x=sem.nsem, y=sem[variable], mode="lines", yaxis="y2",
                             name=etiqueta(variable),
                             line={"color": ROJO, "dash": "dot"}))
    fig.update_layout(
        height=380, xaxis_title="semana de 2025", yaxis_title="kg/ha del fundo",
        yaxis2={"title": etiqueta(variable), "overlaying": "y", "side": "right",
                "showgrid": False},
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        legend={"orientation": "h", "y": 1.14},
    )
    return fig


def _gdd(sem: pd.DataFrame) -> None:
    st.subheader("Grados-día de crecimiento (GDD)")
    st.markdown(
        "La temperatura de una semana no dice cuánto avanzó la planta: 18 °C en invierno "
        "y 18 °C en verano pesan distinto según el desarrollo acumulado antes. Los "
        "**grados-día** traducen temperatura en desarrollo, que es la forma estándar de "
        "medir **tiempo fisiológico** en vez de tiempo de calendario."
    )
    st.latex(
        r"\mathrm{GDD}_{\text{semana}} \;=\; 7 \times \max\!\left(0,\;"
        r"\frac{T_{\max} + T_{\min}}{2} - T_{\text{base}}\right)"
    )
    st.caption(
        f"Con **T base = {TBASE_GDD} °C**, el valor de referencia para arándano: por "
        "debajo de ese umbral la planta no acumula desarrollo."
    )

    media = (sem.TempMax + sem.TempMin) / 2
    r_media = float(np.corrcoef(sem.gdd_semana, media)[0, 1])
    r_cal = float(np.corrcoef(sem.gdd_acum, sem.nsem)[0, 1])
    corr = sv.correlaciones_semanales(sem)
    fila_sem = corr[corr.clave == "gdd_semana"].iloc[0]
    fila_acum = corr[corr.clave == "gdd_acum"].iloc[0]

    tarjetas([
        ("GDD por semana", f"{sem.gdd_semana.min():.0f} – {sem.gdd_semana.max():.0f}",
         "Rango observado, en °C·día."),
        ("GDD acumulados en el año", f"{sem.gdd_acum.max():,.0f}".replace(",", "."),
         "Total al cierre de la campaña."),
        ("r del GDD semanal", f"{fila_sem['r (Pearson)']:+.3f}", "Con el kg/ha."),
        ("r del GDD acumulado", f"{fila_acum['r (Pearson)']:+.3f}", "Con el kg/ha."),
    ])

    fig = go.Figure()
    fig.add_trace(go.Bar(x=sem.nsem, y=sem.gdd_semana, name="GDD de la semana",
                         marker_color=AZUL, opacity=0.75))
    fig.add_trace(go.Scatter(x=sem.nsem, y=sem.gdd_acum, name="GDD acumulados",
                             yaxis="y2", line={"color": ROJO, "width": 2.5}))
    fig.update_layout(
        height=380, xaxis_title="semana de 2025", yaxis_title="GDD de la semana (°C·día)",
        yaxis2={"title": "GDD acumulados", "overlaying": "y", "side": "right",
                "showgrid": False},
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        legend={"orientation": "h", "y": 1.14},
    )
    st.plotly_chart(fig, width="stretch")

    st.divider()
    veredicto_de_prueba(
        "¿Aporta el GDD algo que la temperatura no diga ya?",
        f"No, en este panel. La correlación entre el GDD semanal y la temperatura media "
        f"es **{r_media:.6f}** — son la misma variable en otra escala.",
        "aviso",
        "**Por qué pasa esto.** El GDD solo aporta información propia cuando la "
        f"temperatura cruza el umbral: las semanas por debajo de {TBASE_GDD} °C se "
        "recortan a cero y dejan de contar. En este fundo la temperatura media va de "
        f"{media.min():.1f} a {media.max():.1f} °C, **siempre muy por encima del umbral**, "
        "así que el recorte nunca actúa y la fórmula queda como una multiplicación y una "
        "resta: una transformación lineal exacta.\n\n"
        "Eso no significa que el GDD sea inútil en general — es la variable correcta para "
        "comparar campañas o zonas con inviernos fríos. Significa que **en el desierto "
        "costero de La Libertad no discrimina nada** que la temperatura media no discrimine.",
    )

    veredicto_de_prueba(
        "¿Y el GDD acumulado?",
        f"Es el calendario. Su correlación con el número de semana es **{r_cal:.3f}**: "
        "acumular una cantidad casi constante cada semana produce una recta.",
        "error",
        f"El GDD semanal varía poco ({sem.gdd_semana.min():.0f} a "
        f"{sem.gdd_semana.max():.0f} °C·día, un factor de "
        f"{sem.gdd_semana.max() / sem.gdd_semana.min():.2f}), así que su suma acumulada "
        "crece de forma casi perfectamente lineal con el tiempo.\n\n"
        f"Por eso su correlación con el rendimiento ({fila_acum['r (Pearson)']:+.3f}) hay "
        "que leerla junto a la prueba 4: el **placebo «rampa: el número de semana»** mide "
        "exactamente lo mismo. Y como muestra la prueba 2, ninguna de las dos sobrevive al "
        "control del calendario.\n\n"
        "**Cuándo sí serviría.** El GDD acumulado es informativo cuando se cuenta **desde "
        "la poda de cada módulo**, porque entonces distingue módulos que arrancaron en "
        "fechas distintas. Acumulado desde el 1 de enero para todo el fundo, es un reloj "
        "de pared. La fecha de poda por módulo es el dato que falta.",
    )


def _frutos_peso(sem: pd.DataFrame, panel: Panel) -> None:
    st.subheader("Frutos y peso: los dos componentes del rendimiento")
    st.markdown(
        "kg/ha no se mide directo: sale de multiplicar **cuántos frutos** hay por "
        "planta y **cuánto pesa cada uno**, por la densidad de plantación. La hoja "
        "«Kg Reales» trae esos dos componentes por separado. Correlacionarlos contra el "
        "clima y el riego, cada uno por su lado, responde una pregunta que kg/ha solo no "
        "puede: ¿el efecto es sobre el **cuajado** de fruta o sobre su **tamaño**?"
    )
    if sem.Frutos.notna().sum() < 10:
        st.warning(
            "No hay suficientes semanas con Frutos y Peso cargados para esta sección "
            "(la hoja «Kg Reales» no está, o el formato cambió — ver Datos y calidad).",
            icon=ICONO["aviso"],
        )
        return

    st.info(
        "**Qué representa `Frutos`.** El archivo contiene frutos por planta, no el total "
        "absoluto del módulo. Para estimar frutos totales se necesita además el número "
        "efectivo de plantas productivas por módulo y campaña; no se inventa ese total.",
        icon=ICONO["info"],
    )

    trayectorias = sv.trayectorias_frutos_peso(panel.tabla)
    if not trayectorias.empty:
        st.markdown("#### Cuándo aparece el peak y cómo cambia el peso")
        modulo = st.selectbox(
            "Módulo para ver la curva",
            trayectorias["Módulo"].tolist(),
            key="curva_frutos_peso_modulo",
        )
        serie = panel.tabla[panel.tabla.celda == modulo].dropna(
            subset=["Frutos", "Peso"]
        ).sort_values("nsem")
        fila = trayectorias.loc[trayectorias["Módulo"] == modulo].iloc[0]
        usa_poda = (
            "dias_desde_poda" in serie.columns
            and serie.dias_desde_poda.notna().any()
        )
        eje_x = "dias_desde_poda" if usa_poda else "nsem"
        x = serie[eje_x].to_numpy(dtype=float)
        y_peso = serie.Peso.to_numpy(dtype=float)
        y_tendencia = np.polyval(np.polyfit(x, y_peso, 1), x)
        peak = int(fila["Semana peak frutos"])
        huecos = int(fila["Huecos de calendario"])
        tarjetas([
            ("Peak de frutos", f"S{peak}",
             f"Aparece en la posición {fila['Posición del peak'].lower()} de la ventana observada."),
            ("Frutos en el peak", f"{fila['Peak frutos/planta']:.1f}/planta",
             "Es un peak semanal; no es todavía el total de la campaña."),
            ("Peso: inicio → final", f"{fila['Peso inicial (g)']:.2f} → {fila['Peso final (g)']:.2f} g",
             f"La recta global es {fila['Sentido de la recta']} ({fila['Pendiente peso (g/sem)']:+.3f} g/sem)."),
            ("Frutos acumulados observados", f"{fila['Frutos acumulados observados/planta']:.1f}/planta",
             "Suma de semanas observadas; no se extrapola a semanas faltantes."),
        ])
        if huecos:
            st.warning(
                f"Este módulo tiene **{huecos} hueco(s) de calendario**. La suma acumulada "
                "es solo la suma de semanas observadas y no debe presentarse como total anual "
                "hasta completar o justificar esos huecos.",
                icon=ICONO["aviso"],
            )

        juntas, solo_frutos, solo_peso = st.tabs(["Frutos + peso", "Peak de frutos", "Curva de peso"])
        with juntas:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=serie[eje_x], y=serie.Frutos, mode="lines+markers", name="Frutos/planta",
                line={"color": AZUL, "width": 2.5},
            ))
            fig.add_trace(go.Scatter(
                x=serie[eje_x], y=serie.Peso, mode="lines+markers", name="Peso (g)",
                yaxis="y2", line={"color": ROJO, "width": 2.5},
            ))
            fig.update_layout(
                height=400,
                xaxis_title="días desde poda (proxy)" if usa_poda else "semana calendario",
                yaxis_title="frutos por planta",
                yaxis2={"title": "peso del fruto (g)", "overlaying": "y", "side": "right",
                        "showgrid": False},
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                legend={"orientation": "h", "y": 1.14},
            )
            st.plotly_chart(fig, width="stretch")
            explica_simple(
                "La línea azul es cuántos frutos hay; la roja, cuánto pesa cada uno. Se "
                "puede ver si el momento en que hay más frutos es el mismo momento en que "
                "pesan más, o si son momentos distintos."
            )
            st.caption(
                "Lectura conjunta: el gráfico permite ver si el peak de número de frutos "
                "coincide con un máximo de peso. No obliga a que ambos procesos respondan al "
                "mismo clima ni prueba que uno cause al otro."
            )
        with solo_frutos:
            fig = go.Figure(go.Scatter(
                x=serie[eje_x], y=serie.Frutos, mode="lines+markers", name="Frutos/planta",
                line={"color": AZUL, "width": 2.8},
            ))
            fig.add_vline(
                x=float(fila["Días desde poda peak"]) if usa_poda else peak,
                line_dash="dash", line_color=ROJO,
            )
            fig.add_annotation(
                x=float(fila["Días desde poda peak"]) if usa_poda else peak,
                y=float(fila["Peak frutos/planta"]),
                text=f"peak S{peak}", showarrow=True, arrowhead=2,
            )
            fig.update_layout(
                height=360,
                xaxis_title="días desde poda (proxy)" if usa_poda else "semana calendario",
                yaxis_title="frutos por planta",
                margin={"l": 10, "r": 10, "t": 20, "b": 10},
            )
            st.plotly_chart(fig, width="stretch")
            st.caption(
                "El peak se marca en la semana observada. Para explicar por qué se mueve "
                "entre módulos habrá que reemplazar semana calendario por días desde poda "
                "y comparar las ventanas climáticas de esa fase."
            )
        with solo_peso:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=serie[eje_x], y=serie.Peso, mode="lines+markers", name="Peso observado",
                line={"color": ROJO, "width": 2.8},
            ))
            fig.add_trace(go.Scatter(
                x=serie[eje_x], y=y_tendencia, mode="lines", name="Tendencia lineal",
                line={"color": GRIS, "dash": "dash"},
            ))
            fig.update_layout(
                height=360,
                xaxis_title="días desde poda (proxy)" if usa_poda else "semana calendario",
                yaxis_title="peso del fruto (g)",
                margin={"l": 10, "r": 10, "t": 20, "b": 10},
            )
            st.plotly_chart(fig, width="stretch")
            st.caption(
                f"La recta es {fila['Sentido de la recta']}; la curva observada tiene "
                f"{int(fila['Cambios de sentido'])} cambios de sentido. Si hay olas, la "
                "pendiente solo resume el conjunto y no describe cada etapa de llenado."
            )
        st.dataframe(
            trayectorias.style.format({
                "Peak frutos/planta": "{:.2f}",
                "Frutos acumulados observados/planta": "{:.1f}",
                "Peso inicial (g)": "{:.2f}",
                "Peso final (g)": "{:.2f}",
                "Cambio neto peso (g)": "{:+.2f}",
                "Pendiente peso (g/sem)": "{:+.3f}",
            }),
            width="stretch",
            hide_index=True,
        )
        como_leer(
            "**Posición del peak** divide la ventana observada de cada módulo en tres "
            "partes: inicio, medio y final. Es una descripción útil, pero todavía usa "
            "semana calendario. La comparación agronómica correcta será con días desde "
            "poda o fase fenológica.\n\n"
            "**Pendiente del peso** resume el cambio neto como `des+` o `des-`. Si hay "
            "cambios de sentido, la serie tiene olas y una sola recta oculta parte del "
            "proceso; por eso se muestran también la curva y el número de giros.",
            "Cómo leer el peak y la pendiente",
        )

    st.divider()
    st.markdown("#### Relación de frutos y peso con clima y riego")

    tabla = sv.descomponer_frutos_peso(sem)
    for objetivo, titulo in [("Frutos", "Frutos por planta"), ("Peso", "Peso del fruto")]:
        st.markdown(f"#### {titulo}")
        sub = tabla[tabla.Objetivo == objetivo].sort_values(
            "r sin controlar", key=lambda s: s.abs(), ascending=False
        )
        fig = go.Figure()
        fig.add_trace(go.Bar(y=sub.Variable, x=sub["r sin controlar"], orientation="h",
                             name="Sin controlar", marker_color=ROJO, opacity=0.85))
        fig.add_trace(go.Bar(y=sub.Variable, x=sub["r control no lineal"], orientation="h",
                             name="Descontando el calendario", marker_color=AZUL))
        fig.add_vline(x=0, line_color="#888")
        fig.update_layout(height=280, barmode="group",
                          margin={"l": 10, "r": 10, "t": 10, "b": 10},
                          xaxis_title=f"correlación con {titulo.lower()}",
                          xaxis_range=[-1, 1], legend={"orientation": "h", "y": 1.2},
                          showlegend=objetivo == "Frutos")
        st.plotly_chart(fig, width="stretch")
        sobreviven = sub.loc[sub.Sobrevive, "Variable"].tolist()
        if sobreviven:
            st.success(
                f"Sobreviven al control del calendario: **{', '.join(sobreviven)}**.",
                icon=ICONO["ok"],
            )
        else:
            st.info(f"Ninguna variable sobrevive al control del calendario para {titulo.lower()}.",
                    icon=ICONO["info"])
        if not sub.empty:
            cruda = sub.loc[sub["r sin controlar"].abs().idxmax()]
            controlada = sub.loc[sub["r control no lineal"].abs().idxmax()]
            nombre_crudo = str(cruda["Variable"])
            nombre_control = str(controlada["Variable"])
            if bool(controlada["Sobrevive"]):
                lectura = (
                    f"**Lectura dinámica para {titulo.lower()}:** la asociación cruda más "
                    f"fuerte es {nombre_crudo} (r = {cruda['r sin controlar']:+.3f}), pero "
                    f"la señal que queda con mayor magnitud tras descontar el calendario es "
                    f"{nombre_control} (r = {controlada['r control no lineal']:+.3f}; p = "
                    f"{controlada['p control no lineal']:.3f}). Esto sigue siendo una "
                    "asociación temporal controlada, no un efecto causal."
                )
            else:
                lectura = (
                    f"**Lectura dinámica para {titulo.lower()}:** {nombre_crudo} presenta la "
                    f"mayor asociación cruda (r = {cruda['r sin controlar']:+.3f}), pero "
                    f"ninguna señal queda estadísticamente respaldada al descontar el "
                    f"calendario; la mayor restante es {nombre_control} (r = "
                    f"{controlada['r control no lineal']:+.3f}). No se puede decir que el "
                    "clima haya causado el cambio observado."
                )
            st.markdown(lectura)

        poda_sub = sub.dropna(subset=["r control poda"]) if "r control poda" in sub else pd.DataFrame()
        if not poda_sub.empty:
            fig_poda = go.Figure(go.Bar(
                y=poda_sub.Variable,
                x=poda_sub["r control poda"],
                orientation="h",
                marker_color=[ROJO if s else AZUL for s in poda_sub["Sobrevive poda"]],
                hovertemplate="%{y}<br>r control poda = %{x:+.3f}<extra></extra>",
            ))
            fig_poda.add_vline(x=0, line_color="#888")
            fig_poda.update_layout(
                height=260,
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                xaxis_title=f"asociación con {titulo.lower()} después de controlar días desde poda",
                xaxis_range=[-1, 1],
            )
            st.plotly_chart(fig_poda, width="stretch")
            sobreviv_poda = poda_sub.loc[poda_sub["Sobrevive poda"], "Variable"].tolist()
            st.markdown(
                f"**Lectura con poda para {titulo.lower()}:** "
                + (
                    f"quedan señales en {', '.join(sobreviv_poda)}; siguen siendo "
                    "asociaciones condicionadas, no efectos causales."
                    if sobreviv_poda else
                    "ninguna variable mantiene p < 0,05 después de usar días desde poda "
                    "como control proxy."
                )
            )

    como_leer(
        "Mismo formato que la Prueba 2: la barra roja es la correlación cruda y la azul "
        "es lo que queda tras descontar el tiempo. La figura adicional usa días desde "
        "poda como control proxy. Si una variable pesa distinto sobre Frutos que sobre "
        "Peso, es una pista sobre EN QUÉ ETAPA actúa — cuajado o llenado — que kg/ha por "
        "sí solo no puede distinguir.\n\n"
        "**Advertencia de siempre:** correlación, no causalidad. Y con Frutos y Peso "
        "el riesgo de leer causalidad al revés es mayor: el fundo puede estar "
        "*ajustando* el riego según cómo viene la fruta, no solo la fruta respondiendo "
        "al riego que se le dio."
    )
    st.dataframe(
        tabla.drop(columns=["clave"]).style.format({
            "r sin controlar": "{:+.3f}", "p sin controlar": "{:.4f}",
            "r control no lineal": "{:+.3f}", "p control no lineal": "{:.4f}",
        }),
        width="stretch", hide_index=True,
    )

    st.divider()
    _floracion(panel)
    st.divider()
    _desfases_conjunto(sem, panel.tabla)


def _floracion(panel: Panel) -> None:
    st.markdown("#### Floración: ¿anticipa el cuajado de fruta?")
    if "flores_promedio" not in panel.tabla.columns or panel.tabla.flores_promedio.isna().all():
        st.info(
            "No se cargó «DAtos mes.xlsx» (hoja EvFlores) — sin esto no hay conteo real "
            "de flores para comparar contra Frutos.",
            icon=ICONO["info"],
        )
        return
    st.markdown(
        "A diferencia de todo lo demás en esta sección, esto no compara clima contra "
        "resultado: compara **dos mediciones biológicas reales** — flores contadas por "
        "turno y frutos por planta — para ver si la floración de hace algunas semanas "
        "anticipa el cuajado de fruta. El control es más exigente que el resto del "
        "tablero: además de descontar el calendario, se descuenta el **promedio de cada "
        "módulo** (efecto fijo), para no confundir «este módulo florece y fructifica más "
        "que el resto en general» con una relación temporal real."
    )
    objetivo_flor = st.radio(
        "Comparar floración contra", ["Frutos", "KgHa"],
        format_func=lambda o: "Frutos (cuajado)" if o == "Frutos" else "kg/ha (cosecha)",
        horizontal=True, key="floracion_objetivo",
    )
    rezago = sv.rezago_floracion(panel.tabla, objetivo=objetivo_flor)
    if rezago.empty:
        st.info(f"No hay suficiente solapamiento entre floración y {objetivo_flor} "
                "para esta prueba.", icon=ICONO["info"])
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rezago.Rezago, y=rezago["r bruto"], mode="lines+markers",
                             name="Sin controlar", line={"color": GRIS}))
    fig.add_trace(go.Scatter(x=rezago.Rezago, y=rezago["r control módulo"],
                             mode="lines+markers", name="Controlando módulo",
                             line={"color": ROJO, "dash": "dot"}))
    fig.add_trace(go.Scatter(x=rezago.Rezago, y=rezago["r control módulo y calendario"],
                             mode="lines+markers", name="Controlando módulo y calendario",
                             line={"color": AZUL, "width": 2.8}))
    fig.add_hline(y=0, line_color="#888")
    nombre_obj = "Frutos" if objetivo_flor == "Frutos" else "kg/ha"
    fig.update_layout(
        height=380, xaxis_title=f"semanas de floración antes de {nombre_obj}",
        yaxis_title=f"correlación con {nombre_obj}", yaxis_range=[-1, 1],
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        legend={"orientation": "h", "y": 1.14},
    )
    st.plotly_chart(fig, width="stretch")
    explica_simple(
        f"El punto más alto de la línea azul muestra: si contamos las flores de hace "
        f"varias semanas, ¿adivinamos mejor cuántos {nombre_obj.lower()} va a haber ahora? "
        "Mientras más a la derecha y más alto ese punto, mejor avisan las flores lo que "
        "viene."
    )

    mejor = rezago.loc[rezago["r control módulo y calendario"].abs().idxmax()]
    con_mismo = (rezago.Rezago == 0).any()
    r_mismo = float(rezago.loc[rezago.Rezago == 0, "r control módulo y calendario"].iloc[0]) \
        if con_mismo else None
    r_mejor = float(mejor["r control módulo y calendario"])
    if con_mismo:
        nota_mismo = (
            f" (negativa: mientras el módulo florece todavía no tiene {nombre_obj.lower()})"
            if r_mismo < 0 else ""
        )
        mensaje = (
            f"Sí. Con el control completo (módulo y calendario), la correlación con la "
            f"misma semana es {r_mismo:+.3f}{nota_mismo}, y sube a {r_mejor:+.3f} "
            f"(p = {mejor['p control módulo y calendario']:.1e}, n = {int(mejor.n)} celdas "
            f"de {int(mejor['módulos'])} módulos) con {int(mejor.Rezago)} semanas de "
            "anticipación."
        )
        mejora = abs(r_mejor) > abs(r_mismo)
    else:
        mensaje = (
            f"Mejor rezago: {int(mejor.Rezago)} semanas, r = {r_mejor:+.3f} "
            f"(p = {mejor['p control módulo y calendario']:.1e})."
        )
        mejora = True
    veredicto_de_prueba(
        f"¿La floración de antes explica mejor {nombre_obj} que la de la misma semana?",
        mensaje,
        "ok" if mejora else "aviso",
        "**Por qué el control de módulo, además del de calendario.** Todo el resto del "
        "tablero compara clima (igual para todos los módulos de una semana) contra un "
        "resultado que varía por módulo — ahí basta descontar el calendario. Acá las dos "
        "series varían por módulo, así que un módulo que simplemente florece y fructifica "
        "más que el resto (sin ninguna relación temporal) inflaría la correlación si no se "
        "descuenta también su propio promedio.\n\n"
        "**Este resultado sobrevive controles que casi ninguna variable climática del "
        "tablero sobrevive** (comparar con la Prueba 2). Sigue siendo observacional: no "
        "está pasado por una validación fuera de muestra como el modelo conjunto de "
        "Conclusiones — es una correlación controlada, no un modelo entrenado.",
    )
    st.dataframe(
        rezago.style.format({
            "r bruto": "{:+.3f}", "p bruto": "{:.4f}",
            "r control módulo": "{:+.3f}", "p control módulo": "{:.4f}",
            "r control módulo y calendario": "{:+.3f}",
            "p control módulo y calendario": "{:.4f}",
        }),
        width="stretch", hide_index=True,
    )
    st.caption(
        "El número de celdas y de módulos baja con el rezago porque cada semana de "
        "anticipación exige una semana más de floración observada antes: por eso ésta no "
        "se agregó como variable del modelo conjunto (con 5-6 semanas de rezago, cruzada "
        "con las ventanas de riego y clima ya exigidas, la muestra cae a ~20-30 celdas — "
        "insuficiente para 8 variables). Es una relación real, pero se evalúa aparte."
    )
    st.warning(
        "**Probado y descartado: usar solo la floración (con su mejor rezago) para "
        f"predecir {nombre_obj} con XGBoost.** La correlación de arriba es real, pero un "
        "modelo entrenado únicamente con floración da R² honesto (deja-un-bloque-fuera) "
        "de **−0,04** — peor que predecir siempre el promedio. Una correlación "
        "estadísticamente significativa no implica que haya suficiente señal para que un "
        "modelo aprenda una tasa de conversión estable con 18 módulos; el modelo actual "
        "(las 7 variables de clima y riego) da +0,32 en el mismo test.",
        icon=ICONO["aviso"],
    )


def _desfases_conjunto(sem: pd.DataFrame, tabla: pd.DataFrame) -> None:
    st.markdown("#### Qué desfase explica mejor kg/ha, Frutos, Peso y Floración")
    st.markdown(
        "La Prueba 3 (pestaña «3 · Desfases») busca, para cada variable climática, cuántas "
        "semanas de rezago explican mejor el **kg/ha**. Esta tabla repite exactamente la "
        "misma búsqueda —mismo rango de 0 a 8 semanas, mismo control no lineal del "
        "calendario— pero también contra **Frutos**, **Peso** y **Floración**, para poder "
        "decir si el riego, la temperatura o la ETo pesan en una ventana distinta sobre el "
        "cuajado que sobre el llenado. La fila de Floración usa un control más estricto "
        "(efecto fijo de módulo, no solo calendario) — ver el aviso más abajo."
    )
    resumen = sv.mejor_rezago_por_variable(sem, tabla)
    if resumen.empty:
        st.info("No hay suficientes semanas con Frutos y Peso para esta búsqueda.",
                icon=ICONO["info"])
        return

    tope = int(resumen["Mejor rezago (semanas)"].max())
    en_el_tope = resumen[resumen["Mejor rezago (semanas)"] == tope]
    if len(en_el_tope) >= len(resumen) / 2:
        st.warning(
            f"**{len(en_el_tope)} de {len(resumen)} combinaciones eligen el rezago máximo "
            f"probado ({tope} semanas).** Eso es una señal de alerta, no una confirmación: "
            "con solo 50 semanas de campaña y 9 rezagos × 7 variables × 3 objetivos probados, "
            "parte de esas correlaciones altas puede ser el mejor resultado de muchos intentos "
            "(comparaciones múltiples), y el verdadero óptimo podría estar más allá de la "
            "ventana de 8 semanas que se probó — no hay forma de distinguir ambos casos con "
            "una sola campaña. No se corrige por comparaciones múltiples porque el objetivo es "
            "descriptivo, no una prueba de hipótesis; pero por eso mismo esta tabla no debe "
            "leerse como si cada rezago fuera un hallazgo confirmado.",
            icon=ICONO["aviso"],
        )

    st.dataframe(
        resumen.drop(columns=["clave"]).style.format({
            "r sin tendencia en el mejor rezago": "{:+.3f}",
            "r sin tendencia en rezago 0": "{:+.3f}",
        }).background_gradient(
            cmap="RdBu_r", subset=["r sin tendencia en el mejor rezago"], vmin=-1, vmax=1
        ),
        width="stretch", hide_index=True,
    )
    if "Floración" in resumen.Objetivo.values:
        st.info(
            "**La fila de Floración usa un control distinto de las otras tres.** kg/ha, "
            "Frutos y Peso se miden con la serie semanal agregada del fundo (correcto para "
            "ellos: el clima es un dato de fundo, no de módulo). La floración, en cambio, "
            "varía por módulo — cada uno florece en una fase distinta dentro de la misma "
            "semana calendario (picos entre la semana 7 y la 52 según el módulo) — así que "
            "acá se descuenta ADEMÁS el promedio de cada módulo (efecto fijo), igual que la "
            "correlación floración→Frutos de más arriba. Sin ese control, la correlación de "
            "Floración salía inflada al doble o más (ver `docs/data/resumen_sesion.md` §14).",
            icon=ICONO["info"],
        )
    como_leer(
        "**«Mejor rezago»** es el número de semanas de promedio móvil que maximiza la "
        "correlación **ya descontado el calendario** — no la cruda, por la misma razón "
        "que la Prueba 3 no confía en la curva roja. Un mejor rezago de 0 semanas quiere "
        "decir que ninguna ventana desplazada superó a la señal contemporánea; no implica "
        "que la variable importe menos, solo que este panel no encuentra evidencia de un "
        "rezago biológico distinguible del ruido para ese objetivo.\n\n"
        "**Por qué GDD acumulado no está.** Es un reloj de calendario (Prueba de GDD, más "
        "abajo en «Diagnósticos técnicos»): desplazarlo en el tiempo no prueba nada "
        "distinto de desplazar el número de semana."
    )

    todos = sv.rezagos_todos(sem, tabla)
    objetivos = resumen.Objetivo.unique().tolist()
    izq, der = st.columns(2)
    objetivo_sel = izq.selectbox("Objetivo", objetivos, key="desfase_conjunto_obj")
    claves = resumen.loc[resumen.Objetivo == objetivo_sel, "clave"].tolist()
    variable_sel = der.selectbox(
        "Variable", claves, format_func=etiqueta, key="desfase_conjunto_var",
    )
    d = todos[(todos.Objetivo == objetivo_sel) & (todos.clave == variable_sel)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d.Rezago, y=d["r bruto"], mode="lines+markers",
                             name="Sin descontar la estación", line={"color": ROJO}))
    fig.add_trace(go.Scatter(x=d.Rezago, y=d["r sin tendencia"], mode="lines+markers",
                             name="Descontando la estación",
                             line={"color": AZUL, "dash": "dot"}))
    fig.add_hline(y=0, line_color="#888")
    fig.update_layout(
        height=340, xaxis_title="semanas de rezago",
        yaxis_title=f"correlación con {objetivo_sel}", yaxis_range=[-1, 1],
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        legend={"orientation": "h", "y": 1.14},
    )
    st.plotly_chart(fig, width="stretch")


@st.fragment
def render(panel: Panel) -> None:
    sem = sv.agregar_por_semana(panel.tabla)
    _cabecera(sem, panel)
    glosario(list(CLIMA))
    st.divider()

    pestanas = st.tabs([
        "1 · Relación bruta", "2 · Calendario", "3 · Desfases",
        "4 · Placebo", "5 · Por módulo", "6 · Frutos y peso",
    ])
    with pestanas[0]:
        _prueba_1(sem)
    with pestanas[1]:
        _prueba_2(sem)
    with pestanas[2]:
        _prueba_3(sem)
    with pestanas[3]:
        _prueba_4(sem)
    with pestanas[4]:
        _prueba_5(panel)
    with pestanas[5]:
        _frutos_peso(sem, panel)
    with st.expander("Diagnósticos técnicos: GDD y forma de la relación"):
        st.caption(
            "Se conservan para auditoría y exploración. No son la respuesta principal a "
            "qué variable tiene mayor impacto agronómico: GDD puede ser redundante con "
            "temperatura en esta campaña y la forma univariada no controla el calendario."
        )
        tecnicos = st.tabs(["GDD", "Forma no lineal"])
        with tecnicos[0]:
            _gdd(sem)
        with tecnicos[1]:
            _forma(sem)

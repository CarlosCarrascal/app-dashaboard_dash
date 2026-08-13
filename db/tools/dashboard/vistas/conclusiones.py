"""Conclusiones y hallazgos: una lectura ejecutiva de toda la evidencia."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import servicios as sv
from config import AZUL, CLIMA, ICONO, ROJO, etiqueta
from nucleo import Panel
from vistas.comun import como_leer, explica_simple, semaforo, tarjetas


def _formato_escala(v: float) -> str:
    """Decimales suficientes para que un número no se muestre como «0».

    kg/ha, frutos/planta y gramos viven en escalas muy distintas (cientos de miles contra
    unidades) — un formato fijo de cero decimales redondea el de Peso a 0 y lo hace ver
    como un error en vez de un número real pero chico.
    """
    if pd.isna(v):
        return "—"
    v = float(v)
    if abs(v) >= 100:
        return f"{v:,.0f}".replace(",", ".")
    if abs(v) >= 1:
        return f"{v:,.2f}".replace(",", ".")
    return f"{v:.4f}"


def _ventana_activa_texto() -> str:
    lags = st.session_state.get(
        "lags_config", {"riego": 7, "Rad": 3, "ETo": 2, "DPV": 6, "gdd": 7}
    )
    nombres = {"riego": "Riego", "Rad": "Radiación", "ETo": "ETo", "DPV": "DPV", "gdd": "GDD"}
    return ", ".join(f"{nombres[k]} {v} sem." for k, v in lags.items())


def _relacion_individual_y_conjunta(panel: Panel, sem: pd.DataFrame) -> None:
    """La respuesta directa a «qué variable, con qué desfase, explica qué».

    Dos lecturas complementarias, no intercambiables, y que DELIBERADAMENTE no se
    alimentan una a la otra — ver la advertencia después del mapa de calor:
      * Individual — cada variable sola, su propio mejor desfase, contra cada objetivo.
      * Conjunta — el modelo de 7 variables (la ventana activa en el sidebar ahora
        mismo, la MISMA para todos), explicado con SHAP, repetido para KgHa, Frutos,
        Peso y —si hay datos de floración— Floración.
    """
    st.subheader(
        "Cómo afectan las variables a kg/ha, Frutos, Peso y Floración — "
        "individual y conjunta"
    )
    st.markdown(
        "Dos preguntas distintas, no dos formas de preguntar lo mismo:\n\n"
        "1. **Por variable, sola** — de esta variable en particular, ignorando a las "
        "demás, ¿qué ventana de promedio móvil explica mejor cada objetivo?\n"
        "2. **Las siete juntas** — con la ventana que tengas configurada ahora, ¿cuánto "
        "pesa cada variable dentro de un solo modelo que ya conoce a las otras seis?"
    )

    st.markdown("#### 1 · Por variable, sola: ¿qué desfase le sienta mejor a cada objetivo?")
    resumen = sv.mejor_rezago_por_variable(sem, panel.tabla)
    if not resumen.empty:
        pivote = resumen.pivot(index="Variable", columns="Objetivo",
                               values="r sin tendencia en el mejor rezago")
        ventanas = resumen.pivot(index="Variable", columns="Objetivo",
                                 values="Mejor rezago (semanas)")
        orden_obj = [o for o in ["kg/ha", "Frutos", "Peso", "Floración"]
                    if o in pivote.columns]
        pivote, ventanas = pivote[orden_obj], ventanas[orden_obj]
        texto = pivote.copy()
        for c in pivote.columns:
            texto[c] = [
                f"{v:+.2f}<br>({int(w)} sem.)" if pd.notna(v) else ""
                for v, w in zip(pivote[c], ventanas[c], strict=True)
            ]
        st.caption(
            "**Cómo leer cada celda:** el número grande es la correlación (de −1 a +1, ya "
            "descontado el calendario); el número chico entre paréntesis es **cuántas "
            "semanas de promedio móvil** hicieron falta para llegar a esa correlación. "
            "Por ejemplo, `+0,42 (8 sem.)` en la columna kg/ha significa: *promediar esa "
            "variable de las últimas 8 semanas da la correlación más fuerte posible "
            "(+0,42) con el rendimiento, entre todas las ventanas de 0 a 8 semanas "
            "probadas.*"
        )
        fig = go.Figure(go.Heatmap(
            z=pivote.to_numpy(), x=orden_obj, y=pivote.index.tolist(),
            text=texto.to_numpy(), texttemplate="%{text}",
            colorscale="RdBu_r", zmid=0, zmin=-1, zmax=1,
            colorbar={"title": "r"},
        ))
        fig.update_layout(
            height=60 + 55 * len(pivote), margin={"l": 10, "r": 10, "t": 10, "b": 10},
            xaxis_title="objetivo", yaxis_title=None,
        )
        st.plotly_chart(fig, width="stretch")
        explica_simple(
            "Cada casillero muestra si esa variable (fila) va de la mano con ese "
            "resultado (columna): rojo = suben juntos, azul = uno sube cuando el otro "
            "baja. El número entre paréntesis es cuántas semanas antes hay que mirar esa "
            "variable para verlo mejor."
        )
        como_leer(
            "**Rojo** = sube junto con el objetivo; **azul** = baja. Leé cada FILA de "
            "izquierda a derecha: si el color se invierte entre columnas, esa variable "
            "pesa en sentido contrario sobre el cuajado (Frutos) que sobre el tamaño "
            "(Peso) — por ejemplo, algo que ayuda a que haya más frutos puede, al mismo "
            "tiempo, achicar el peso de cada uno.\n\n"
            "**La columna Floración no es comparable con las otras tres de la misma "
            "forma.** kg/ha, Frutos y Peso usan el clima agregado por semana del fundo; "
            "Floración varía por módulo (cada uno florece en su propia fase dentro de la "
            "misma semana), así que además se descuenta el promedio de cada módulo — sin "
            "eso, la correlación salía inflada al doble o más."
        )
        st.warning(
            f"**Esto es un diagnóstico, no una configuración.** La ventana que de verdad "
            "usa el modelo conjunto de la sección 2, ahora mismo, es la del sidebar: "
            f"`{_ventana_activa_texto()}` — **no** la que salió como «mejor» en este mapa "
            "de calor. Son dos análisis independientes a propósito: éste busca la ventana "
            "de cada variable **sola**; el modelo conjunto necesita **una sola ventana "
            "por variable, compartida por las tres**, y esa ventana se prueba y se elige a "
            "mano, no automáticamente a partir de este mapa. Si querés que el modelo "
            "conjunto refleje lo que encontraste acá, cambiá el número correspondiente en "
            "«Ventanas del modelo» (menú lateral) y volvé a esta pantalla.",
            icon=ICONO["aviso"],
        )

    st.divider()
    st.markdown("#### 2 · Las siete juntas: un modelo por objetivo, con la ventana activa")
    st.markdown(
        f"Ventana activa ahora: **`{_ventana_activa_texto()}`**. El mismo modelo XGBoost "
        "de siempre — las 7 variables juntas — entrenado una vez por objetivo con esa "
        "ventana. SHAP reparte cuánto pesa cada variable *dado que las demás ya están en "
        "el modelo*; por eso el orden puede no coincidir con el mapa de calor de arriba, "
        "que mira cada variable aislada."
    )
    honesto = sv.honesto_por_objetivo(panel.tabla)
    if not honesto.empty:
        cols = st.columns(len(honesto))
        for col, fila in zip(cols, honesto.itertuples(), strict=True):
            with col:
                st.metric(
                    fila.Objetivo, f"{fila._2:+.3f}",
                    help=f"R² honesto (deja-un-bloque-de-10-semanas fuera), n = "
                         f"{int(fila._4)} filas.",
                )
                st.caption(
                    "✓ Ventana propia" if fila._6 else "⚠ Usa la ventana de kg/ha"
                )
        st.caption(
            "**R² honesto** es el único número de esta pantalla que dice si el modelo "
            "generaliza a semanas que no vio — no es un promedio de aciertos, es "
            "1 − (error del modelo / error de solo predecir el promedio). Por encima de 0 "
            "significa que el modelo aporta algo; cerca o por debajo de 0 significa que no "
            "hay que confiar en el ranking SHAP de abajo para ese objetivo."
        )
        sin_calibrar = honesto.loc[~honesto["Hiperparámetros propios"], "Objetivo"].tolist()
        if sin_calibrar:
            st.warning(
                f"**{', '.join(sin_calibrar)} usa los hiperparámetros de XGBoost "
                "calibrados para kg/ha**, sin barrido propio. El R² de arriba es la única "
                "garantía de que el ranking no está sobreajustado.",
                icon=ICONO["aviso"],
            )
        with st.expander("Ver la tabla completa (MAE y varianza de referencia)"):
            st.dataframe(
                honesto.style.format({
                    "R² honesto": "{:+.3f}", "n filas": "{:.0f}",
                    "MAE honesto": _formato_escala,
                    "Varianza del objetivo (referencia)": _formato_escala,
                }),
                width="stretch", hide_index=True,
            )
            st.caption(
                "MAE y varianza están en la unidad de cada objetivo (kg/ha, frutos/planta "
                "o gramos): no son comparables entre filas, cada una compárese contra la "
                "propia. La varianza es la referencia — el error de predecir siempre el "
                "promedio — contra la que se mide implícitamente el MAE."
            )

    conjunto = sv.aporte_conjunto_por_objetivo(panel.tabla)
    if not conjunto.empty:
        st.markdown(
            "**Qué es «cuánto mueve» cada variable.** Es el promedio, en todas las celdas "
            "del panel, de cuánto sube o baja la predicción del modelo por causa de esa "
            "variable — el mismo número que ya viste como «Cuánto mueve» en Explicación "
            "del modelo, repetido acá para cada objetivo, uno al lado del otro."
        )
        unidad_por_objetivo = {
            "kg/ha": "kg/ha", "Frutos": "frutos/planta", "Peso": "g",
            "Floración": "flores/turno",
        }
        # Solo los objetivos que de verdad se pudieron entrenar (`aporte_conjunto_por_
        # objetivo` ya descarta los que no tienen datos) — fijar una lista de 3 a mano
        # dejaba a «Floración» convertida en NaN por `pd.Categorical` cuando sí había datos.
        orden_obj_conjunto = [
            o for o in ["kg/ha", "Frutos", "Peso", "Floración"]
            if o in conjunto.Objetivo.unique()
        ]
        orden_var = (
            conjunto.groupby("clave")["Aporte SHAP medio (|valor|)"].mean()
            .sort_values(ascending=False).index.tolist()
        )
        etiquetas_orden = [etiqueta(c) for c in orden_var]
        # kg/ha vive en cientos, Frutos en decenas y Peso en décimas de gramo: un solo eje
        # compartido aplasta a Frutos y Peso contra el cero (Peso llega, como mucho, al
        # 0,1 % del ancho del eje de kg/ha). Un panel por objetivo, cada uno con su propia
        # escala (`matches=None`), es lo que permite comparar la FORMA del ranking entre los
        # tres sin que la unidad de uno tape a los otros.
        conjunto = conjunto.assign(
            Objetivo=pd.Categorical(conjunto.Objetivo, orden_obj_conjunto, ordered=True),
            _texto=conjunto["Aporte SHAP medio (|valor|)"].map(_formato_escala),
        ).sort_values("Objetivo")
        fig = px.bar(
            conjunto, x="Aporte SHAP medio (|valor|)", y="Variable", color="Objetivo",
            orientation="h", facet_col="Objetivo", text="_texto",
            category_orders={"Variable": etiquetas_orden, "Objetivo": orden_obj_conjunto},
            color_discrete_sequence=[AZUL, ROJO, "#7f8c8d", "#8E6C88"],
        )
        fig.update_traces(textposition="outside", cliponaxis=False)
        # Un hovertemplate a mano: el automático de Plotly agrega una línea por cada
        # columna que uses en `text`/`color` — con `text="_texto"` eso incluía una línea
        # literal «_texto=231» en el cartel emergente, el nombre interno de la columna en
        # vez de algo legible.
        for tr in fig.data:
            unidad = unidad_por_objetivo.get(tr.name, "")
            tr.hovertemplate = (
                "<b>%{y}</b><br>Cuánto mueve: %{x:.3g} " + unidad + "<extra></extra>"
            )
        # `facet_col` deja, por omisión, los tres ejes X ATADOS entre sí (`matches="x"`):
        # sin esta línea, Frutos y Peso se dibujan en la escala de kg/ha (0-200) y sus
        # barras reales (máximo ~10 y ~0,24) quedan invisibles contra el cero — solo se ve
        # el número flotando, sin barra. Esto se rompió en una edición anterior al mover
        # el título del eje a un bloque separado y perder esta línea; quedó sin detectar
        # porque solo se había verificado el TÍTULO de cada eje, no si el RANGO seguía
        # compartido.
        fig.update_xaxes(matches=None)
        # `matches=None` en Y desvincula el RANGO (correcto, evita que se comparta el
        # orden) pero borra el `categoryarray` que px.bar solo le había puesto al primer
        # panel. Se reimpone en los tres para que las filas queden alineadas.
        # Las etiquetas de variable solo se muestran en el panel de la izquierda —
        # repetirlas en los tres saturaba el gráfico sin agregar información, porque la
        # fila ya queda alineada entre paneles.
        fig.update_yaxes(matches=None, categoryorder="array",
                         categoryarray=etiquetas_orden[::-1])
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
        for i, obj in enumerate(orden_obj_conjunto):
            eje_x = "xaxis" if i == 0 else f"xaxis{i + 1}"
            fig.layout[eje_x].title.text = unidad_por_objetivo[obj]
        fig.update_layout(
            height=110 + 40 * len(orden_var), margin={"l": 10, "r": 10, "t": 30, "b": 30},
            showlegend=False,
        )
        st.plotly_chart(fig, width="stretch")
        explica_simple(
            "En cada panel, la barra más larga es la variable que más mueve la aguja "
            "para ese resultado — cada panel tiene su propia regla de medir, así que no "
            "hay que comparar el largo de una barra de un panel con el de otro."
        )
        como_leer(
            "Cada panel tiene **su propia escala y su propia unidad** (el título debajo "
            "de cada eje) — el número exacto queda escrito junto a cada barra porque no "
            "tiene sentido comparar el largo de una barra de kg/ha contra una de Peso. "
            "Las filas están alineadas entre los tres paneles (mismo orden de arriba "
            "hacia abajo), aunque el nombre de la variable solo se vea escrito en el "
            "panel de la izquierda — para leer una fila de Peso, ubicá su posición "
            "vertical y mirá el nombre correspondiente en el panel de kg/ha.\n\n"
            "Una variable puede encabezar el ranking en Peso y no en kg/ha: eso pasa "
            "cuando su efecto se reparte entre Frutos y Peso de forma que se cancela "
            "parcialmente al multiplicarlos. El SHAP de kg/ha, Frutos y Peso no tiene por "
            "qué coincidir, y esa diferencia es información, no ruido.\n\n"
            "**Antes de leer esto como impacto agronómico:** mirá las tarjetas de R² "
            "honesto más arriba. Si un objetivo tiene «Usa la ventana de kg/ha» y un R² "
            "bajo, su ranking describe cómo usa el modelo sus variables, no una relación "
            "que vaya a generalizar."
        )


def _resumen_evidencia(panel: Panel, sem: pd.DataFrame) -> None:
    st.subheader("Qué dice hoy el conjunto de datos")
    corr = sv.correlaciones_semanales(sem)
    parcial = sv.correlacion_parcial(sem)
    poda = sv.correlacion_control_poda(sem)
    techo_entre, techo_dentro = sv.descomposicion_varianza(panel.tabla)
    mejor = corr.iloc[0]
    mejor_control = parcial.iloc[0]

    tarjetas([
        ("Asociación bruta más fuerte", etiqueta(mejor.clave),
         f"r = {mejor['r (Pearson)']:+.3f} con kg/ha"),
        ("Después del calendario", etiqueta(mejor_control.clave),
         f"r = {mejor_control['r control no lineal']:+.3f}"),
        ("Variación entre módulos", f"{techo_dentro:.0f}%",
         "No puede explicarla un clima idéntico dentro de la semana"),
        ("Celdas analizadas", f"{len(panel.tabla):,}",
         f"{panel.n_modulos} módulos × {panel.n_semanas} semanas"),
    ])

    if poda.empty:
        semaforo(
            "aviso",
            "La poda todavía no está disponible para controlar el reloj biológico. "
            "La conclusión climática sigue dependiendo de la semana calendario.",
        )
    else:
        sobrevive = poda.loc[poda["Sobrevive poda"], "Variable"].tolist()
        mejor_poda = poda.iloc[0]
        if sobrevive:
            semaforo(
                "aviso",
                f"Con el proxy de días desde poda, la señal de mayor magnitud es "
                f"{mejor_poda.Variable} (r = {mejor_poda['r control poda']:+.3f}) y "
                f"mantienen evidencia estadística: {', '.join(sobrevive)}. Esto es una "
                "asociación ajustada, no un efecto causal.",
            )
        else:
            semaforo(
                "ok",
                f"Al controlar con el proxy de días desde poda, ninguna variable climática "
                f"mantiene p < 0,05. La mayor señal restante es {mejor_poda.Variable} "
                f"(r = {mejor_poda['r control poda']:+.3f}).",
            )

    st.dataframe(
        pd.DataFrame([
            {
                "Capa": "Asociación",
                "Resultado": f"{etiqueta(mejor.clave)}: r = {mejor['r (Pearson)']:+.3f}",
                "Lectura": "Qué se mueve junto con kg/ha en la campaña.",
                "No significa": "Que la variable cause el rendimiento.",
            },
            {
                "Capa": "Control por calendario",
                "Resultado": f"{etiqueta(mejor_control.clave)}: "
                f"r = {mejor_control['r control no lineal']:+.3f}",
                "Lectura": "Qué queda al retirar la forma estacional.",
                "No significa": "Que el control elimine todos los confusores.",
            },
            {
                "Capa": "Control por poda",
                "Resultado": "Disponible" if not poda.empty else "No disponible",
                "Lectura": "Qué queda al usar días desde poda como reloj biológico proxy.",
                "No significa": "Que una fecha promedio por módulo sea una fase fenológica.",
            },
            {
                "Capa": "Techo estructural",
                "Resultado": f"{techo_entre:.0f}% entre semanas / {techo_dentro:.0f}% entre módulos",
                "Lectura": "El clima semanal solo puede actuar sobre la parte entre semanas.",
                "No significa": "Que el porcentaje entre semanas sea un R² predictivo.",
            },
        ]),
        width="stretch",
        hide_index=True,
    )


def _picos_y_clima(panel: Panel) -> None:
    st.subheader("Por qué el peak de frutos aparece al inicio, medio o final")
    tray = sv.trayectorias_frutos_peso(panel.tabla)
    resumen = sv.resumen_picos_frutos_peso(panel.tabla)
    if tray.empty or resumen.empty:
        st.info(
            "No hay suficientes pares Frutos–Peso por módulo para comparar la posición "
            "del peak.",
            icon=ICONO["info"],
        )
        return

    st.markdown(
        "La posición del peak se calcula dentro de la ventana observada de cada módulo. "
        "Después se compara con días desde poda, con la dispersión de poda y con el clima "
        "de las cuatro semanas observadas que preceden al peak. Así se separa una "
        "explicación de calendario de una simple lectura de la curva."
    )
    izq, der = st.columns(2)
    with izq:
        conteo = tray["Posición del peak"].value_counts().reindex(
            ["Inicio", "Medio", "Final"], fill_value=0
        ).rename_axis("Posición").reset_index(name="Módulos")
        fig = px.bar(
            conteo, x="Posición", y="Módulos", text="Módulos",
            color="Posición", color_discrete_sequence=[AZUL, "#7f8c8d", ROJO],
        )
        fig.update_layout(
            height=330, showlegend=False, margin={"l": 10, "r": 10, "t": 10, "b": 10},
            xaxis_title="posición del peak dentro de la ventana observada",
            yaxis_title="módulos",
        )
        st.plotly_chart(fig, width="stretch")
    with der:
        variable = st.selectbox(
            "Clima para contrastar alrededor del peak",
            ["TempMin", "DPV", "Rad", "ETo", "riego_lt_planta", "gdd_semana"],
            format_func=etiqueta,
            key="conclusiones_clima_peak",
        )
        columna = {
            "TempMin": "TempMin 4sem pre-peak",
            "DPV": "DPV 4sem pre-peak",
            "Rad": "Rad 4sem pre-peak",
            "ETo": "ETo 4sem pre-peak",
            "riego_lt_planta": "Riego 4sem pre-peak",
            "gdd_semana": "GDD 4sem pre-peak",
        }[variable]
        x = "Días desde poda peak" if tray["Días desde poda peak"].notna().any() else "Semana peak frutos"
        fig = px.scatter(
            tray, x=x, y=columna, color="Posición del peak",
            hover_name="Módulo",
            hover_data={
                "Semana peak frutos": True,
                "Días desde poda peak": ":.0f",
                columna: ":.2f",
                "Cambio neto peso (g)": ":.2f",
            },
            category_orders={"Posición del peak": ["Inicio", "Medio", "Final"]},
            color_discrete_sequence=[AZUL, "#7f8c8d", ROJO],
        )
        fig.update_layout(
            height=330, margin={"l": 10, "r": 10, "t": 10, "b": 10},
            xaxis_title="días desde poda del peak" if x.startswith("Días") else "semana del peak",
            yaxis_title=f"{etiqueta(variable)}: promedio de 4 semanas pre-peak",
        )
        st.plotly_chart(fig, width="stretch")

    explica_simple(
        "El gráfico de la izquierda muestra cuántos módulos tuvieron su mejor semana de "
        "frutos al inicio, a la mitad o al final del período observado. El de la derecha "
        "compara esos grupos con el clima de las semanas justo antes de esa mejor semana."
    )
    st.dataframe(
        resumen.style.format({
            "DAP peak medio": "{:.0f}",
            "Poda dispersion dias media": "{:.0f}",
            "Semana peak media": "{:.1f}",
            "Frutos peak medio": "{:.1f}",
            "Peso peak medio (g)": "{:.2f}",
            "TempMin pre-peak": "{:.2f}",
            "DPV pre-peak": "{:.2f}",
            "Rad pre-peak": "{:.1f}",
            "ETo pre-peak": "{:.1f}",
            "Riego pre-peak": "{:.2f}",
            "GDD pre-peak": "{:.1f}",
        }),
        width="stretch",
        hide_index=True,
    )

    columna_peak_resumen = next(
        columna for columna in resumen.columns
        if str(columna).lower().startswith("posici") and "peak" in str(columna).lower()
    )
    columna_peak_tray = next(
        columna for columna in tray.columns
        if str(columna).lower().startswith("posici") and "peak" in str(columna).lower()
    )
    grupos = set(resumen[columna_peak_resumen].astype(str))
    if "Inicio" not in grupos:
        st.info(
            "En la campa�a actual no aparece un peak clasificado como Inicio: "
            f"se observan {int((tray[columna_peak_tray] == 'Medio').sum())} modulos en Medio "
            f"y {int((tray[columna_peak_tray] == 'Final').sum())} en Final. "
            "Esto describe la ventana observada disponible; no permite concluir que el "
            "cultivo nunca tenga peaks tempranos. Para medirlos hacen falta semanas de "
            "fruto anteriores o una ventana fenol�gica completa.",
            icon=ICONO["info"],
        )

    disponibles = resumen.dropna(subset=["DAP peak medio"])
    if len(disponibles) >= 2:
        temprano = disponibles.iloc[0]
        tardio = disponibles.iloc[-1]
        diff_dap = float(tardio["DAP peak medio"] - temprano["DAP peak medio"])
        diff_dispersion = float(
            tardio["Poda dispersion dias media"] - temprano["Poda dispersion dias media"]
        )
        diff_temp = float(tardio["TempMin pre-peak"] - temprano["TempMin pre-peak"])
        diff_dpv = float(tardio["DPV pre-peak"] - temprano["DPV pre-peak"])
        st.caption(f"Diferencia de dispersion media de poda entre grupos: {diff_dispersion:+.0f} dias.")
        st.markdown(
            f"**Lectura dinámica:** los peaks del grupo **{temprano['Posición del peak']}** "
            f"ocurren en promedio a {temprano['DAP peak medio']:.0f} días desde poda y "
            f"los del grupo **{tardio['Posición del peak']}** a "
            f"{tardio['DAP peak medio']:.0f} días; la diferencia es de {diff_dap:+.0f} días. "
            f"En las cuatro semanas pre-peak, la temperatura mínima cambia "
            f"{diff_temp:+.2f} °C y el DPV {diff_dpv:+.2f} kPa entre ambos grupos. "
            "Esto permite ver si el desplazamiento del peak coincide con una exposición "
            "climática distinta, pero no demuestra que el clima lo haya causado: el mismo "
            "clima semanal se comparte entre módulos y la poda tiene dispersión dentro de "
            "varios módulos."
        )

    st.caption(
        "El gráfico no afirma que el peak temprano sea bueno o malo. Responde otra cosa: "
        "si los módulos que alcanzan el máximo en momentos biológicos distintos también "
        "vieron perfiles climáticos distintos antes del máximo."
    )


def _peso_y_clima(panel: Panel) -> None:
    st.subheader("Peso del fruto: subida, bajada y olas")
    tray = sv.trayectorias_frutos_peso(panel.tabla)
    if tray.empty:
        return
    variable = st.selectbox(
        "Clima para relacionar con el cambio de peso",
        ["TempMin", "DPV", "Rad", "ETo", "riego_lt_planta", "gdd_semana"],
        format_func=etiqueta,
        key="conclusiones_clima_peso",
    )
    columna = {
        "TempMin": "TempMin 4sem pre-peak",
        "DPV": "DPV 4sem pre-peak",
        "Rad": "Rad 4sem pre-peak",
        "ETo": "ETo 4sem pre-peak",
        "riego_lt_planta": "Riego 4sem pre-peak",
        "gdd_semana": "GDD 4sem pre-peak",
    }[variable]
    fig = px.scatter(
        tray, x=columna, y="Cambio neto peso (g)", color="Posición del peak",
        hover_name="Módulo",
        hover_data={
            "Pendiente peso (g/sem)": ":.3f",
            "Cambios de sentido": True,
            "Días desde poda peak": ":.0f",
        },
        category_orders={"Posición del peak": ["Inicio", "Medio", "Final"]},
        color_discrete_sequence=[AZUL, "#7f8c8d", ROJO],
    )
    fig.add_hline(y=0, line_color="#888")
    fig.update_layout(
        height=380, margin={"l": 10, "r": 10, "t": 10, "b": 10},
        xaxis_title=f"{etiqueta(variable)}: promedio de 4 semanas pre-peak",
        yaxis_title="cambio neto del peso observado (g)",
    )
    st.plotly_chart(fig, width="stretch")
    explica_simple(
        "Cada punto es un módulo. Arriba del cero (línea horizontal) significa que el "
        "fruto terminó pesando más que al principio; abajo, que terminó pesando menos."
    )
    positivo = int((tray["Cambio neto peso (g)"] > 0).sum())
    negativo = int((tray["Cambio neto peso (g)"] < 0).sum())
    olas = int((tray["Cambios de sentido"] > 0).sum())
    st.markdown(
        f"**Lectura dinámica:** en los módulos con suficientes datos, el peso termina "
        f"por encima del inicio en {positivo}, por debajo en {negativo}, y presenta al "
        f"menos un cambio de sentido en {olas}. Por eso des+ / des- resume una trayectoria, "
        "pero no explica por sí solo cada ola. La nube permite comprobar si esas trayectorias "
        f"cambian junto con {etiqueta(variable)} antes del peak; la asociación sigue siendo "
        "observacional."
    )


def _hallazgos(panel: Panel) -> None:
    st.subheader("Hallazgos que condicionan la lectura")
    if not panel.hallazgos:
        st.success("No hay hallazgos registrados.", icon=ICONO["ok"])
        return
    orden = {"alta": 0, "media": 1, "baja": 2}
    filas = [
        {
            "Gravedad": h.gravedad,
            "Hallazgo": h.titulo,
            "Qué cambia": h.detalle,
            "Efecto": h.efecto,
        }
        for h in sorted(panel.hallazgos, key=lambda h: orden[h.gravedad])
    ]
    st.dataframe(pd.DataFrame(filas), width="stretch", hide_index=True)


def _modelo(panel: Panel) -> None:
    with st.expander("Aporte predictivo: cómo leerlo sin llamarlo impacto", expanded=False):
        st.markdown(
            "El R² pertenece al modelo completo y sus ablaciones dicen cuánto pierde "
            "este modelo al retirar una variable o una familia. No es el porcentaje de "
            "impacto agronómico de cada variable. La validación honesta sigue en "
            "Qué explica el R² y Modelo predictivo."
        )
        if st.button(
            "Calcular el resumen predictivo en esta pantalla",
            key="conclusiones_calcular_modelo",
            type="primary",
        ):
            validacion = sv.tabla_validacion(panel.tabla)
            st.dataframe(validacion, width="stretch", hide_index=True)
            como_leer(
                "Esta tabla permite comparar modelos y particiones. El valor que debe "
                "guiar la conclusión es el de validación temporal/bloque, no el R² "
                "aleatorio ni un SHAP calculado sobre las mismas filas.",
                "Lectura del R²",
            )
        else:
            st.caption("Se calcula bajo demanda porque entrena varios modelos.")


def render(panel: Panel) -> None:
    sem = sv.agregar_por_semana(panel.tabla)
    st.warning(
        "**Conclusión provisional:** el panel ya puede ordenar el ciclo por poda y "
        "relacionar el desplazamiento de frutos y peso con el clima observado alrededor "
        "del peak. La fecha de módulo es un proxy porque M_Poda está a nivel de lote; "
        "todavía no es una estimación causal.",
        icon=ICONO["aviso"],
    )
    _resumen_evidencia(panel, sem)
    st.divider()
    _relacion_individual_y_conjunta(panel, sem)
    st.divider()
    _picos_y_clima(panel)
    st.divider()
    _peso_y_clima(panel)
    st.divider()
    _hallazgos(panel)
    _modelo(panel)
    variables = [c for c in CLIMA if c in panel.tabla.columns]
    if variables:
        st.caption("Variables climáticas usadas en las comparaciones: " +
                   ", ".join(etiqueta(c) for c in variables))

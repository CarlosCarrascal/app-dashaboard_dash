"""Gráficos de la mesa operativa de cosecha."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .proyeccion_domain import FUNDOS_OPERATIVOS, etiqueta_semana

COLORES = {
    "real": "#172033",
    "parcial": "#d97706",
    "modelo": "#0f766e",
    "r09": "#64748b",
    "nowcast": "#7c3aed",
    "hibrido_v2": "#2563eb",
    "grid": "#e6ece9",
}
COLORES_FUNDO = {
    "Arena": "#2563eb",
    "Ayllu": "#7c3aed",
    "Kawsay": "#0f766e",
    "Quri": "#d97706",
}


def _base(height: int) -> go.Figure:
    return go.Figure().update_layout(
        template="plotly_white",
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="closest",
        font={"family": "Inter, 'Segoe UI', system-ui, sans-serif", "color": "#273b34"},
        margin={"l": 58, "r": 22, "t": 38, "b": 48},
        xaxis={"gridcolor": COLORES["grid"], "showgrid": True},
        yaxis={"gridcolor": COLORES["grid"], "rangemode": "tozero", "tickformat": "~s"},
        legend={"orientation": "h", "y": 1.10, "x": 0},
    )


def _semanal(tabla: pd.DataFrame, valor: str) -> pd.DataFrame:
    if not isinstance(tabla, pd.DataFrame) or tabla.empty or valor not in tabla:
        return pd.DataFrame(columns=["semana_inicio", "semana_cierre", "rango_semana", valor])
    salida = tabla.copy()
    if "semana_inicio" not in salida:
        fechas = pd.to_datetime(salida["fecha_objetivo"], errors="coerce")
        salida["semana_inicio"] = fechas - pd.to_timedelta(fechas.dt.weekday, unit="D")
    salida[valor] = pd.to_numeric(salida[valor], errors="coerce")
    salida = salida.dropna(subset=["semana_inicio", valor])
    agregaciones: dict[str, object] = {valor: lambda serie: serie.sum(min_count=1)}
    if "version_fuente" in salida:
        agregaciones["version_fuente"] = lambda serie: " / ".join(
            sorted({str(valor) for valor in serie.dropna() if str(valor).strip()})
        )
    if "fecha_emision" in salida:
        agregaciones["fecha_emision"] = lambda serie: " / ".join(
            sorted(
                {
                    fecha.strftime("%d/%m/%Y")
                    for fecha in pd.to_datetime(serie, errors="coerce").dropna()
                }
            )
        )
    salida = salida.groupby("semana_inicio", as_index=False).agg(agregaciones)
    salida["semana_cierre"] = salida["semana_inicio"] + pd.Timedelta(days=6)
    salida["rango_semana"] = salida["semana_inicio"].map(etiqueta_semana)
    return salida.sort_values("semana_inicio")


def _agregar_serie(
    figura: go.Figure,
    tabla: pd.DataFrame,
    valor: str,
    *,
    nombre: str,
    color: str,
    dash: str = "solid",
    width: float = 2.5,
    fill: str | None = None,
    fillcolor: str | None = None,
    row: int | None = None,
    col: int | None = None,
    estado: str = "Proyección semanal",
    mostrar_version: bool = False,
) -> pd.DataFrame:
    semanal = _semanal(tabla, valor)
    if semanal.empty:
        return semanal
    valores = semanal[valor].map(lambda x: f"{x:,.0f}".replace(",", "."))
    versiones = (
        semanal["version_fuente"].fillna("").astype(str)
        if "version_fuente" in semanal
        else pd.Series([""] * len(semanal), index=semanal.index)
    )
    emisiones = (
        semanal["fecha_emision"].fillna("").astype(str) if "fecha_emision" in semanal else versiones
    )
    datos_hover = {
        "periodo": semanal["rango_semana"],
        "kg": valores,
        "estado": [estado] * len(semanal),
    }
    hover = (
        "<b>%{customdata[0]}</b><br>" + nombre + ": <b>%{customdata[1]} kg</b><br>"
        "%{customdata[2]}<extra></extra>"
    )
    if mostrar_version:
        datos_hover["emision"] = emisiones
        hover = (
            "<b>%{customdata[0]}</b><br>" + nombre + ": <b>%{customdata[1]} kg</b><br>"
            "Emisión: <b>%{customdata[3]}</b><br>"
            "%{customdata[2]}<extra></extra>"
        )
    traza = go.Scatter(
        x=semanal["semana_cierre"],
        y=semanal[valor],
        name=nombre,
        mode="lines+markers",
        line={"color": color, "width": width, "dash": dash},
        marker={"size": 6},
        fill=fill,
        fillcolor=fillcolor,
        customdata=pd.DataFrame(datos_hover),
        hovertemplate=hover,
        legendgroup=nombre,
        showlegend=row in (None, 1) and col in (None, 1),
    )
    if row is None:
        figura.add_trace(traza)
    else:
        figura.add_trace(traza, row=row, col=col)
    return semanal


def curva_operativa_actual(
    modelo: pd.DataFrame,
    r09: pd.DataFrame,
    real: pd.DataFrame,
    *,
    mostrar_r09: bool = False,
    nowcast: pd.DataFrame | None = None,
    mostrar_nowcast: bool = False,
    hibrido_v2: pd.DataFrame | None = None,
    mostrar_hibrido_v2: bool = False,
    fecha_hoy: object | None = None,
) -> go.Figure:
    """Curva operativa y comparaciones opcionales.

    ``nowcast`` es un producto distinto del plan de 1--6 semanas: estima el cierre
    del miércoles usando el avance de lunes y martes. Solo se dibuja cuando el usuario
    lo solicita, para no mezclarlo con la planificación futura.
    """
    figura = _base(430)
    hoy = pd.to_datetime(fecha_hoy, errors="coerce")
    if pd.isna(hoy):
        hoy = pd.Timestamp.now().normalize()
    semana_actual = hoy - pd.Timedelta(days=hoy.weekday())

    real_sem = _semanal(real, "real_kg")
    semana_parcial = semana_actual
    if not real_sem.empty and "ultima_fecha_real" in real:
        ultima_fecha = pd.to_datetime(real["ultima_fecha_real"], errors="coerce").max()
        if pd.notna(ultima_fecha):
            ultima_semana = ultima_fecha - pd.Timedelta(days=ultima_fecha.weekday())
            # Una semana se considera materialmente cerrada cuando la fuente alcanzó
            # al menos el sábado. Si solo llegó a martes, como S34, se muestra parcial
            # aunque el calendario ya haya pasado al lunes siguiente.
            if ultima_fecha < ultima_semana + pd.Timedelta(days=5):
                semana_parcial = ultima_semana
    cerrada = real_sem[
        (real_sem["semana_inicio"] < semana_actual) & ~real_sem["semana_inicio"].eq(semana_parcial)
    ]
    parcial = real_sem[real_sem["semana_inicio"].eq(semana_parcial)]
    if not cerrada.empty:
        figura.add_trace(
            go.Scatter(
                x=cerrada.semana_cierre,
                y=cerrada.real_kg,
                name="Real cosechado",
                mode="lines+markers",
                line={"color": COLORES["real"], "width": 3},
                marker={"size": 6},
                customdata=pd.DataFrame(
                    {
                        "periodo": cerrada["rango_semana"],
                        "kg": cerrada["real_kg"].map(lambda x: f"{x:,.0f}".replace(",", ".")),
                    }
                ),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>Real cosechado: "
                    "<b>%{customdata[1]} kg</b><br>Semana cerrada<extra></extra>"
                ),
            )
        )
    if not parcial.empty:
        figura.add_trace(
            go.Scatter(
                x=parcial.semana_cierre,
                y=parcial.real_kg,
                name="Real parcial",
                mode="markers",
                marker={"color": COLORES["parcial"], "size": 10, "symbol": "diamond"},
                customdata=pd.DataFrame(
                    {
                        "periodo": parcial["rango_semana"],
                        "kg": parcial["real_kg"].map(lambda x: f"{x:,.0f}".replace(",", ".")),
                    }
                ),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>Real disponible: "
                    "<b>%{customdata[1]} kg</b><br>Fuente todavía parcial<extra></extra>"
                ),
            )
        )

    modelo_sem = _agregar_serie(
        figura,
        modelo,
        "p50_kg",
        nombre="Modelo Python",
        color=COLORES["modelo"],
        width=3,
        fill="tozeroy",
        fillcolor="rgba(15, 118, 110, 0.10)",
        estado="Estimación de la Macro Python al cierre de la semana",
    )
    if mostrar_r09:
        _agregar_serie(
            figura,
            r09,
            "p50_kg",
            nombre="R09 publicado",
            color=COLORES["r09"],
            dash="dash",
            width=2,
            estado="Referencia publicada; no se extrapola",
            mostrar_version=True,
        )
    if mostrar_nowcast:
        _agregar_serie(
            figura,
            nowcast if isinstance(nowcast, pd.DataFrame) else pd.DataFrame(),
            "p50_kg",
            nombre="NowcastCierreSemanal_v1 · cierre miércoles",
            color=COLORES["nowcast"],
            dash="dot",
            width=2.2,
            estado=(
                "Nowcast emitido el miércoles con kilos observados lunes-martes; "
                "solo comparación histórica"
            ),
        )
    if mostrar_hibrido_v2:
        _agregar_serie(
            figura,
            hibrido_v2 if isinstance(hibrido_v2, pd.DataFrame) else pd.DataFrame(),
            "p50_kg",
            nombre="Híbrido ocurrencia v2",
            color=COLORES["hibrido_v2"],
            dash="dashdot",
            width=2.6,
            estado=(
                "Comparación del Híbrido ocurrencia v2 con su corrida normal de seis "
                "semanas; no modifica el plan operativo de la Macro"
            ),
            mostrar_version=True,
        )

    if not modelo_sem.empty:
        futuras = modelo_sem[modelo_sem["semana_inicio"] > semana_actual]
        inicio_futuro = (
            futuras["semana_inicio"].min()
            if not futuras.empty
            else modelo_sem["semana_inicio"].min()
        )
        figura.add_vline(
            x=inicio_futuro,
            line={"color": "#85a99d", "width": 1.2, "dash": "dot"},
        )
        figura.add_annotation(
            x=inicio_futuro,
            y=1,
            yref="paper",
            text="Semanas futuras",
            showarrow=False,
            xanchor="left",
            yanchor="bottom",
            font={"size": 11, "color": COLORES["modelo"]},
        )
    if not parcial.empty and semana_parcial == semana_actual:
        figura.add_vrect(
            x0=semana_actual,
            x1=semana_actual + pd.Timedelta(days=6),
            fillcolor="rgba(217, 119, 6, 0.07)",
            line_width=0,
            layer="below",
        )
        figura.add_annotation(
            x=semana_actual + pd.Timedelta(days=3),
            y=1,
            yref="paper",
            text="Semana en curso",
            showarrow=False,
            yanchor="bottom",
            font={"size": 10, "color": COLORES["parcial"]},
        )

    figura.update_layout(
        xaxis_title="Cierre de semana de cosecha",
        yaxis_title="Kg por semana",
        uirevision="proyeccion-operativa",
    )
    figura.update_xaxes(tickformat="%d %b\n%Y", hoverformat="%d/%m/%Y", automargin=True)
    return figura


def curvas_por_fundo(modelo: pd.DataFrame, real: pd.DataFrame) -> go.Figure:
    """Cuatro perfiles semanales comparables con una escala común de kilos."""
    del real
    if not isinstance(modelo, pd.DataFrame) or modelo.empty:
        figura = _base(280)
        figura.add_annotation(
            text="No hay proyección por fundo para este filtro.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
        return figura

    tabla = modelo.copy()
    tabla["p50_kg"] = pd.to_numeric(tabla.get("p50_kg"), errors="coerce")
    agregado = (
        tabla.dropna(subset=["semana_inicio", "fundo", "p50_kg"])
        .groupby(["fundo", "semana_inicio"], as_index=False)["p50_kg"]
        .sum(min_count=1)
    )
    semanas = sorted(pd.to_datetime(agregado["semana_inicio"].unique()))
    fundos = [fundo for fundo in FUNDOS_OPERATIVOS if fundo in set(agregado["fundo"])]
    if not semanas or not fundos:
        return _base(280)

    rellenos = {
        "Arena": "rgba(37, 99, 235, 0.12)",
        "Ayllu": "rgba(124, 58, 237, 0.12)",
        "Kawsay": "rgba(15, 118, 110, 0.12)",
        "Quri": "rgba(217, 119, 6, 0.13)",
    }
    figura = make_subplots(
        rows=1,
        cols=len(fundos),
        shared_yaxes=True,
        horizontal_spacing=0.045,
    )

    maximo = float(agregado["p50_kg"].max()) if not agregado.empty else 0.0
    limite_y = maximo * 1.18 if maximo > 0 else 1.0
    tickvals = [pd.Timestamp(fecha) + pd.Timedelta(days=6) for fecha in semanas]
    ticktext = [pd.Timestamp(fecha).strftime("%d/%m") for fecha in semanas]

    for indice, fundo in enumerate(fundos, start=1):
        parte = (
            agregado[agregado["fundo"].eq(fundo)]
            .set_index("semana_inicio")
            .reindex(semanas)
            .reset_index()
        )
        parte["semana_cierre"] = pd.to_datetime(parte["semana_inicio"]) + pd.Timedelta(days=6)
        parte["rango_semana"] = pd.to_datetime(parte["semana_inicio"]).map(etiqueta_semana)
        total = float(parte["p50_kg"].fillna(0).sum())
        figura.add_trace(
            go.Scatter(
                x=parte["semana_cierre"],
                y=parte["p50_kg"],
                name=fundo,
                mode="lines+markers",
                line={"color": COLORES_FUNDO[fundo], "width": 2.6},
                marker={"size": 6, "color": COLORES_FUNDO[fundo]},
                fill="tozeroy",
                fillcolor=rellenos[fundo],
                customdata=parte[["rango_semana"]],
                hovertemplate=(
                    "%{customdata[0]}<br><b>%{y:,.0f} kg</b><extra>" + fundo + "</extra>"
                ),
                showlegend=False,
            ),
            row=1,
            col=indice,
        )
        total_texto = (
            f"{total / 1_000_000:.2f} M kg" if total >= 1_000_000 else f"{total / 1000:.0f} mil kg"
        )
        figura.add_annotation(
            x=0,
            y=1.16,
            xref=f"x{indice} domain" if indice > 1 else "x domain",
            yref="paper",
            text=(
                f"<b>{fundo}</b><br>"
                f"<span style='font-size:11px;color:#6b7a74'>"
                f"{total_texto} · 6 semanas</span>"
            ),
            showarrow=False,
            xanchor="left",
            align="left",
        )
        figura.update_xaxes(
            tickvals=tickvals,
            ticktext=ticktext,
            tickangle=0,
            showgrid=False,
            zeroline=False,
            row=1,
            col=indice,
        )
        figura.update_yaxes(
            range=[0, limite_y],
            tickformat="~s",
            gridcolor=COLORES["grid"],
            showticklabels=indice == 1,
            title_text="kg/semana" if indice == 1 else "",
            row=1,
            col=indice,
        )

    figura.update_layout(
        template="plotly_white",
        height=300,
        margin={"l": 58, "r": 18, "t": 68, "b": 42},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, 'Segoe UI', system-ui, sans-serif", "color": "#273b34"},
        hovermode="closest",
        uirevision="proyeccion-fundos",
    )
    return figura


def figura_nowcast_cierre(tabla: pd.DataFrame) -> go.Figure:
    """Compara el cierre estimado el miércoles contra el cierre real.

    Esta figura no representa el plan previo de seis semanas. Usa únicamente la
    release histórica aprobada del producto de cierre intra-semanal.
    """
    figura = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.76, 0.24],
    )
    if not isinstance(tabla, pd.DataFrame) or tabla.empty:
        figura.add_annotation(
            text="No existe una validación histórica aprobada para el cierre semanal.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
        return figura.update_layout(
            template="plotly_white",
            height=430,
            margin={"l": 58, "r": 20, "t": 30, "b": 46},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )

    if "fundo" not in tabla.columns:
        return figura_nowcast_cierre(pd.DataFrame())
    empresa = tabla.loc[tabla["fundo"].astype(str).eq("Empresa")].copy()
    if empresa.empty:
        empresa = tabla.groupby(["campania", "semana_inicio"], as_index=False).agg(
            semana_cierre=("semana_cierre", "max"),
            p50_kg=("p50_kg", "sum"),
            real_kg=("real_kg", "sum"),
            macro_kg=("macro_kg", "sum"),
            r09_misma_semana_kg=("r09_misma_semana_kg", lambda x: x.sum(min_count=1)),
        )
    for column in ("semana_inicio", "semana_cierre"):
        empresa[column] = pd.to_datetime(empresa[column], errors="coerce")
    for column in ("p50_kg", "real_kg", "macro_kg", "r09_misma_semana_kg"):
        empresa[column] = pd.to_numeric(empresa.get(column), errors="coerce")
    empresa = empresa.dropna(subset=["semana_inicio", "p50_kg", "real_kg"]).sort_values(
        "semana_inicio"
    )
    empresa["semana_cierre"] = empresa.semana_cierre.fillna(
        empresa.semana_inicio + pd.Timedelta(days=6)
    )
    empresa["periodo"] = empresa.semana_inicio.map(etiqueta_semana)
    empresa["error_kg"] = empresa.p50_kg - empresa.real_kg

    def _trace(column: str, name: str, color: str, dash: str = "solid", width: float = 2.5):
        valid = empresa[column].notna()
        values = empresa.loc[valid, column]
        custom = pd.DataFrame(
            {
                "periodo": empresa.loc[valid, "periodo"],
                "kg": values.map(lambda value: f"{value:,.0f}".replace(",", ".")),
            }
        )
        figura.add_trace(
            go.Scatter(
                x=empresa.loc[valid, "semana_cierre"],
                y=values,
                name=name,
                mode="lines+markers",
                line={"color": color, "width": width, "dash": dash},
                marker={"size": 6},
                customdata=custom,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    + name
                    + ": <b>%{customdata[1]} kg</b><extra></extra>"
                ),
            ),
            row=1,
            col=1,
        )

    _trace("real_kg", "Cierre real", COLORES["real"], width=3)
    _trace("p50_kg", "Nowcast miércoles", COLORES["modelo"], width=3)
    if empresa.r09_misma_semana_kg.notna().any():
        _trace("r09_misma_semana_kg", "R09 ajustado en la semana", COLORES["r09"], "dash", 1.8)

    colores_error = np.where(empresa.error_kg.ge(0), "#c95f32", "#34889a")
    figura.add_trace(
        go.Bar(
            x=empresa.semana_cierre,
            y=empresa.error_kg,
            name="Desviación",
            marker_color=colores_error,
            customdata=pd.DataFrame(
                {
                    "periodo": empresa.periodo,
                    "kg": empresa.error_kg.map(lambda value: f"{value:+,.0f}".replace(",", ".")),
                }
            ),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>Desviación: <b>%{customdata[1]} kg</b><extra></extra>"
            ),
            showlegend=False,
        ),
        row=2,
        col=1,
    )
    figura.add_hline(y=0, line={"color": "#9aaba5", "width": 1}, row=2, col=1)
    figura.update_layout(
        template="plotly_white",
        height=470,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        font={"family": "Inter, 'Segoe UI', system-ui, sans-serif", "color": "#273b34"},
        margin={"l": 62, "r": 20, "t": 36, "b": 48},
        legend={"orientation": "h", "y": 1.10, "x": 0},
        uirevision="nowcast-cierre-semanal",
    )
    figura.update_yaxes(
        title_text="kg por semana", tickformat="~s", gridcolor=COLORES["grid"], row=1, col=1
    )
    figura.update_yaxes(
        title_text="desviación", tickformat="~s", gridcolor=COLORES["grid"], row=2, col=1
    )
    figura.update_xaxes(tickformat="%d %b\n%Y", hoverformat="%d/%m/%Y", row=2, col=1)
    return figura


def historico_y_desviacion(
    agrupada: pd.DataFrame,
    *,
    nombre_serie: str,
    granularidad: str = "mes",
) -> go.Figure:
    """Curvas para varios períodos; comparación compacta si solo existe uno."""
    es_resumen = (
        isinstance(agrupada, pd.DataFrame)
        and not agrupada.empty
        and (granularidad == "campania" or len(agrupada) == 1)
    )
    if es_resumen:
        figura = go.Figure()
        lineas_x: list[float | None] = []
        lineas_y: list[str | None] = []
        for fila in agrupada.itertuples(index=False):
            lineas_x.extend([float(fila.real_kg), float(fila.proyectado_kg), None])
            lineas_y.extend([str(fila.etiqueta), str(fila.etiqueta), None])
        figura.add_trace(
            go.Scatter(
                x=lineas_x,
                y=lineas_y,
                mode="lines",
                line={"color": "#cbd5d1", "width": 7},
                hoverinfo="skip",
                showlegend=False,
            )
        )
        figura.add_trace(
            go.Scatter(
                x=agrupada["real_kg"],
                y=agrupada["etiqueta"],
                name="Cosecha real",
                mode="markers",
                marker={"color": COLORES["real"], "size": 13},
                hovertemplate="%{y}<br>Real: <b>%{x:,.0f} kg</b><extra></extra>",
            )
        )
        figura.add_trace(
            go.Scatter(
                x=agrupada["proyectado_kg"],
                y=agrupada["etiqueta"],
                name=nombre_serie,
                mode="markers+text",
                marker={"color": COLORES["modelo"], "size": 13},
                text=[f"{valor:+,.0f} kg" for valor in agrupada["desviacion_kg"]],
                textposition="middle right",
                textfont={"size": 12, "color": "#50655d"},
                customdata=agrupada[["real_kg", "desviacion_kg"]],
                hovertemplate=(
                    "%{y}<br>Proyección: <b>%{x:,.0f} kg</b>"
                    "<br>Real: %{customdata[0]:,.0f} kg"
                    "<br>Desviación: %{customdata[1]:+,.0f} kg<extra></extra>"
                ),
            )
        )
        figura.update_layout(
            template="plotly_white",
            height=max(245, 95 + 58 * len(agrupada)),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"family": "Inter, 'Segoe UI', system-ui, sans-serif", "color": "#273b34"},
            margin={"l": 86, "r": 125, "t": 48, "b": 48},
            legend={"orientation": "h", "y": 1.16, "x": 0},
            xaxis={
                "title": "Kg de campaña" if granularidad == "campania" else "Kg del período",
                "tickformat": "~s",
                "gridcolor": COLORES["grid"],
            },
            yaxis={"title": "", "showgrid": False},
            hovermode="closest",
            uirevision=f"proyeccion-historica-resumen-{granularidad}",
        )
        return figura

    figura = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.69, 0.31],
        vertical_spacing=0.08,
    )
    if not isinstance(agrupada, pd.DataFrame) or agrupada.empty:
        figura.add_annotation(
            text="No hay predicciones históricas evaluables para esta selección.",
            x=0.5,
            y=0.55,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"color": "#63736d"},
        )
    else:
        x = pd.to_datetime(agrupada["orden"], errors="coerce")
        etiquetas = agrupada["etiqueta"].astype(str)
        figura.add_trace(
            go.Scatter(
                x=x,
                y=agrupada["real_kg"],
                name="Cosecha real",
                mode="lines+markers",
                line={"color": COLORES["real"], "width": 2.8},
                marker={"color": COLORES["real"], "size": 7},
                customdata=etiquetas,
                hovertemplate="%{customdata}<br>%{y:,.0f} kg<extra>Cosecha real</extra>",
            ),
            row=1,
            col=1,
        )
        figura.add_trace(
            go.Scatter(
                x=x,
                y=agrupada["proyectado_kg"],
                name=nombre_serie,
                mode="lines+markers",
                line={"color": COLORES["modelo"], "width": 2.8},
                marker={"color": COLORES["modelo"], "size": 7},
                customdata=etiquetas,
                hovertemplate="%{customdata}<br>%{y:,.0f} kg<extra>" + nombre_serie + "</extra>",
            ),
            row=1,
            col=1,
        )
        colores = ["#c95f35" if valor > 0 else "#2f7f91" for valor in agrupada["desviacion_kg"]]
        figura.add_trace(
            go.Bar(
                x=x,
                y=agrupada["desviacion_kg"],
                name="Desviación",
                marker={"color": colores, "line": {"width": 0}},
                customdata=pd.DataFrame(
                    {
                        "etiqueta": etiquetas,
                        "real_kg": agrupada["real_kg"],
                        "proyectado_kg": agrupada["proyectado_kg"],
                    }
                ),
                hovertemplate=(
                    "%{customdata[0]}<br>Desviación: %{y:+,.0f} kg"
                    "<br>Real: %{customdata[1]:,.0f} kg"
                    "<br>Proyección: %{customdata[2]:,.0f} kg<extra></extra>"
                ),
                showlegend=False,
            ),
            row=2,
            col=1,
        )
        figura.add_hline(y=0, line_color="#95a39e", line_width=1, row=2, col=1)
    figura.update_layout(
        template="plotly_white",
        height=465,
        bargap=0.38,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, 'Segoe UI', system-ui, sans-serif", "color": "#273b34"},
        margin={"l": 66, "r": 24, "t": 48, "b": 72},
        legend={"orientation": "h", "y": 1.08, "x": 0},
        hovermode="x unified",
        uirevision="proyeccion-historica",
    )
    figura.update_yaxes(title_text="Kg", tickformat="~s", gridcolor=COLORES["grid"], row=1, col=1)
    figura.update_yaxes(
        title_text="Diferencia", tickformat="~s", gridcolor=COLORES["grid"], row=2, col=1
    )
    if granularidad == "semana":
        figura.update_xaxes(
            dtick=14 * 24 * 60 * 60 * 1000,
            tickformat="%d %b<br>%Y",
            tickangle=0,
            showgrid=False,
            row=2,
            col=1,
        )
    else:
        figura.update_xaxes(
            dtick="M1",
            tickformat="%b<br>%Y",
            tickangle=0,
            showgrid=False,
            row=2,
            col=1,
        )
    return figura


def figura_matriz_six(matriz: pd.DataFrame) -> go.Figure:
    figura = _base(390)
    if not isinstance(matriz, pd.DataFrame) or matriz.empty:
        figura.add_annotation(
            text="No hay emisiones históricas suficientes para construir la Matriz SIX.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
        return figura
    vista = matriz.tail(10)
    x = [f"S{pd.Timestamp(col).isocalendar().week:02d}" for col in vista.columns]
    y = [f"Emisión {pd.Timestamp(idx):%d/%m}" for idx in vista.index]
    figura = go.Figure(
        go.Heatmap(
            z=vista.to_numpy(dtype=float),
            x=x,
            y=y,
            colorscale=[[0, "#f2f7f4"], [1, "#0f766e"]],
            colorbar={"title": "kg", "tickformat": "~s"},
            hovertemplate="%{y}<br>Objetivo %{x}<br>%{z:,.0f} kg<extra></extra>",
        )
    )
    figura.update_layout(
        template="plotly_white",
        height=390,
        paper_bgcolor="rgba(0,0,0,0)",
        margin={"l": 105, "r": 25, "t": 20, "b": 45},
        xaxis_title="Semana objetivo",
        yaxis_title="",
        font={"family": "Inter, system-ui, sans-serif", "color": "#273b34"},
    )
    return figura


def curva_historica(curva: pd.DataFrame) -> go.Figure:
    """Comparación histórica secundaria; nunca se usa como curva operativa."""
    figura = _base(400)
    if not isinstance(curva, pd.DataFrame) or curva.empty:
        return figura
    tabla = curva.copy()
    tabla["fecha_objetivo"] = pd.to_datetime(tabla["fecha_objetivo"], errors="coerce")
    colores = {
        "Real cosechado": COLORES["real"],
        "R09_publicado": COLORES["r09"],
        "ModeloOperativoActual_v1": COLORES["modelo"],
        "MacroLegacy_v1": "#b45309",
        "HibridoOcurrenciaOnline_v2": COLORES["modelo"],
        "HibridoParametrosAsOf_v1": "#7c3aed",
    }
    etiquetas = {
        "Real cosechado": "Real",
        "R09_publicado": "R09 publicado",
        "ModeloOperativoActual_v1": "Macro operativa",
        "MacroLegacy_v1": "Macro legacy",
        "HibridoOcurrenciaOnline_v2": "Híbrido ocurrencia v2",
        "HibridoParametrosAsOf_v1": "Híbrido parámetros as-of",
    }
    for modelo in (
        "Real cosechado",
        "R09_publicado",
        "ModeloOperativoActual_v1",
        "MacroLegacy_v1",
        "HibridoOcurrenciaOnline_v2",
        "HibridoParametrosAsOf_v1",
    ):
        parte = tabla[tabla.modelo.astype(str).eq(modelo)].sort_values("fecha_objetivo")
        if parte.empty:
            continue
        figura.add_trace(
            go.Scatter(
                x=parte.fecha_objetivo,
                y=pd.to_numeric(parte.p50_kg, errors="coerce"),
                name=etiquetas[modelo],
                mode="lines+markers",
                line={"color": colores[modelo], "width": 2.5},
            )
        )
    figura.update_layout(xaxis_title="Semana objetivo", yaxis_title="Kg")
    return figura

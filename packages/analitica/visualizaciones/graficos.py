"""Constructores de figuras Plotly. Reciben datos, devuelven `go.Figure`, no dibujan.

Separados de las vistas para que la lógica de presentación sea probable sin Streamlit y
para que el estilo (alturas, márgenes, paleta) esté en un solo lugar.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from ..config import AZUL, ETIQUETAS, GRIS, NARANJA, ROJO, VERDE, etiqueta

MARGEN = {"l": 10, "r": 10, "t": 10, "b": 10}
DIVERGENTE = "RdBu_r"
ESTACIONAL = "Turbo"  # color por número de semana


def _limpio(fig: go.Figure, alto: int, **layout) -> go.Figure:
    """Alto y márgenes uniformes. `margin` se puede sobrescribir desde la llamada."""
    layout.setdefault("margin", MARGEN)
    fig.update_layout(height=alto, **layout)
    return fig


def matriz_correlacion(corr: pd.DataFrame) -> go.Figure:
    fig = px.imshow(
        corr.values, x=list(corr.columns), y=list(corr.index),
        color_continuous_scale=DIVERGENTE, zmin=-1, zmax=1,
        text_auto=".2f", aspect="auto",
    )
    return _limpio(fig, 520, margin={**MARGEN, "t": 30})


def barras_correlacion(valores: pd.Series, titulo_x: str) -> go.Figure:
    """Barras horizontales de correlación, con el cero como referencia visual."""
    v = valores.sort_values()
    fig = px.bar(
        x=v.values, y=[etiqueta(i) for i in v.index], orientation="h",
        color=v.values, color_continuous_scale=DIVERGENTE, range_color=[-1, 1],
        range_x=[-1, 1], labels={"x": titulo_x, "y": ""},
    )
    return _limpio(fig, max(300, 46 * len(v)), coloraxis_showscale=False)


def dispersion_contra_objetivo(tabla: pd.DataFrame, col: str) -> go.Figure:
    """Dispersión coloreada por semana, con recta de ajuste.

    La recta se calcula con numpy: `trendline="ols"` de plotly arrastraría statsmodels
    como dependencia solo para esto.
    """
    fig = px.scatter(
        tabla, x=col, y="KgHa", color="nsem",
        hover_data=["Fundo", "Modulo", "Semana"], color_continuous_scale=ESTACIONAL,
        labels={col: etiqueta(col), "KgHa": "kg/ha", "nsem": "semana"},
    )
    x, y = tabla[col].to_numpy(), tabla.KgHa.to_numpy()
    pendiente, origen = np.polyfit(x, y, 1)
    xs = np.linspace(x.min(), x.max(), 50)
    r = float(np.corrcoef(x, y)[0, 1])
    fig.add_trace(
        go.Scatter(
            x=xs, y=pendiente * xs + origen, mode="lines",
            line={"color": GRIS, "dash": "dash"}, name=f"ajuste lineal · r={r:+.2f}",
            hovertemplate=f"pendiente: {pendiente:+,.0f} kg/ha por unidad<extra></extra>",
        )
    )
    return _limpio(fig, 460, legend={"orientation": "h", "y": 1.1})


def barras_importancia(importancia: pd.Series) -> go.Figure:
    v = importancia[::-1]
    fig = px.bar(
        x=v.values, y=[etiqueta(i) for i in v.index], orientation="h",
        color=v.values, color_continuous_scale="Blues",
        labels={"x": "|SHAP| medio (kg/ha)", "y": ""},
    )
    return _limpio(fig, 340, coloraxis_showscale=False)


def summary_shap(
    shap_values: np.ndarray, X: pd.DataFrame, orden: list[str], tabla: pd.DataFrame,
    unidad: str = "kg/ha",
) -> go.Figure:
    """Enjambre de puntos: un punto por celda, color según el valor de la variable."""
    columnas = list(X.columns)
    fig = go.Figure()
    for i, col in enumerate(orden):
        j = columnas.index(col)
        v = X[col].to_numpy()
        # Normalizado a 0-1 solo para el color: azul = valor bajo, rojo = valor alto.
        rango = v.max() - v.min()
        vn = (v - v.min()) / rango if rango > 0 else np.zeros_like(v)
        # Dispersión vertical determinista: misma figura en cada recarga.
        rng = np.random.default_rng(i)
        fig.add_trace(
            go.Scatter(
                x=shap_values[:, j], y=i + rng.uniform(-0.18, 0.18, len(v)), mode="markers",
                marker={
                    "size": 5, "color": vn, "colorscale": [[0, AZUL], [1, ROJO]],
                    "showscale": i == len(orden) - 1, "opacity": 0.65,
                    "colorbar": {
                        "title": "valor de<br>la variable",
                        "tickvals": [0, 1], "ticktext": ["bajo", "alto"],
                    },
                },
                name=etiqueta(col), showlegend=False,
                customdata=np.c_[tabla.Fundo, tabla.Modulo, tabla.Semana, v],
                hovertemplate=(
                    "%{customdata[0]} · %{customdata[1]} · %{customdata[2]}<br>"
                    f"{etiqueta(col)}: " "%{customdata[3]:.2f}<br>"
                    f"efecto SHAP: %{{x:+.2f}} {unidad}<extra></extra>"
                ),
            )
        )
    fig.add_vline(x=0, line_dash="dash", line_color="#888")
    return _limpio(
        fig, 460,
        xaxis_title=f"efecto sobre {unidad} (SHAP)",
        yaxis={
            "tickmode": "array", "tickvals": list(range(len(orden))),
            "ticktext": [etiqueta(c) for c in orden],
        },
    )


def dependencia_shap(
    shap_values: np.ndarray, X: pd.DataFrame, col: str, semanas: pd.Series,
    unidad: str = "kg/ha",
) -> go.Figure:
    j = list(X.columns).index(col)
    fig = px.scatter(
        x=X[col].to_numpy(), y=shap_values[:, j], color=semanas,
        color_continuous_scale=ESTACIONAL,
        labels={"x": etiqueta(col), "y": f"efecto SHAP de {etiqueta(col)} ({unidad})",
                "color": "semana"},
    )
    fig.add_hline(y=0, line_dash="dash", line_color="#888")
    return _limpio(fig, 440)


def waterfall(
    base: float, contribuciones: pd.Series, prediccion: float, titulo: str
) -> go.Figure:
    """Descomposición de una predicción: del promedio general al valor de esta celda."""
    orden = contribuciones.reindex(contribuciones.abs().sort_values(ascending=False).index)
    mil = lambda v, f="{:,.0f}": f.format(v).replace(",", ".")  # noqa: E731
    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=["absolute"] + ["relative"] * len(orden) + ["total"],
            x=["Promedio general"] + [etiqueta(i) for i in orden.index] + ["Predicción"],
            y=[base, *orden.values, None],
            text=[mil(base)] + [mil(v, "{:+,.0f}") for v in orden.values] + [mil(prediccion)],
            textposition="outside",
            connector={"line": {"color": "#bbb"}},
            increasing={"marker": {"color": ROJO}},
            decreasing={"marker": {"color": AZUL}},
            totals={"marker": {"color": GRIS}},
        )
    )
    return _limpio(fig, 460, yaxis_title="kg/ha", margin={**MARGEN, "t": 30}, title=titulo)


def _doble_eje(
    x, y1, y2, nombre1: str, nombre2: str, titulo_y1: str, titulo_y2: str,
    titulo_x: str, alto: int, color2: str,
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y1, mode="lines+markers", name=nombre1,
                             line={"color": AZUL}))
    fig.add_trace(go.Scatter(x=x, y=y2, mode="lines", name=nombre2, yaxis="y2",
                             line={"color": color2, "dash": "dot"}))
    return _limpio(
        fig, alto, xaxis_title=titulo_x, yaxis_title=titulo_y1,
        yaxis2={"title": titulo_y2, "overlaying": "y", "side": "right", "showgrid": False},
        legend={"orientation": "h", "y": 1.12},
    )


def serie_del_modulo(serie: pd.DataFrame, semana_marcada: int) -> go.Figure:
    fig = _doble_eje(
        serie.nsem, serie.KgHa, serie.riego_lt_planta, "kg/ha", "riego (L/planta)",
        "kg/ha", "riego (L/planta)", "semana", 380, VERDE,
    )
    fig.add_vline(x=semana_marcada, line_dash="dash", line_color=ROJO)
    return fig


def serie_semanal(sem: pd.DataFrame, col: str) -> go.Figure:
    return _doble_eje(
        sem.nsem, sem.kg_ha, sem[col], "kg/ha del fundo", etiqueta(col),
        "kg/ha del fundo", etiqueta(col), "semana de 2025", 420, ROJO,
    )


def mapa_por_modulo(porm: pd.DataFrame, columnas: list[str]) -> go.Figure:
    fig = px.imshow(
        porm[columnas].values, x=columnas, y=porm["Módulo"].tolist(),
        color_continuous_scale=DIVERGENTE, zmin=-1, zmax=1,
        text_auto=".2f", aspect="auto", labels={"color": "correlación"},
    )
    return _limpio(fig, max(420, 26 * len(porm)), margin={**MARGEN, "t": 30})


def ventana_de_cosecha(porm: pd.DataFrame) -> go.Figure:
    """Correlación de cada módulo contra dónde arranca su cosecha.

    Es el gráfico que revela que el signo de la correlación lo fija la ventana de cosecha.
    """
    col = ETIQUETAS["TempMin"]
    fig = px.scatter(
        porm, x="Inicio", y=col, size="Semanas", color=col,
        color_continuous_scale=DIVERGENTE, range_color=[-1, 1],
        hover_name="Módulo", hover_data=["Pico", "kg/ha medio"],
        labels={"Inicio": "primera semana con cosecha",
                col: "correlación Temp. mín ↔ kg/ha"},
    )
    fig.add_hline(y=0, line_dash="dash", line_color="#888")
    return _limpio(fig, 440)


def reparto_varianza(pct_entre: float, pct_dentro: float) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=[pct_entre, pct_dentro], y=["variación del kg/ha"] * 2, orientation="h",
            text=[f"entre semanas · {pct_entre:.0f}%", f"entre módulos · {pct_dentro:.0f}%"],
            textposition="inside", marker={"color": [AZUL, NARANJA]},
            hovertemplate="%{text}<extra></extra>",
        )
    )
    return _limpio(fig, 170, barmode="stack", showlegend=False,
                   xaxis_title="% de la varianza total del kg/ha")

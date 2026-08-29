"""Figuras de la página. Cada una responde una pregunta que la tabla no responde sola."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .analisis import Barrido
from .formato import nombre_objetivo, nombre_variable
from .textos import BLOQUES_GRAFICO

# Divergente centrada en cero: el signo de una correlación importa tanto como su tamaño, y
# una escala secuencial lo esconde.
ESCALA_CORRELACION = [
    [0.0, "#b45309"],
    [0.35, "#fcd9a4"],
    [0.5, "#f8fafc"],
    [0.65, "#a7d8d2"],
    [1.0, "#0f766e"],
]

PLANTILLA = {
    "template": "plotly_white",
    "margin": {"l": 10, "r": 20, "t": 10, "b": 45},
}


def _vacia(alto: int = 160) -> go.Figure:
    return go.Figure().update_layout(template="plotly_white", height=alto)


def mapa_matriz(matriz: pd.DataFrame) -> go.Figure:
    """Todo contra todo, de un vistazo: qué cruces sobrevivieron y con qué signo.

    Solo se pinta el desfase de mayor efecto de cada par superviviente. Las celdas vacías
    son cruces que se probaron y no pasaron los filtros — que es información, no un hueco.
    """
    vivos = matriz[matriz.sobrevive].copy() if "sobrevive" in matriz else pd.DataFrame()
    if vivos.empty:
        return _vacia()
    vivos["magnitud"] = vivos.correlacion_parcial.abs()
    mejores = vivos.sort_values("magnitud").groupby(["predictor", "respuesta"]).tail(1)
    tabla = mejores.pivot_table(
        index="predictor", columns="respuesta", values="correlacion_parcial", aggfunc="first"
    )
    # Se ordenan las filas por el efecto más fuerte de cada predictor: así lo que importa
    # queda arriba y no disperso por el orden alfabético.
    tabla = tabla.reindex(tabla.abs().max(axis=1).sort_values().index)
    desfases = mejores.pivot_table(
        index="predictor", columns="respuesta", values="rezago_semanas", aggfunc="first"
    ).reindex(index=tabla.index, columns=tabla.columns)
    semanas = mejores.pivot_table(
        index="predictor", columns="respuesta", values="n_efectivo", aggfunc="first"
    ).reindex(index=tabla.index, columns=tabla.columns)

    figura = go.Figure(
        go.Heatmap(
            z=tabla.values,
            x=[nombre_objetivo(c) for c in tabla.columns],
            y=[nombre_variable(i) for i in tabla.index],
            colorscale=ESCALA_CORRELACION,
            zmid=0,
            zmin=-0.7,
            zmax=0.7,
            xgap=3,
            ygap=3,
            customdata=[
                [[d, s] for d, s in zip(fd, fs, strict=True)]
                for fd, fs in zip(desfases.values, semanas.values, strict=True)
            ],
            hovertemplate="%{y} → %{x}<br>correlación: %{z:+.2f}<br>"
            "desfase: %{customdata[0]:.0f} sem · muestra: %{customdata[1]:.0f} sem"
            "<extra></extra>",
            colorbar={
                "title": {"text": "correlación", "side": "right"},
                "thickness": 12,
                "len": 0.7,
                "tickvals": [-0.6, -0.3, 0, 0.3, 0.6],
            },
        )
    )
    figura.update_layout(
        **PLANTILLA,
        height=180 + 26 * len(tabla),
        xaxis={"side": "top", "tickangle": -30},
        yaxis={"autorange": True},
    )
    return figura


def perfil_desfases(matriz: pd.DataFrame, maximo: int = 6) -> go.Figure:
    """Cómo cambia cada relación al mover el desfase.

    Es la comprobación visual de que un hallazgo no es un accidente: una relación real sube,
    llega a un pico y baja. Una que salta de signo entre semanas contiguas es ruido, por muy
    alto que sea su mejor coeficiente.
    """
    if matriz.empty or "sobrevive" not in matriz:
        return _vacia()
    vivos = matriz[matriz.sobrevive]
    if vivos.empty:
        return _vacia()
    fuertes = (
        vivos.assign(magnitud=vivos.correlacion_parcial.abs())
        .groupby(["predictor", "respuesta"])
        .magnitud.max()
        .sort_values(ascending=False)
        .head(maximo)
        .index
    )
    colores = ["#0f766e", "#b45309", "#7c3aed", "#be123c", "#0369a1", "#4d7c0f"]
    figura = go.Figure()
    for color, (predictor, respuesta) in zip(colores, fuertes, strict=False):
        serie = matriz[
            (matriz.predictor == predictor) & (matriz.respuesta == respuesta)
        ].sort_values("rezago_semanas")
        nombre = f"{nombre_variable(predictor)} → {nombre_objetivo(respuesta)}"
        figura.add_trace(
            go.Scatter(
                x=serie.rezago_semanas,
                y=serie.correlacion_parcial,
                name=nombre,
                mode="lines+markers",
                line={"color": color, "width": 2},
                marker={"size": [9 if s else 5 for s in serie.sobrevive], "line": {"width": 0}},
                hovertemplate=nombre + "<br>desfase %{x:.0f} sem: %{y:+.2f}<extra></extra>",
            )
        )
    figura.add_hline(y=0, line_dash="dot", line_color="#94a3b8")
    figura.update_layout(
        **PLANTILLA,
        height=430,
        xaxis_title="Semanas de desfase entre la señal y el resultado",
        yaxis_title="Correlación (descontado calendario y módulo)",
        legend={"orientation": "h", "y": -0.26, "x": 0, "font": {"size": 11}},
    )
    return figura


def embudo_filtrado(barrido: Barrido) -> go.Figure:
    """Cuánto se cae en cada filtro. Sin esto no se puede juzgar cuánto filtro hubo."""
    if not barrido.hay_datos:
        return _vacia()
    etapas = [
        ("Cruces probados", barrido.pruebas, "#cbd5e1"),
        ("Con señal aparente", barrido.sin_corregir, "#94a3b8"),
        ("Sobreviven al placebo", barrido.tras_placebo, "#5eaaa0"),
        ("Sobreviven a la corrección", barrido.supervivientes, "#0f766e"),
    ]
    figura = go.Figure(
        go.Bar(
            x=[v for _, v, _ in etapas],
            y=[n for n, _, _ in etapas],
            orientation="h",
            marker_color=[c for _, _, c in etapas],
            text=[f"{v:,}".replace(",", ".") for _, v, _ in etapas],
            textposition="auto",
            hovertemplate="%{y}: %{x:,.0f}<extra></extra>",
        )
    )
    # La línea de azar es la referencia que convierte el recuento en un juicio.
    figura.add_vline(
        x=barrido.esperados_por_azar,
        line_dash="dash",
        line_color="#be123c",
        annotation_text=f"  {barrido.esperados_por_azar} esperados por azar",
        annotation_position="top",
        annotation_font_color="#be123c",
    )
    # El margen común deja 10 px arriba y la anotación de la línea se corta por la mitad.
    figura.update_layout(
        **{**PLANTILLA, "margin": {**PLANTILLA["margin"], "t": 34}},
        height=320,
        xaxis_title="Número de cruces",
        yaxis={"autorange": "reversed"},
        showlegend=False,
    )
    return figura


def _barras_efecto(hallazgos, respuestas, unidad, escala, color) -> go.Figure | None:
    """Efectos en la unidad real de la respuesta, ordenados por magnitud.

    Se grafica el efecto y no la correlación porque dos relaciones con el mismo coeficiente
    pueden valer 5 kg o 500 kg, y esa diferencia —no el coeficiente— es la que dice si vale
    la pena mirarla.
    """
    vista = hallazgos[
        hallazgos.respuesta.isin(respuestas) & hallazgos.efecto_rango_iqr.notna()
    ].copy()
    if vista.empty:
        return None
    vista["valor"] = vista.efecto_rango_iqr * escala
    vista = vista.reindex(vista.valor.abs().sort_values().index).tail(10)
    vista["etiqueta_y"] = [
        nombre_variable(p)
        if len(respuestas) == 1
        else f"{nombre_variable(p)} → {nombre_objetivo(r)}"
        for p, r in zip(vista.predictor, vista.respuesta, strict=True)
    ]
    figura = go.Figure(
        go.Bar(
            x=vista.valor,
            y=vista.etiqueta_y,
            orientation="h",
            marker_color=[color if v > 0 else "#94a3b8" for v in vista.valor],
            customdata=list(zip(vista.n_efectivo, vista.rezago_semanas, strict=True)),
            hovertemplate="%{y}<br>%{x:+.2f} "
            + unidad
            + "<br>%{customdata[0]:.0f} semanas · desfase %{customdata[1]:.0f}<extra></extra>",
        )
    )
    figura.add_vline(x=0, line_dash="dot", line_color="#94a3b8")
    figura.update_layout(
        **PLANTILLA,
        height=110 + 32 * len(vista),
        showlegend=False,
        xaxis_title=f"Diferencia en {unidad}, de un cuarto bajo a un cuarto alto",
    )
    return figura


def efectos_por_unidad(hallazgos: pd.DataFrame):
    """Un gráfico por unidad. Rinde `(titulo, explicacion, figura)`."""
    if hallazgos.empty:
        return
    for respuestas, unidad, escala, color, titulo, explicacion in BLOQUES_GRAFICO:
        figura = _barras_efecto(hallazgos, respuestas, unidad, escala, color)
        if figura is not None:
            yield titulo, explicacion, figura


def importancia(vista: pd.DataFrame) -> go.Figure:
    figura = go.Figure(
        go.Bar(
            x=vista.aumento_mae,
            y=vista.nombre,
            orientation="h",
            error_x={
                "type": "data",
                "symmetric": False,
                "array": vista.ic_superior - vista.aumento_mae,
                "arrayminus": vista.aumento_mae - vista.ic_inferior,
            },
            marker_color=["#0f766e" if a else "#cbd5e1" for a in vista.aporta],
            hovertemplate="%{y}: %{x:,.0f} kg<extra></extra>",
        )
    )
    figura.add_vline(x=0, line_dash="dot", line_color="#94a3b8")
    figura.update_layout(
        **PLANTILLA,
        height=90 + 55 * len(vista),
        showlegend=False,
        xaxis_title="Kilos de error que se añaden al perder ese grupo",
    )
    return figura

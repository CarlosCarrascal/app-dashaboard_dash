"""Piezas de interfaz reutilizables — puerto de `dashboard/vistas/comun.py` a Dash.

Misma regla que en el Streamlit: nada se muestra sin decir cómo se lee. Por eso existen
`como_leer`, `semaforo` y `glosario` acá también, con la misma firma que sus equivalentes
Streamlit para que portar una vista sea sobre todo un cambio de `st.xxx` por `ui.xxx`.

Sin dash-bootstrap-components ni librería de iconos: `html.Details`/`html.Summary` (HTML
nativo) dan el plegado de `como_leer`/`glosario` sin JS, y las clases son Tailwind puro.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
from dash import dcc, html

from config import GLOSARIO, etiqueta, glosa

# ── Formato ──────────────────────────────────────────────────────────────────


def miles(v: float, formato: str = "{:,.0f}") -> str:
    """Número con punto como separador de miles, que es lo que se usa en el fundo."""
    return formato.format(v).replace(",", "@").replace(".", ",").replace("@", ".")


def entero(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


# ── Semáforo / veredicto ─────────────────────────────────────────────────────

_SEMAFORO_ESTILO = {
    "ok": ("bg-emerald-50 border-emerald-300 text-emerald-900", "check_circle", "text-emerald-600"),
    "aviso": ("bg-amber-50 border-amber-300 text-amber-900", "warning", "text-amber-600"),
    "error": ("bg-rose-50 border-rose-300 text-rose-900", "dangerous", "text-rose-600"),
    "info": ("bg-sky-50 border-sky-300 text-sky-900", "info", "text-sky-600"),
}
_SEMAFORO_SIMBOLO = {"ok": "✓", "aviso": "⚠", "error": "✕", "info": "ℹ"}


def semaforo(estado: str, mensaje: str) -> html.Div:
    """Conclusión con color: verde confirma, ámbar matiza, rojo desmiente."""
    clases, _, color_texto = _SEMAFORO_ESTILO.get(estado, _SEMAFORO_ESTILO["info"])
    return html.Div(
        className=f"flex gap-3 rounded-2xl border p-4 {clases}",
        children=[
            html.Span(
                _SEMAFORO_SIMBOLO.get(estado, "ℹ"),
                className=f"flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/70 text-sm font-bold {color_texto}",
            ),
            dcc.Markdown(mensaje, className="prose prose-sm max-w-none"),
        ],
    )


def como_leer(texto: str, titulo: str = "Cómo se lee este gráfico") -> html.Details:
    """Instrucción de lectura, plegada por omisión para no competir con el dato."""
    return html.Details(
        className="group rounded-2xl border border-slate-200 bg-slate-50 p-3 open:bg-white open:shadow-sm",
        children=[
            html.Summary(
                f"ℹ  {titulo}",
                className="cursor-pointer select-none text-sm font-medium text-slate-600",
            ),
            html.Div(
                dcc.Markdown(texto, className="prose prose-sm max-w-none"),
                className="mt-2",
            ),
        ],
    )


def veredicto_de_prueba(pregunta: str, respuesta: str, estado: str, evidencia: str) -> html.Div:
    """Una prueba estadística presentada como pregunta, respuesta y evidencia."""
    return html.Div(
        className="space-y-2",
        children=[
            dcc.Markdown(f"**{pregunta}**"),
            semaforo(estado, respuesta),
            como_leer(evidencia, "La evidencia detrás de esta respuesta"),
        ],
    )


def glosario(claves: Iterable[str] | None = None, titulo: str = "Glosario") -> html.Details:
    """Despliega qué significa cada variable, en lenguaje llano."""
    claves = list(claves) if claves is not None else list(GLOSARIO)
    filas = []
    for c in claves:
        texto = glosa(c)
        if texto:
            filas.append(dcc.Markdown(f"**{etiqueta(c)}** — {texto}", className="text-sm"))
    return html.Details(
        className="group rounded-2xl border border-slate-200 bg-slate-50 p-3 open:bg-white open:shadow-sm",
        children=[
            html.Summary(
                f"ℹ  {titulo}",
                className="cursor-pointer select-none text-sm font-medium text-slate-600",
            ),
            html.Div(filas, className="mt-2 space-y-1"),
        ],
    )


def escala_correlacion() -> html.P:
    """Recordatorio de qué significa un r, para quien no lee correlaciones a diario."""
    return dcc.Markdown(
        "**Cómo leer un coeficiente de correlación (r):** va de −1 a +1. "
        "Cerca de **0** no hay relación lineal. **Positivo** = cuando una sube, la otra "
        "tiende a subir. **Negativo** = cuando una sube, la otra tiende a bajar. "
        "Por encima de **|0,5|** se considera una asociación fuerte — lo que no significa "
        "que una cause la otra.",
        className="text-xs text-slate-500",
    )


# ── Tarjetas de métricas ──────────────────────────────────────────────────────


def tarjetas(items: list[tuple[str, str, str | None]]) -> html.Div:
    """Fila de métricas con su ayuda. Cada item es (rótulo, valor, ayuda)."""
    return html.Div(
        className="grid gap-3",
        style={"gridTemplateColumns": f"repeat({len(items)}, minmax(0, 1fr))"},
        children=[
            html.Div(
                className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md",
                title=ayuda or "",
                children=[
                    html.Div(rotulo, className="text-xs font-medium uppercase tracking-wide text-slate-400"),
                    html.Div(valor, className="mt-2 font-mono text-2xl font-semibold tabular-nums text-slate-900"),
                ],
            )
            for rotulo, valor, ayuda in items
        ],
    )


# ── Estructura de sección ─────────────────────────────────────────────────────


def titulo_seccion(texto: str, nivel: str = "h3") -> html.H3 | html.H2:
    Tag = getattr(html, nivel.capitalize())
    return Tag(texto, className="mt-6 text-lg font-semibold text-slate-900 first:mt-0")


def parrafo(texto: str) -> dcc.Markdown:
    return dcc.Markdown(texto, className="prose prose-slate max-w-none text-[0.95rem]")


def caja(*children, className: str = "") -> html.Div:
    """Contenedor con borde, equivalente a `st.container(border=True)`."""
    return html.Div(children=list(children), className=f"rounded-2xl border border-slate-200 bg-white p-4 shadow-sm {className}")


def tabla_desde_df(
    df: pd.DataFrame, formato: dict[str, str] | None = None, ocultar: Iterable[str] = ()
) -> html.Div:
    """Tabla HTML simple a partir de un DataFrame.

    Sin gradiente de color ni ordenamiento — para eso el gráfico de arriba ya hace el
    trabajo visual. Para tablas grandes (cientos de filas) usar `dash_ag_grid` en su
    lugar, no esto (ver `pages/datos_calidad.py`).
    """
    formato = formato or {}
    columnas = [c for c in df.columns if c not in set(ocultar)]

    def _fmt(col: str, v) -> str:
        f = formato.get(col)
        if f is None:
            return str(v)
        try:
            return f.format(v)
        except (ValueError, TypeError):
            return str(v)

    return html.Div(
        className="overflow-x-auto rounded-2xl border border-slate-200 shadow-sm",
        children=html.Table(
            className="w-full min-w-max text-left text-sm",
            children=[
                html.Thead(html.Tr([
                    html.Th(
                        c,
                        className="whitespace-nowrap border-b border-slate-200 bg-slate-50 py-2.5 px-3 "
                        "text-xs font-semibold uppercase tracking-wide text-slate-400",
                    )
                    for c in columnas
                ])),
                html.Tbody([
                    html.Tr([
                        html.Td(_fmt(c, fila[c]), className="whitespace-nowrap border-b border-slate-100 py-1.5 px-3")
                        for c in columnas
                    ])
                    for _, fila in df.iterrows()
                ]),
            ],
        ),
    )


def pendiente_de_migrar(pagina_streamlit: str, alcance: str) -> html.Div:
    """Aviso estándar para las páginas todavía no portadas del Streamlit.

    Deja explícito qué vista de `db/tools/dashboard/vistas/` reemplaza y qué contenido
    va a tener, para que la migración de esta sección sea un trabajo acotado y no una
    exploración desde cero.
    """
    return html.Div(
        className="space-y-3",
        children=[
            semaforo(
                "aviso",
                f"**Migración pendiente.** El contenido de esta sección todavía vive en "
                f"`db/tools/dashboard/vistas/{pagina_streamlit}` (Streamlit). El cálculo ya "
                "existe y es reutilizable — falta portar la interfaz.",
            ),
            parrafo(alcance),
        ],
    )

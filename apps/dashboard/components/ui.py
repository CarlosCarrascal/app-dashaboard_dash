"""Piezas de interfaz reutilizables del dashboard Dash.

Misma regla que en el Streamlit: nada se muestra sin decir cómo se lee. Por eso existen
`como_leer`, `semaforo` y `glosario` acá también, con la misma firma que sus equivalentes
Streamlit para que portar una vista sea sobre todo un cambio de `st.xxx` por `ui.xxx`.

Sin dash-bootstrap-components ni librería de iconos: `html.Details`/`html.Summary` (HTML
nativo) dan el plegado de `como_leer`/`glosario` sin JS, y las clases son Tailwind puro.
Los iconos son SVG propios (`assets/icons/`) recoloreados por CSS — nunca emojis.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
from dash import dcc, html

from analitica.config import GLOSARIO, etiqueta, glosa

# ── Iconos ────────────────────────────────────────────────────────────────────


def icono(nombre: str, className: str = "h-4 w-4") -> html.Span:
    """Ícono SVG recoloreable por `currentColor`, sin librería ni etiqueta `<img>`.

    Misma técnica que el sidebar (`components/layout._icono`): el SVG de `assets/icons/`
    es una máscara CSS sobre un span con `bg-current`, así el color lo fija la clase
    `text-...` que se pase (o herede) y un mismo archivo sirve en cualquier color y tamaño.
    La URL va por `style`, no por una clase `[mask-image:url(...)]`: el escaneo de Tailwind
    es estático y no vería un nombre de archivo interpolado en un f-string.
    """
    ruta = f"url(/assets/icons/{nombre}.svg)"
    return html.Span(
        className=f"inline-block shrink-0 bg-current {className}",
        style={
            "maskImage": ruta,
            "WebkitMaskImage": ruta,
            "maskRepeat": "no-repeat",
            "WebkitMaskRepeat": "no-repeat",
            "maskPosition": "center",
            "WebkitMaskPosition": "center",
            "maskSize": "contain",
            "WebkitMaskSize": "contain",
        },
    )


# ── Vocabulario visual ────────────────────────────────────────────────────────
#
# Tres decisiones de estilo que se repiten en todo el tablero, nombradas acá una sola vez
# para que una página no invente su propia variante: el rótulo en mayúsculas espaciadas
# (identifica de qué es el número, sin competir con él), el número en monoespaciado con
# cifras tabulares (así una columna de valores queda alineada por dígito), y el borde
# cálido tenue (`stone` en lugar de `slate`) que separa sin dibujar una caja pesada.

ROTULO = "text-[0.7rem] font-medium uppercase tracking-[0.12em] text-slate-400"
CIFRA = "font-mono font-semibold tabular-nums tracking-tight text-slate-900"
BORDE = "border-stone-200/80"

# Título de una sección dentro de una card: negrita gris, sin mayúsculas. Es deliberadamente
# más discreto que `ROTULO` — el rótulo identifica un número suelto, esto encabeza un bloque
# de texto y no debe competir con él.
SUBTITULO = "text-sm font-semibold text-slate-500"

# Fondo de las cabeceras de sección. `stone-50` de Tailwind es exactamente #FAFAF9, así que
# se usa la clase en lugar de un valor arbitrario.
CABECERA = "bg-stone-50"


# ── Formato ──────────────────────────────────────────────────────────────────


def miles(v: float, formato: str = "{:,.0f}") -> str:
    """Número con punto como separador de miles, que es lo que se usa en el fundo."""
    return formato.format(v).replace(",", "@").replace(".", ",").replace("@", ".")


def entero(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


# ── Semáforo / veredicto ─────────────────────────────────────────────────────

_SEMAFORO_ESTILO = {
    "ok": ("bg-emerald-50 border-emerald-200 text-emerald-900", "check-circle", "text-emerald-600"),
    "aviso": ("bg-amber-50 border-amber-200 text-amber-900", "warning", "text-amber-600"),
    "error": ("bg-rose-50 border-rose-200 text-rose-900", "x-circle", "text-rose-600"),
    "info": ("bg-sky-50 border-sky-200 text-sky-900", "info", "text-sky-600"),
}


def semaforo(estado: str, mensaje: str) -> html.Div:
    """Conclusión con color: verde confirma, ámbar matiza, rojo desmiente."""
    clases, nombre_icono, color_texto = _SEMAFORO_ESTILO.get(estado, _SEMAFORO_ESTILO["info"])
    return html.Div(
        className=f"flex gap-3 rounded-2xl border p-4 {clases}",
        children=[
            html.Span(
                icono(nombre_icono, "h-5 w-5"),
                className=f"flex h-6 w-6 shrink-0 items-center justify-center {color_texto}",
            ),
            dcc.Markdown(mensaje, className="prose prose-sm max-w-none"),
        ],
    )


def _summary_plegable(titulo: str) -> html.Summary:
    """Cabecera de un `<details>`: ícono de info + título + chevron que gira al abrir."""
    return html.Summary(
        className="flex cursor-pointer select-none items-center gap-2 text-sm font-medium text-slate-600",
        children=[
            icono("info", "h-4 w-4 text-slate-400"),
            html.Span(titulo),
            icono("chevron-down", "ml-auto h-4 w-4 text-slate-400 transition-transform group-open:rotate-180"),
        ],
    )


def como_leer(texto: str, titulo: str = "Cómo se lee este gráfico") -> html.Details:
    """Instrucción de lectura, plegada por omisión para no competir con el dato."""
    return html.Details(
        className="group rounded-2xl border border-slate-200 bg-slate-50 p-3 open:bg-white open:shadow-sm",
        children=[
            _summary_plegable(titulo),
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


def glosario(claves: Iterable[str] | None = None, titulo: str = "Glosario",
             plano: bool = False) -> html.Details | html.Dl:
    """Qué significa cada variable, en lenguaje llano.

    Como lista de definiciones (`<dl>`) en dos columnas: el término en su propia línea y la
    glosa debajo, sin el guion largo que antes los unía — con el término ya en negrita el
    separador no aportaba nada y ensuciaba el arranque de cada definición.

    `plano=True` devuelve solo la lista, sin el `<details>` ni su marco, para cuando ya va
    dentro de un `panel` que aporta el título y el borde (si no, es card sobre card).
    """
    claves = list(claves) if claves is not None else list(GLOSARIO)
    filas = []
    for c in claves:
        texto = glosa(c)
        if texto:
            filas.append(html.Div([
                html.Dt(etiqueta(c), className="text-sm font-medium text-slate-900"),
                html.Dd(texto, className="mt-0.5 text-sm leading-snug text-slate-500"),
            ]))
    # Una sola columna: en dos, la vista se lee en zigzag y los términos de la columna
    # derecha quedan sueltos de la definición que les corresponde a la izquierda.
    cuerpo = html.Dl(filas, className="divide-y divide-stone-200/80 [&>div]:py-2.5 [&>div:first-child]:pt-0 [&>div:last-child]:pb-0")
    if plano:
        return cuerpo
    return html.Details(
        className="group rounded-2xl border border-slate-200 bg-slate-50 p-3 open:bg-white open:shadow-sm",
        children=[_summary_plegable(titulo), html.Div(cuerpo, className="mt-2")],
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


def encabezado_pagina(titulo: str, entrada: str | None = None) -> html.Div:
    """Título de página grande, con una frase de entrada opcional debajo.

    Va después de la migaja de ruta y antes de los KPIs: la migaja dice *dónde estás*, el
    título dice *qué es esto*. Sin borde ni fondo — el aire lo separa del contenido.
    """
    hijos = [html.H1(titulo, className="text-2xl font-semibold tracking-tight text-slate-900")]
    if entrada:
        hijos.append(html.P(entrada, className="mt-1 text-sm text-slate-500"))
    return html.Div(hijos, className="mb-5")


def _barras(serie: Iterable[float], className: str = "h-8 w-24") -> html.Div:
    """Mini-gráfico de barras sin librería: un `div` por valor, alto proporcional.

    Se usa dentro de un KPI para dar la forma de la serie junto al número, no para leer
    valores — por eso no lleva eje, ni tooltip, ni etiquetas. Con `plotly` costaría una
    figura y un callback por tarjeta; con divs son cero peticiones y cero JS.

    La altura mínima es 8 % para que un valor de cero siga dibujando una marca visible
    (una barra de alto 0 desaparece y hace ver la serie más corta de lo que es).
    """
    valores = [v for v in serie if pd.notna(v)]
    if not valores:
        return html.Div(className=className)
    techo = max(valores) or 1
    # Con muchas barras el separador de 1 px se come más ancho que las barras mismas (50
    # semanas en 6 rem dejarían ~1 px de barra y ~1 px de hueco), así que a partir de ahí
    # se pegan y la serie se lee como una trama continua.
    separacion = "gap-px" if len(valores) <= 24 else "gap-0"
    return html.Div(
        className=f"flex items-end {separacion} {className}",
        children=[
            html.Div(
                className="flex-1 rounded-sm bg-slate-200",
                style={"height": f"{max(8, round(100 * v / techo))}%"},
            )
            for v in valores
        ],
    )


def kpi(rotulo: str, valor: str, nota: str | None = None, serie: Iterable[float] | None = None,
        ayuda: str | None = None, plano: bool = False) -> html.Div:
    """Tarjeta de un solo número: rótulo arriba, cifra grande, forma de la serie al lado.

    `nota` va bajo una línea divisoria fina, como el pie de las tarjetas de referencia.
    Ahí va contexto verificable (el rango observado, de qué se compone el número) — no un
    porcentaje de variación: esta campaña no tiene una anterior con la cual compararse, así
    que un delta sería inventado.

    La unidad no se repite en la cifra: ya está en el rótulo («kg/ha promedio»), y ponerla
    dos veces en la misma tarjeta hace leer el número dos veces para entender uno.

    `plano=True` quita el marco, para los KPI que van dentro de un `panel`.
    """
    hijos = [
        html.Div(rotulo, className=ROTULO),
        html.Div(
            className="mt-2 flex items-end justify-between gap-3",
            children=[
                html.Span(valor, className=f"text-[1.75rem] leading-none {CIFRA}"),
                _barras(serie) if serie is not None else None,
            ],
        ),
    ]
    if nota:
        hijos.append(
            html.Div(nota, className=f"mt-3 border-t {BORDE} pt-2.5 text-xs leading-snug text-slate-400")
        )
    marco = "" if plano else f"min-h-[10.2rem] rounded-xl border {BORDE} bg-white p-4 shadow-[0_0_6px_rgba(0,0,0,0.1)]"
    return html.Div(hijos, className=marco, title=ayuda or "")


def fila_kpi(items: list[html.Div]) -> html.Div:
    """Rejilla de KPIs que se reacomoda en pantallas angostas en lugar de comprimirse."""
    return html.Div(items, className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4")


def panel(titulo: str, *children, ayuda: str | None = None, aside=None,
          plegable: bool = False, abierto: bool = True) -> html.Div | html.Details:
    """Bloque de contenido con cabecera, como el panel «SALES TREND» de la referencia.

    Es **la única card de su sección**: nada de lo que va dentro debe traer su propio borde
    ni su propia sombra, o se ve una card dentro de otra. Los componentes que sí dibujan
    marco (`caja`, `semaforo`, `como_leer`, `glosario`) aceptan `plano=True` justamente para
    poder vivir acá dentro.

    La cabecera es una banda #FAFAF9 separada del cuerpo por una línea fina. `ayuda` va como
    tooltip del título, sin ícono: repetir un ⓘ en cada sección lo convierte en ruido en vez
    de en señal.

    Con `plegable=True` la cabecera pasa a ser el `<summary>` de un `<details>` y gana el
    chevron que gira al abrir — mismo HTML nativo que `como_leer`, sin JS ni callback. Se usa
    para las secciones de consulta (un glosario que no se lee de corrido), no para las que
    llevan la línea argumental de la página.
    """
    cuerpo = html.Div(list(children), className="space-y-4 px-4 pb-4 pt-3")
    marco = f"overflow-hidden rounded-xl border {BORDE} bg-white shadow-[0_0_6px_rgba(0,0,0,0.1)]"
    cabecera = f"flex items-center gap-2 border-b {BORDE} {CABECERA} px-4 py-2.5"

    if not plegable:
        return html.Div(
            className=marco,
            children=[
                html.Div(
                    className=cabecera,
                    children=[
                        html.Span(titulo, className=SUBTITULO, title=ayuda or ""),
                        html.Div(aside, className="ml-auto") if aside is not None else None,
                    ],
                ),
                cuerpo,
            ],
        )

    return html.Details(
        className=f"group {marco}",
        open=abierto,
        children=[
            html.Summary(
                className=f"cursor-pointer select-none {cabecera}",
                title=ayuda or "",
                children=[
                    html.Span(titulo, className=SUBTITULO),
                    icono("chevron-down",
                          "ml-auto h-4 w-4 text-slate-400 transition-transform group-open:rotate-180"),
                ],
            ),
            cuerpo,
        ],
    )


def tarjetas(items: list[tuple[str, str, str | None]]) -> html.Div:
    """Fila de métricas con su ayuda. Cada item es (rótulo, valor, ayuda)."""
    return html.Div(
        className="grid gap-3",
        style={"gridTemplateColumns": f"repeat({len(items)}, minmax(0, 1fr))"},
        children=[
            html.Div(
                className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_0_6px_rgba(0,0,0,0.1)]",
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
    return html.Div(children=list(children), className=f"rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_0_6px_rgba(0,0,0,0.1)] {className}")


def subseccion(titulo: str, *children) -> html.Div:
    """Subdivisión dentro de un `panel`: subtítulo en negrita gris y su contenido debajo.

    Sin ícono, sin color y sin viñetas a propósito. Un check verde y una x roja enfrentados
    parecen un veredicto de calidad («esto está bien / esto está mal») cuando en realidad
    solo delimitan alcance, y las viñetas trocean en lista lo que se lee mejor de corrido.
    El contraste lo hace el subtítulo.
    """
    return html.Div(
        className="space-y-1.5",
        children=[html.Div(titulo, className=SUBTITULO), *children],
    )


def plegable(titulo: str, *children, abierto: bool = False) -> html.Details:
    """Detalle plegable **sin marco**, para usar dentro de un `panel`.

    A diferencia de `como_leer`, no dibuja borde ni fondo: la card ya la pone el panel que lo
    contiene. Lo separa del contenido de arriba una línea fina, así se lee como un pie de
    sección y no como un bloque aparte. HTML nativo (`<details>`), sin JS ni callback.
    """
    return html.Details(
        className=f"group border-t {BORDE} pt-3",
        open=abierto,
        children=[
            html.Summary(
                className="flex cursor-pointer select-none items-center gap-2",
                children=[
                    html.Span(titulo, className=SUBTITULO),
                    icono("chevron-down",
                          "ml-auto h-4 w-4 text-slate-400 transition-transform group-open:rotate-180"),
                ],
            ),
            html.Div(list(children), className="mt-2 space-y-3"),
        ],
    )


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


def contenido_pendiente(seccion: str, alcance: str) -> html.Div:
    """Aviso estándar para una sección cuyo contenido aún requiere definición funcional."""
    return html.Div(
        className="space-y-3",
        children=[
            semaforo(
                "aviso",
                f"**Contenido pendiente.** La sección `{seccion}` aún necesita "
                "definición funcional. El cálculo ya "
                "existe y es reutilizable — falta portar la interfaz.",
            ),
            parrafo(alcance),
        ],
    )

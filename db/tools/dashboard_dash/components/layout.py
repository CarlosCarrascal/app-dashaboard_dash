"""Estructura de la interfaz: barra lateral agrupada por área + contenedor de páginas.

La agrupación no vive en un archivo de configuración aparte: cada página se registra con
`dash.register_page(__name__, ..., grupo="...")` y este módulo arma el menú leyendo
`dash.page_registry`. Agregar una página nueva es una sola línea en su propio archivo, no
dos (acá y en el registro).
"""

from __future__ import annotations

import dash
from dash import Input, Output, callback, dcc, html

from servicios.carga import BOOT_STORE, ORIGEN_STORE, PANEL_STORE

# Orden de los grupos en el menú. Un grupo que no aparece acá se muestra al final, en el
# orden en que Python recorra el registro (no debería pasar: cada página declara el suyo).
ORDEN_GRUPOS = ["General", "Impacto agronómico", "Modelo predictivo", "Referencia"]

# Un ícono propio por página (SVG en `assets/icons/`, sin librería externa). La clave es
# el `path` de `dash.register_page`, que ya es único y estable por página.
ICONOS = {
    "/": "pregunta",
    "/impacto/evidencia": "evidencia",
    "/impacto/por-modulo": "por-modulo",
    "/impacto/frutos-peso": "frutos-peso",
    "/impacto/descubrimientos": "descubrimientos",
    "/modelo/r2": "r2",
    "/modelo/modelo": "modelo",
    "/modelo/explicacion": "explicacion",
    "/datos-calidad": "datos-calidad",
    "/metodologia": "metodologia",
}


def _paginas_por_grupo() -> dict[str, list[dict]]:
    grupos: dict[str, list[dict]] = {}
    for pagina in dash.page_registry.values():
        grupo = pagina.get("grupo", "General")
        grupos.setdefault(grupo, []).append(pagina)
    for lista in grupos.values():
        lista.sort(key=lambda p: p.get("order") or 0)
    return grupos


def _icono(nombre: str) -> html.Span:
    """Ícono como máscara CSS sobre un `div` con color de fondo, no un `<img>`.

    Así el mismo SVG (una sola forma, sin variante clara/oscura) cambia de color con una
    clase Tailwind (`bg-slate-400` inactivo, `bg-white` activo) igual que el resto de la
    interfaz — no hace falta un archivo por estado ni una librería de iconos.

    La URL de la máscara va por `style`, no por una clase `[mask-image:url(...)]`: el
    escaneo de clases de Tailwind es estático (lee el texto del `.py` tal cual, sin
    ejecutarlo), así que una clase armada con un f-string nunca llega a coincidir con el
    nombre real del ícono — Tailwind vería literalmente la variable interpolada, no su
    valor. Confirmado con el CSS compilado antes de este cambio.
    """
    ruta = f"url(/assets/icons/{nombre}.svg)"
    estilo_mascara = {
        "maskImage": ruta,
        "WebkitMaskImage": ruta,
        "maskRepeat": "no-repeat",
        "WebkitMaskRepeat": "no-repeat",
        "maskPosition": "center",
        "WebkitMaskPosition": "center",
        "maskSize": "contain",
        "WebkitMaskSize": "contain",
    }
    return html.Span(
        className="nav-icon-caja flex h-6 w-6 shrink-0 items-center justify-center rounded-md transition-colors",
        children=html.Span(
            className="nav-icon h-3.5 w-3.5 bg-slate-400 transition-colors",
            style=estilo_mascara,
        ),
    )


def _enlace(pagina: dict) -> dcc.Link:
    return dcc.Link(
        [
            _icono(ICONOS.get(pagina["path"], "pregunta")),
            html.Span(pagina["name"]),
        ],
        href=pagina["path"],
        className="nav-link flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-sm text-slate-600 "
        "transition-colors hover:bg-white/70 hover:text-slate-900",
        # El resaltado de la página activa lo hace el clientside_callback de `app.py`:
        # comparar `pathname` en cada navegación no necesita ida y vuelta al servidor por
        # algo puramente visual. Recolorea `.nav-icon`/`.nav-icon-caja` a la vez que el
        # fondo del enlace.
    )


def _barra_lateral() -> html.Nav:
    grupos = _paginas_por_grupo()
    orden = [*ORDEN_GRUPOS, *[g for g in grupos if g not in ORDEN_GRUPOS]]
    secciones = []
    for i, grupo in enumerate(orden):
        paginas = grupos.get(grupo)
        if not paginas:
            continue
        borde = "" if i == 0 else "mt-4 border-t border-stone-200/70 pt-4"
        secciones.append(
            html.Div(
                className=f"mb-1 {borde}",
                children=[
                    html.Div(grupo, className="px-2.5 pb-1 text-xs font-bold text-slate-500"),
                    html.Div([_enlace(p) for p in paginas], className="space-y-0.5"),
                ],
            )
        )
    return html.Nav(
        id="barra-lateral",
        className="flex w-64 shrink-0 flex-col border-r border-stone-200/70 bg-stone-50 px-2 py-4",
        children=[
            html.Div(
                className="flex items-center gap-3 px-2.5 pb-4",
                style={"overflow": "hidden"},
                children=[
                    html.Div(
                        className="flex shrink-0 items-center justify-center rounded-lg",
                        style={"width": "100px", "height": "40px", "backgroundColor": "#000000", "overflow": "hidden"},
                        children=html.Img(
                            src="/assets/aqp_logo.png",
                            style={
                                "width": "100%", 
                                "height": "100%", 
                                "objectFit": "cover", 
                                "objectPosition": "center",
                                "transform": "scale(1.2)"
                            },
                        ),
                    ),
                    html.Div(
                        style={"minWidth": "0", "flex": "1"},
                        children=[
                            html.Div(
                                "Aqu Anqa", 
                                className="text-sm font-bold text-slate-900",
                                style={"whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis"}
                            ),
                            html.Div(
                                "Clima, riego y rendimiento · 2025",
                                className="text-xs text-slate-500",
                                style={"whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis"}
                            ),
                        ],
                    ),
                ],
            ),
            *secciones,
            html.Div(
                id="estado-panel",
                className="mt-auto rounded-xl bg-white px-3 py-3 text-xs leading-relaxed text-slate-400 shadow-sm",
            ),
        ],
    )


def armar() -> html.Div:
    return html.Div(
        className="flex h-screen items-stretch bg-slate-100 p-4",
        children=[
            dcc.Store(id=BOOT_STORE, data=0),
            dcc.Store(id=PANEL_STORE),
            dcc.Store(id=ORIGEN_STORE),
            dcc.Location(id="_url"),
            html.Div(id="_resaltado_nav", style={"display": "none"}),
            html.Div(
                className="flex w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm",
                children=[
                    _barra_lateral(),
                    html.Main(
                        className="flex-1 overflow-y-auto",
                        children=html.Div(
                            [
                                html.Div(id="ruta-actual", className="mb-4 flex items-center gap-1.5 text-sm"),
                                dash.page_container,
                            ],
                            className="mx-auto max-w-5xl px-8 py-8",
                        ),
                    ),
                ],
            ),
        ],
    )


@callback(Output("ruta-actual", "children"), Input("_url", "pathname"))
def _actualizar_ruta(pathname):
    """Migaja de ruta sobre el contenido: grupo actual + nombre de la página, leídos de
    `dash.page_registry` — el mismo dato que ya arma la barra lateral, no uno nuevo."""
    pagina = next((p for p in dash.page_registry.values() if p["path"] == pathname), None)
    if pagina is None:
        return []
    return [
        html.Span(pagina.get("grupo", "General"), className="font-medium text-slate-400"),
        html.Span("›", className="text-slate-300"),
        html.Span(pagina["name"], className="font-semibold text-slate-900"),
    ]

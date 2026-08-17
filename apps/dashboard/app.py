"""Dashboard oficial de análisis de Aqu Anqa.

Reutiliza el paquete analítico independiente `analitica`, que no importa Dash. La interfaz
(`pages/`) y la caché (`servicios/`) viven directamente en esta aplicación.

División de páginas (ver el hilo de diseño): «Impacto agronómico» cuenta la asociación
observada sin mezclar XGBoost/SHAP; «Modelo predictivo» concentra el modelo y su
validación.

Uso:
    npm run dashboard
    python app.py   # desde apps/dashboard
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# Permite ejecutar el archivo desde el checkout; en despliegue se usa el paquete instalado.
if __package__ in (None, ""):
    sys.path.insert(0, str(RAIZ))
    sys.path.insert(1, str(RAIZ.parents[1] / "packages"))

from dash import Input, Output, clientside_callback, html  # noqa: E402
from dash_extensions.enrich import (  # noqa: E402
    DashProxy,
    FileSystemBackend,
    Input as EInput,
    Output as EOutput,
    ServersideOutputTransform,
    callback as ecallback,
)

from components import layout, ui  # noqa: E402
from servicios.carga import ORIGEN_STORE, PANEL_STORE  # noqa: E402

CACHE_DIR = RAIZ / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

backend = FileSystemBackend(cache_dir=str(CACHE_DIR))

app = DashProxy(
    __name__,
    use_pages=True,
    pages_folder=str(RAIZ / "pages"),
    assets_folder=str(RAIZ / "assets"),
    transforms=[ServersideOutputTransform(backends=[backend], default_backend=backend)],
    title="Aqu Anqa · Clima y rendimiento",
    # Cada página registra callbacks sobre IDs que solo existen en ESA página (p. ej.
    # `fp-modulo` de Frutos y peso, `r2-tabs` de Qué explica el R²). Dash valida por
    # defecto que todo ID de callback esté en el layout inicial — con `use_pages=True`
    # eso siempre falla, porque el layout inicial solo monta la página activa. Es el
    # ajuste estándar (y documentado) para apps multipágina, no un parche puntual.
    suppress_callback_exceptions=True,
)
server = app.server
app.layout = layout.armar()


@ecallback(EOutput("estado-panel", "children"), EInput(PANEL_STORE, "data"), EInput(ORIGEN_STORE, "data"))
def _estado_panel(panel, info):
    """Pie de la barra lateral: qué se cargó, igual que `_pie()` en el Streamlit."""
    if info is None:
        return "Cargando…"
    if info.get("error"):
        return html.Div(
            className="flex items-center gap-2 text-amber-600",
            children=[ui.icono("warning", "h-4 w-4"), html.Span(info["error"])],
        )
    extra = []
    if info.get("poda"):
        extra.append("poda")
    if info.get("floracion"):
        extra.append("floración")
    detalle = f" (+{', '.join(extra)})" if extra else ""
    if panel is None:
        return f"{info['nombre']}{detalle}"
    return (
        f"{len(panel.tabla):,}".replace(",", ".") + " celdas · "
        f"{panel.n_modulos} módulos · {panel.n_semanas} semanas\n{info['nombre']}{detalle}"
    )


# Resaltado del enlace activo: puramente visual, así que corre en el navegador con
# `clientside_callback` (0 ms de latencia, 0 peticiones al servidor) — pilar B de la
# arquitectura. No toca `PANEL_STORE`, así que usa el `Output`/`Input` planos de `dash`.
clientside_callback(
    """
    function(pathname) {
        document.querySelectorAll('#barra-lateral a.nav-link').forEach(function (a) {
            const activo = a.getAttribute('href') === pathname
            a.classList.toggle('bg-white', activo)
            a.classList.toggle('shadow-sm', activo)
            a.classList.toggle('text-slate-900', activo)
            a.classList.toggle('font-semibold', activo)
            const caja = a.querySelector('.nav-icon-caja')
            if (caja) caja.classList.toggle('bg-slate-900', activo)
            const icono = a.querySelector('.nav-icon')
            if (icono) {
                icono.classList.toggle('bg-white', activo)
                icono.classList.toggle('bg-slate-400', !activo)
            }
        })
        return window.dash_clientside.no_update
    }
    """,
    Output("_resaltado_nav", "title"),
    Input("_url", "pathname"),
)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=8050)

"""Dashboard oficial de análisis de Aqu Anqa.

Reutiliza el paquete analítico independiente `analitica`, que no importa Dash. La interfaz
(`pages/`) y la caché (`servicios/`) viven directamente en esta aplicación.

División de páginas: «Plataforma analítica» contiene las relaciones, explicaciones,
backtesting y proyecciones oficiales. Las páginas históricas ``/modelo/*`` se conservan
para auditoría, pero Dash no las descubre ni registra salvo que se habiliten explícitamente
con ``AQUANQA_ENABLE_LEGACY_MODEL=true``.

Uso:
    npm run dashboard
    python app.py   # desde apps/dashboard
"""

# ruff: noqa: E402 -- el checkout añade sus paquetes locales antes de importar Dash.

from __future__ import annotations

import os
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
    ServersideOutputTransform,
)
from dash_extensions.enrich import (
    Input as EInput,
)
from dash_extensions.enrich import (
    Output as EOutput,
)
from dash_extensions.enrich import (
    callback as ecallback,
)

from analitica import settings  # noqa: E402
from components import layout, ui  # noqa: E402
from pages.modelo._legacy import legacy_habilitado  # noqa: E402
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

# Dash omite los módulos históricos durante el descubrimiento automático. La importación
# explícita conserva una salida de auditoría reproducible, pero solo se ejecuta cuando la
# persona operadora pide el modo legacy de manera consciente.
if legacy_habilitado():
    from pages.modelo import explicacion as _legacy_explicacion  # noqa: F401,E402
    from pages.modelo import modelo as _legacy_modelo  # noqa: F401,E402
    from pages.modelo import que_explica_r2 as _legacy_r2  # noqa: F401,E402


# Endpoint de readiness para Render/orquestadores: el proceso puede estar vivo aunque
# PostgreSQL no esté disponible, pero eso no debe anunciarse como servicio sano.
@server.route("/health")
def health():
    dsn = settings.postgres_dsn()
    if not dsn:
        return {"status": "degraded", "detail": "PostgreSQL no está configurado"}, 503
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=1) as conexion, conexion.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:
        detalle = f"PostgreSQL no disponible: {type(exc).__name__}"
        return {"status": "degraded", "detail": detalle}, 503
    return {"status": "ok"}, 200


app.layout = layout.armar()


@ecallback(
    EOutput("estado-panel", "children"),
    EInput(PANEL_STORE, "data"),
    EInput(ORIGEN_STORE, "data"),
    EInput("_url", "pathname"),
)
def _estado_panel(panel, info, pathname):
    """Pie de la barra lateral: qué se cargó, igual que `_pie()` en el Streamlit."""
    # Las rutas oficiales no consumen el libro analítico global. Mostrar aquí IA.final.xlsx
    # induciría a pensar que ese archivo alimenta cualquiera de sus resultados.
    if pathname and pathname.startswith("/analitica/"):
        return "Plataforma analítica\nPostgreSQL · datos publicados"
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
        // El valor no se muestra; devolverlo evita que Dash intente resolver `no_update`
        // antes de que el contenedor oculto exista durante una recarga en modo debug.
        return pathname || ''
    }
    """,
    Output("_resaltado_nav", "title"),
    Input("_url", "pathname"),
)


if __name__ == "__main__":
    # El panel de depuración de Dash tapa gráficos y controles en el uso diario.
    # Se habilita solo cuando el desarrollador lo solicita explícitamente.
    debug = os.getenv("DASH_DEBUG", "0").strip().casefold() in {"1", "true", "yes", "on"}
    app.run(debug=debug, host="127.0.0.1", port=8050)

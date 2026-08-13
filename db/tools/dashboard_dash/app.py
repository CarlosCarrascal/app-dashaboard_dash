"""Tablero Dash — sucesor del Streamlit en `db/tools/dashboard/`. Ambos conviven durante
la migración (`npm run dashboard` sigue siendo el Streamlit; `npm run dashboard:dash` es
este).

Reutiliza sin copiar `nucleo/`, `vistas/graficos.py` y `config.py` del Streamlit: ninguno
de los tres importa Streamlit, así que toda la disciplina estadística ya validada
(particiones honestas, SHAP, hallazgos de calidad) se comparte sin reimplementarla. Solo
la capa de interfaz (`vistas/` → `pages/`) y la de caché (`servicios/`) se reescriben.

División de páginas (ver el hilo de diseño): «Impacto agronómico» cuenta la asociación
observada sin mezclar XGBoost/SHAP; «Modelo predictivo» concentra el modelo y su
validación. Antes vivían mezclados en `dashboard/vistas/conclusiones.py`.

Uso:
    npm run dashboard:dash
    python db/tools/dashboard_dash/app.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
STREAMLIT_DIR = RAIZ.parent / "dashboard"

# Tiene que ir antes de cualquier import propio de este archivo: `nucleo` y `config` viven
# en el Streamlit y no se copian acá. Con `append` (no `insert(0, ...)`) a propósito: Python
# ya puso el directorio de este archivo primero en sys.path al ejecutar `python app.py`, y
# tiene que seguir teniendo prioridad — si no, `import servicios` resolvería al `servicios/`
# del Streamlit (que no tiene `carga.py`) en vez del propio de este tablero. Probado: con
# `insert(0, ...)` el arranque falla con `ModuleNotFoundError: servicios.carga`.
sys.path.append(str(STREAMLIT_DIR))


def _cargar_modulo_sibling(nombre: str, ruta: Path):
    """Carga un único archivo del Streamlit como módulo top-level, sin pasar por el
    `__init__.py` de su paquete.

    `vistas/graficos.py` no importa Streamlit (es cálculo puro → `go.Figure`), pero
    `vistas/__init__.py` sí importa todas sus vistas hermanas, que import Streamlit. Un
    `import vistas.graficos` normal ejecutaría ese `__init__.py` igual — esto lo evita.
    """
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    return modulo


_cargar_modulo_sibling("graficos", STREAMLIT_DIR / "vistas" / "graficos.py")

from dash import Input, Output, clientside_callback  # noqa: E402
from dash_extensions.enrich import (  # noqa: E402
    DashProxy,
    FileSystemBackend,
    Input as EInput,
    Output as EOutput,
    ServersideOutputTransform,
    callback as ecallback,
)

from components import layout  # noqa: E402
from servicios.carga import ORIGEN_STORE, PANEL_STORE  # noqa: E402  (registra su callback)

CACHE_DIR = RAIZ / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

backend = FileSystemBackend(cache_dir=str(CACHE_DIR))

app = DashProxy(
    __name__,
    use_pages=True,
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
        return f"⚠ {info['error']}"
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

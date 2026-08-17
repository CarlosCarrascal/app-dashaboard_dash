"""Carga del panel al arrancar el tablero: un único punto de entrada de datos.

A diferencia de `dashboard/servicios/cache.py` (que envuelve cada función de `nucleo/` en
`st.cache_data`), acá solo el paso caro —leer el Excel y armar el panel— se cachea, vía
`Serverside` de `dash-extensions`: el objeto `Panel` se queda en el servidor (backend de
archivos en `.cache/`) y cada página recibe apenas una referencia liviana en `dcc.Store`.
Las funciones de `nucleo/clima.py` son baratas (corren sobre ~50-450 filas) y cada página
las llama directo sobre `panel.tabla`, sin envoltorio de caché propio.

Importante: los callbacks que leen o escriben `PANEL_STORE` deben importar
`Output`/`Input`/`State`/`callback` de `dash_extensions.enrich`, no de `dash`. Es la única
combinación que activa `ServersideOutputTransform` — probado: un callback registrado con
las de `dash` falla con `Serverside is not JSON serializable`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dash_extensions.enrich import Input, Output, Serverside, callback

from analitica import nucleo, settings
from servicios.cache_analisis import panel_key, precargar

PANEL_STORE = "panel-store"
ORIGEN_STORE = "origen-info"
BOOT_STORE = "_boot"

# Mismo valor por omisión que la aplicación anterior (hallado por barrido, ver
# `docs/data/resumen_sesion.md` §10): riego 7 semanas, Rad 3, ETo 2, DPV 6, gdd 7.
LAGS_POR_DEFECTO = {"riego": 7, "Rad": 3, "ETo": 2, "DPV": 6, "gdd": 7}


def _precargar_dashboard(panel) -> None:
    """Usa el tiempo de lectura de la portada para preparar las vistas más costosas."""
    sem = nucleo.clima.agregar_por_semana(panel.tabla)
    precargar(
        panel,
        {
            # Primero Frutos y peso: son las piezas visibles de la página más gráfica.
            "fp:semana": lambda: sem,
            "fp:trayectorias": lambda: nucleo.clima.trayectorias_frutos_peso(panel.tabla),
            "fp:descomposicion": lambda: nucleo.clima.descomponer_frutos_peso(sem),
            "fp:picos": lambda: nucleo.clima.resumen_picos_frutos_peso(panel.tabla),
            "fp:mejor-rezago": lambda: nucleo.clima.mejor_rezago_por_variable(sem, panel.tabla),
            "fp:rezagos": lambda: nucleo.clima.rezagos_todos(sem, panel.tabla),
            # Las pestañas de R² empiezan sin que el usuario tenga que abrirlas.
            "r2:grupos": lambda: nucleo.aporte_por_grupo(panel.tabla),
            "r2:aporte": lambda: nucleo.aporte_por_variable(panel.tabla),
            "r2:esquemas": lambda: nucleo.tabla_validacion(panel.tabla, referencias=()),
            # SHAP global por defecto; las otras metas se calculan solo si se seleccionan.
            "modelo:ajuste:KgHa": lambda: nucleo.entrenar(panel.tabla, objetivo="KgHa"),
        },
    )


def _leer_si_existe(ruta: Path) -> bytes | None:
    return ruta.read_bytes() if ruta.is_file() else None


def _firma_archivo(ruta: Path) -> tuple[str, int | None, int | None]:
    """Firma barata que invalida el panel si cambia cualquiera de los Excel."""
    if not ruta.is_file():
        return str(ruta.resolve()), None, None
    estado = ruta.stat()
    return str(ruta.resolve()), estado.st_mtime_ns, estado.st_size


@lru_cache(maxsize=2)
def _panel_repo_cacheado(
    firma_panel: tuple[str, int | None, int | None],
    firma_poda: tuple[str, int | None, int | None],
    firma_floracion: tuple[str, int | None, int | None],
):
    """Lee y consolida una vez por proceso mientras las fuentes sean las mismas."""
    contenido = _leer_si_existe(Path(firma_panel[0]))
    if contenido is None:
        return None, {"nombre": None, "error": f"No se encontró {firma_panel[0]}"}

    poda_contenido = _leer_si_existe(Path(firma_poda[0]))
    floracion_contenido = _leer_si_existe(Path(firma_floracion[0]))
    panel = nucleo.cargar_panel(
        contenido, LAGS_POR_DEFECTO, poda_contenido, floracion_contenido
    )
    panel_key(panel)
    _precargar_dashboard(panel)
    info = {
        "nombre": Path(firma_panel[0]).name,
        "poda": poda_contenido is not None,
        "floracion": floracion_contenido is not None,
        "error": None,
    }
    return panel, info


@callback(
    Output(PANEL_STORE, "data"),
    Output(ORIGEN_STORE, "data"),
    Input(BOOT_STORE, "data"),
)
def _cargar_panel_inicial(_boot: int):
    """Arma el panel una sola vez, al arrancar la app (dispara con el valor inicial de
    `_boot` en el layout — no hace falta ninguna acción del usuario).

    Usa siempre el Excel del repositorio (o `AQUANQA_XLSX`), igual que el estado por
    omisión del Streamlit. La subida manual de otro archivo (`datos_origen.py` en el
    Streamlit) queda pendiente de portar — ver el aviso en `pages/datos_calidad.py`.
    """
    panel, info = _panel_repo_cacheado(
        _firma_archivo(settings.XLSX_REPO),
        _firma_archivo(settings.PODA_REPO),
        _firma_archivo(settings.FLORACION_REPO),
    )
    if panel is None:
        return None, info
    # Serverside serializa una referencia por sesión, pero el Panel base ya no se vuelve a
    # construir para cada recarga o pestaña del mismo proceso.
    return Serverside(panel), dict(info)

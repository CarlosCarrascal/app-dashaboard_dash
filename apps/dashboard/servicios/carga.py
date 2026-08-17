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

from pathlib import Path

from dash_extensions.enrich import Input, Output, Serverside, callback

from analitica import nucleo, settings

PANEL_STORE = "panel-store"
ORIGEN_STORE = "origen-info"
BOOT_STORE = "_boot"

# Mismo valor por omisión que la aplicación anterior (hallado por barrido, ver
# `docs/data/resumen_sesion.md` §10): riego 7 semanas, Rad 3, ETo 2, DPV 6, gdd 7.
LAGS_POR_DEFECTO = {"riego": 7, "Rad": 3, "ETo": 2, "DPV": 6, "gdd": 7}


def _leer_si_existe(ruta: Path) -> bytes | None:
    return ruta.read_bytes() if ruta.is_file() else None


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
    contenido = _leer_si_existe(settings.XLSX_REPO)
    if contenido is None:
        return None, {"nombre": None, "error": f"No se encontró {settings.XLSX_REPO}"}

    poda_contenido = _leer_si_existe(settings.PODA_REPO)
    floracion_contenido = _leer_si_existe(settings.FLORACION_REPO)
    panel = nucleo.cargar_panel(
        contenido, LAGS_POR_DEFECTO, poda_contenido, floracion_contenido
    )
    info = {
        "nombre": settings.XLSX_REPO.name,
        "poda": poda_contenido is not None,
        "floracion": floracion_contenido is not None,
        "error": None,
    }
    return Serverside(panel), info

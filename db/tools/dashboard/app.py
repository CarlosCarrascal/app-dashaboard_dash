"""Dashboard de relación clima-riego ↔ rendimiento — Aqu Anqa, campaña 2025.

Lee el Excel `IA.final.xlsx`, arma el panel Fundo × Módulo × Semana y separa tres capas:
asociación agronómica observada, aporte predictivo y explicación de XGBoost con SHAP.

Lo que este tablero SÍ hace: cuantifica y ordena asociaciones, y deja auditar celda por
celda de dónde sale cada número.

Lo que NO hace: pronosticar ni estimar todavía un efecto causal. Las secciones «Impacto
agronómico» y «Qué explica el R²» muestran las pruebas y límites de la campaña actual.

Reparto por capas:

    config.py       variables, etiquetas, glosario, hiperparámetros, paleta, secciones
    estilo.py       la hoja de estilo
    datos_origen.py el control que elige qué Excel entra
    nucleo/         cálculo puro — no importa Streamlit ni Plotly
        datos.py        Excel → panel consolidado + hallazgos de calidad
        clima.py        el estudio estadístico: correlación, control, rezagos, placebo
        modelo.py       ajuste XGBoost + SHAP
        evaluacion.py   conjuntos, particiones y plan de validación
        exportar.py     el motor del .xlsx
        informe.py      qué hojas lleva el .xlsx y cómo se explican
    servicios/      la capa de caché sobre `nucleo/`
    vistas/         una sección por módulo, cada una con render()

La dependencia va en un solo sentido: vistas → servicios → nucleo → config, y
`verificar_capas.py` lo comprueba.

Uso:
    npm run dashboard      ·      streamlit run db/tools/dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit ejecuta este archivo por ruta, no como paquete: sin esto los módulos hermanos
# no se resuelven. Misma solución que en el resto de `db/tools`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

import estilo  # noqa: E402
import servicios as sv  # noqa: E402
import vistas  # noqa: E402
from config import FLORACION_REPO, ICONO, PODA_REPO, SECCIONES, XLSX_REPO  # noqa: E402
from datos_origen import elegir_origen  # noqa: E402

st.set_page_config(
    page_title="Aqu Anqa · Clima y rendimiento",
    page_icon=":material/agriculture:",
    layout="wide",
    initial_sidebar_state="expanded",
)
estilo.aplicar()

POR_CLAVE = {s.clave: s for s in SECCIONES}

# El despacho es un diccionario y no una cadena de `if`: agregar una sección es una
# entrada acá y otra en `SECCIONES`. Cada valor recibe (panel, origen) y decide qué usa.
VISTAS = {
    "resumen": lambda p, o: vistas.resumen.render(p),
    "conclusiones": lambda p, o: vistas.conclusiones.render(p),
    "impacto": lambda p, o: vistas.impacto.render(p),
    "r2": lambda p, o: vistas.validacion.render(p),
    "modelo": lambda p, o: vistas.modelo.render(p),
    "explicacion": lambda p, o: vistas.explicacion.render(p),
    "datos": lambda p, o: vistas.datos_calidad.render(p, o),
    "metodologia": lambda p, o: vistas.metodologia.render(p),
}


def _navegacion() -> str:
    """Menú lateral con botones nativos.

    Se usan botones y `session_state` en vez de un radio con CSS: el radio obligaba a
    apuntarle a la estructura interna del widget con selectores frágiles, y el resultado
    dependía de la versión de Streamlit. Acá el resaltado del activo lo hace Streamlit.
    """
    st.markdown("## Aqu Anqa")
    st.caption("Relación clima-riego y rendimiento · campaña 2025")
    st.divider()

    st.session_state.setdefault("seccion", SECCIONES[0].clave)
    for s in SECCIONES:
        activa = st.session_state.seccion == s.clave
        if st.button(
            f"{s.icono}  {s.titulo}",
            key=f"nav_{s.clave}",
            width="stretch",
            type="primary" if activa else "tertiary",
        ):
            st.session_state.seccion = s.clave
            st.rerun()
    return st.session_state.seccion





def _pie(panel, nombre_origen: str) -> None:
    """Estado del panel al pie del menú: qué se cargó y si hay algo que mirar."""
    graves = panel.graves()
    if graves:
        st.error(
            f"**{len(graves)} problema(s) grave(s)** en los datos. El detalle está en "
            "la sección Datos y calidad.",
            icon=ICONO["error"],
        )

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("Celdas", f"{len(panel.tabla):,}".replace(",", "."))
        c2.metric("Módulos", panel.n_modulos)
        c3.metric("Semanas", panel.n_semanas)
        estado = (f"{ICONO['error']} {len(graves)} problema(s) grave(s)" if graves
                  else f"{ICONO['ok']} Sin problemas graves")
        st.caption(f"{estado} · `{Path(nombre_origen).name}`")


def _config_modelo() -> None:
    """Controles que alteran solo las variables predictoras y su explicación."""
    st.caption("Configuración compartida por las secciones del modelo")
    with st.expander(":material/tune:  Ventanas del modelo", expanded=False):
        st.markdown("**Semanas de promedio móvil:**")
        st.caption(
            "Son variables predictivas de calendario. No equivalen todavía a fases "
            "fenológicas; para eso falta alinear cada módulo desde su fecha de poda."
        )

        with st.form("lags_form", border=False):
            if "w_riego" not in st.session_state:
                current = st.session_state.lags_config
                st.session_state.w_riego = max(1, current.get("riego", 1))
                st.session_state.w_rad = max(1, current.get("Rad", 7))
                st.session_state.w_eto = max(1, current.get("ETo", 7))
                st.session_state.w_dpv = max(1, current.get("DPV", 7))
                st.session_state.w_gdd = max(1, current.get("gdd", 7))

            ayuda = "1 = solo la semana actual (dato puro)\n2 = actual + 1 anterior"
            c1, c2 = st.columns(2)
            with c1:
                st.number_input("Riego", 1, 8, key="w_riego", help=ayuda)
                st.number_input("Radiación", 1, 8, key="w_rad", help=ayuda)
                st.number_input("GDD (calor)", 1, 8, key="w_gdd", help=ayuda)
            with c2:
                st.number_input("ETo", 1, 8, key="w_eto", help=ayuda)
                st.number_input("DPV", 1, 8, key="w_dpv", help=ayuda)

            if st.form_submit_button("Aplicar", use_container_width=True):
                st.session_state.lags_config = {
                    "riego": st.session_state.w_riego,
                    "Rad": st.session_state.w_rad,
                    "ETo": st.session_state.w_eto,
                    "DPV": st.session_state.w_dpv,
                    "gdd": st.session_state.w_gdd,
                }


with st.sidebar:
    # Inicializar lags en session_state
    if "lags_config" not in st.session_state:
        st.session_state.lags_config = {"riego": 7, "Rad": 3, "ETo": 2, "DPV": 6, "gdd": 7}

    clave = _navegacion()
    st.divider()

    st.checkbox(
        "Modo presentación (sin alertas)", key="modo_presentacion",
        help="Apaga temporalmente los avisos y errores de calidad de datos, y agrega una "
             "frase simple debajo de los gráficos principales. Pensado para mostrar el "
             "tablero sin las advertencias técnicas — no borra nada, solo lo oculta "
             "mientras el interruptor esté activo.",
    )

    if clave in {"r2", "modelo", "explicacion", "conclusiones"}:
        _config_modelo()

    lags_config = st.session_state.lags_config

    st.divider()
    origen = elegir_origen(XLSX_REPO, sv.leer_archivo)
    poda_contenido = (
        sv.leer_archivo(str(PODA_REPO), PODA_REPO.stat().st_mtime)
        if PODA_REPO.is_file() else None
    )
    if poda_contenido is not None:
        st.caption(f"Poda: {PODA_REPO.name}")
    floracion_contenido = (
        sv.leer_archivo(str(FLORACION_REPO), FLORACION_REPO.stat().st_mtime)
        if FLORACION_REPO.is_file() else None
    )
    if floracion_contenido is not None:
        st.caption(f"Floración: {FLORACION_REPO.name}")

if origen is None:
    st.title("Relación clima-riego y rendimiento")
    st.caption("Campaña 2025 · panel Fundo × Módulo × Semana")
    st.info(
        "Cargá el Excel de la campaña en el menú lateral para empezar.\n\n"
        "**¿Dónde ver cada cosa?**\n"
        "- **Impacto agronómico:** asociación, calendario, rezagos, placebo, módulos, "
        "frutos y peso.\n"
        "- **Qué explica el R²:** aporte predictivo del conjunto, de cada variable y de "
        "cada familia.\n"
        "- **Explicación del modelo:** SHAP y auditoría de una predicción, sin lectura "
        "causal.\n"
        "- **Marco metodológico:** fuentes revisadas y datos faltantes antes de DML.\n",
        icon=ICONO["info"],
    )
    st.stop()

contenido, nombre_origen = origen
try:
    panel = sv.cargar_panel(contenido, lags_config, poda_contenido, floracion_contenido)
except Exception as exc:  # noqa: BLE001 — cualquier fallo de lectura va a la pantalla
    st.error(f"No pude armar el panel: {exc}", icon=ICONO["error"])
    st.stop()

# Interruptor de "Modo presentación": apaga avisos y errores en el resto del render. Los
# originales se guardan UNA sola vez en el propio módulo (sobrevive entre reruns de
# Streamlit, que reejecuta este archivo pero no reimporta `streamlit`) — sin ese guard,
# un rerun con el modo ya activado capturaría el no-op como si fuera el original y no
# habría forma de volver a mostrar las alertas al apagar el interruptor.
if not hasattr(st, "_original_warning"):
    st._original_warning = st.warning
    st._original_error = st.error
if st.session_state.get("modo_presentacion", False):
    st.warning = lambda *a, **k: None
    st.error = lambda *a, **k: None
else:
    st.warning = st._original_warning
    st.error = st._original_error

seccion = POR_CLAVE[clave]
st.title(seccion.titulo)
st.caption(seccion.resumen)
VISTAS[clave](panel, Path(nombre_origen).name)

with st.sidebar:
    _pie(panel, nombre_origen)

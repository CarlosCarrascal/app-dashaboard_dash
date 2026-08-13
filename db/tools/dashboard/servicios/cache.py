"""Capa de caché: envuelve el cálculo puro de `nucleo/` en `st.cache_data`.

Existe para que `nucleo/` no dependa de Streamlit y se pueda ejecutar o probar sin
levantar la app. Todas las funciones reciben argumentos que Streamlit sabe hashear
(bytes, DataFrame, str), nunca los objetos de los registros de `evaluacion`.

Regla de nombres: los parámetros con guion bajo inicial no entran en la clave de caché.
Se usa para objetos caros que ya vienen de otra caché y no se pueden hashear.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from config import FEATURES, OBJETIVO
from nucleo import clima as _cl
from nucleo import datos as _datos
from nucleo import evaluacion as _ev
from nucleo import informe as _informe
from nucleo import modelo as _modelo
from nucleo import sintesis as _sin

# ── Origen y panel ───────────────────────────────────────────────────────────


@st.cache_data(show_spinner=False)
def leer_archivo(ruta: str, _mtime: float) -> bytes:
    """Bytes del Excel del repositorio.

    `_mtime` no se usa dentro pero sí entra en la clave de caché: si el archivo cambia en
    disco, la lectura se rehace. Sin esto, cada interacción del usuario releería medio
    megabyte del disco, porque Streamlit vuelve a ejecutar el script entero.
    """
    return Path(ruta).read_bytes()


@st.cache_data(show_spinner="Leyendo los datos y armando el panel…")
def cargar_panel(
    contenido: bytes, lags_config: dict, poda_contenido: bytes | None = None,
    floracion_contenido: bytes | None = None,
) -> _datos.Panel:
    return _datos.cargar_panel(contenido, lags_config, poda_contenido, floracion_contenido)


@st.cache_data
def diagnostico_ventanas(tabla: pd.DataFrame, lags_config: dict) -> pd.DataFrame:
    return _datos.diagnostico_ventanas(tabla, lags_config)


# ── Modelo ───────────────────────────────────────────────────────────────────

# `cache_resource` y no `cache_data`: el ajuste contiene un modelo de XGBoost, y
# `cache_data` lo serializaría y copiaría en cada acceso (376 KB, ~10 ms por recarga).
# `cache_resource` devuelve siempre la misma instancia. Es seguro porque `Ajuste` se
# trata como de solo lectura: nadie lo muta después de entrenarlo.
@st.cache_resource(show_spinner="Entrenando el modelo…")
def entrenar(
    tabla: pd.DataFrame, features: tuple = _modelo.FEATURES, objetivo: str = OBJETIVO,
) -> _modelo.Ajuste:
    del features
    return _modelo.entrenar(tabla, objetivo=objetivo)


@st.cache_data(show_spinner="Comprobando el reparto SHAP…")
def verificar_consistencia(_ajuste: _modelo.Ajuste, clave: str) -> _modelo.Consistencia:
    del clave
    return _modelo.verificar_consistencia(_ajuste)


# ── Evaluación ───────────────────────────────────────────────────────────────


@st.cache_data(show_spinner="Comparando esquemas de validación…")
def tabla_validacion(tabla: pd.DataFrame) -> pd.DataFrame:
    return _ev.tabla_validacion(tabla)


@st.cache_data(show_spinner="Midiendo el aporte de cada variable…")
def aporte_por_variable(tabla: pd.DataFrame) -> pd.DataFrame:
    return _ev.aporte_por_variable(tabla)


@st.cache_data(show_spinner="Midiendo el aporte de cada familia…")
def aporte_por_grupo(tabla: pd.DataFrame) -> pd.DataFrame:
    return _ev.aporte_por_grupo(tabla)


@st.cache_data(show_spinner="Comparando familias de modelo…")
def comparar_familias(tabla: pd.DataFrame) -> pd.DataFrame:
    return _ev.comparar_familias(tabla)


@st.cache_data
def correlaciones_con_objetivo(
    tabla: pd.DataFrame, metodo: str, variables: tuple = FEATURES
) -> pd.DataFrame:
    return _ev.correlaciones_con_objetivo(tabla, metodo, variables)


@st.cache_data
def descomposicion_varianza(tabla: pd.DataFrame) -> tuple[float, float]:
    return _ev.descomposicion_varianza(tabla)


# ── Estudio del clima ────────────────────────────────────────────────────────


@st.cache_data
def agregar_por_semana(tabla: pd.DataFrame) -> pd.DataFrame:
    return _cl.agregar_por_semana(tabla)


@st.cache_data
def correlaciones_semanales(sem: pd.DataFrame) -> pd.DataFrame:
    return _cl.correlaciones_semanales(sem)


@st.cache_data
def correlacion_parcial(sem: pd.DataFrame) -> pd.DataFrame:
    return _cl.correlacion_parcial(sem)


@st.cache_data
def correlacion_control_poda(sem: pd.DataFrame) -> pd.DataFrame:
    return _cl.correlacion_control_poda(sem)


@st.cache_data
def rezagos(sem: pd.DataFrame, objetivo: str = "kg_ha") -> pd.DataFrame:
    return _cl.rezagos(sem, objetivo)


@st.cache_data
def rezagos_todos(sem: pd.DataFrame, tabla: pd.DataFrame | None = None) -> pd.DataFrame:
    return _cl.rezagos_todos(sem, tabla)


@st.cache_data
def rezago_floracion(tabla: pd.DataFrame, objetivo: str = "Frutos") -> pd.DataFrame:
    return _cl.rezago_floracion(tabla, objetivo)


@st.cache_data
def mejor_rezago_por_variable(
    sem: pd.DataFrame, tabla: pd.DataFrame | None = None,
) -> pd.DataFrame:
    return _cl.mejor_rezago_por_variable(sem, tabla)


@st.cache_data
def placebo(sem: pd.DataFrame) -> pd.DataFrame:
    return _cl.placebo(sem)


@st.cache_data
def ganancia_cuadratica(sem: pd.DataFrame) -> pd.DataFrame:
    return _cl.ganancia_cuadratica(sem)


@st.cache_data
def forma_de_la_relacion(sem: pd.DataFrame, variable: str) -> pd.DataFrame:
    return _cl.forma_de_la_relacion(sem, variable)


@st.cache_data
def por_modulo(tabla: pd.DataFrame) -> pd.DataFrame:
    return _cl.por_modulo(tabla)


@st.cache_data
def signo_depende_de_la_ventana(porm: pd.DataFrame) -> pd.DataFrame:
    return _cl.signo_depende_de_la_ventana(porm)


@st.cache_data
def tamano_efectivo(tabla: pd.DataFrame) -> _cl.TamanoEfectivo:
    return _cl.tamano_efectivo(tabla)


@st.cache_data
def veredicto(sem: pd.DataFrame) -> _cl.Veredicto:
    return _cl.veredicto(sem)


@st.cache_data
def descomponer_frutos_peso(sem: pd.DataFrame) -> pd.DataFrame:
    return _cl.descomponer_frutos_peso(sem)


@st.cache_data
def trayectorias_frutos_peso(tabla: pd.DataFrame) -> pd.DataFrame:
    return _cl.trayectorias_frutos_peso(tabla)


@st.cache_data
def resumen_picos_frutos_peso(tabla: pd.DataFrame) -> pd.DataFrame:
    return _cl.resumen_picos_frutos_peso(tabla)


# ── Síntesis individual + conjunta (kg/ha, Frutos, Peso) ─────────────────────


@st.cache_data(show_spinner="Entrenando el modelo conjunto para kg/ha, Frutos y Peso…")
def aporte_conjunto_por_objetivo(tabla: pd.DataFrame) -> pd.DataFrame:
    return _sin.aporte_conjunto_por_objetivo(tabla)


@st.cache_data(show_spinner="Validando el modelo conjunto fuera de muestra…")
def honesto_por_objetivo(tabla: pd.DataFrame) -> pd.DataFrame:
    return _sin.honesto_por_objetivo(tabla)


# ── Exportación ──────────────────────────────────────────────────────────────


@st.cache_data(show_spinner="Armando el Excel…")
def construir_informe(
    _panel: _datos.Panel, tabla_filtrada: pd.DataFrame,
    incluir: frozenset[str], origen: str, fecha: str,
) -> bytes:
    """El libro exportado. `_panel` no entra en la clave; `tabla_filtrada` sí."""
    return _informe.construir(_panel, tabla_filtrada, set(incluir), origen, fecha)

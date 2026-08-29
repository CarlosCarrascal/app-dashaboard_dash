"""Replay rolling-origin y curva vintage del modelo híbrido.

El replay prepara el panel una sola vez, corta cada emisión en su fecha y une los
resultados reales únicamente después de generar la predicción. Las proyecciones se
comparten desde el motor interno de la familia, evitando depender del servicio y de
la fachada histórica y manteniendo la carga del paquete sin ciclos.
"""

from __future__ import annotations

from hashlib import sha256

import numpy as np
import pandas as pd

from ...nucleo.bhattacharya import ParametrosBhattacharya
from ..compartido.identidad import sha256_dataframe
from ..fenologico.panel import construir_panel_fenologico
from ..versiones import banda_horizonte
from .priors import _campania_defecto, _normalizar_emisiones
from .proyecciones import (
    _legacy_panel,
    proyectar_hibrido_v1,
    proyectar_macro_legacy_v1,
)

_TABLAS_SNAPSHOT = (
    "forecast",
    "forecast_campania",
    "cosecha",
    "poda",
    "flores",
    "estados",
    "bayas",
    "brotes",
    "ramas",
    "packing",
    "clima",
    "riego",
    "lotes",
)


def _firma_snapshot(datos) -> tuple[tuple[str, str], ...]:
    """Calcula una identidad estable de las tablas que alimentan el panel.

    El cache es intencionalmente de instancia, pero las tablas son mutables. Incluir
    sus huellas evita devolver un panel obsoleto si un proceso reutiliza ``datos`` y
    actualiza una fuente sin construir otra instancia.
    """

    fuente = getattr(datos, "fuente", None)
    firma_fuente = (
        str(getattr(fuente, "nombre", "")),
        str(getattr(fuente, "firma", "")),
        str(getattr(fuente, "corte", "")),
    )
    huellas = [("fuente", "|".join(firma_fuente))]
    for nombre in _TABLAS_SNAPSHOT:
        tabla = getattr(datos, nombre, pd.DataFrame())
        if not isinstance(tabla, pd.DataFrame):
            huella = repr(tabla)
        else:
            try:
                huella = sha256_dataframe(tabla, list(tabla.columns))
            except (TypeError, ValueError):
                huella = sha256(
                    tabla.to_json(orient="split", date_format="iso", default_handler=str).encode(
                        "utf-8"
                    )
                ).hexdigest()
        huellas.append((nombre, huella))
    return tuple(huellas)


def panel_replay_cache(datos, emisiones: pd.DataFrame, horizonte_semanas: int) -> pd.DataFrame:
    """Construye una sola vez el panel para MacroLegacy e híbrido.

    El cache vive únicamente durante la instancia ``DatosProyeccion``. No cruza campañas,
    conjuntos de emisiones ni snapshots, y solo guarda el panel as-of ya construido; las
    calibraciones y el entrenamiento residual siguen filtrándose por fecha de emisión.
    """

    if "campania" in emisiones:
        campanias = set(emisiones.campania.dropna().astype(str))
        if len(campanias) > 1:
            raise ValueError("panel_replay_cache requiere emisiones de una sola campaña")
    fechas = tuple(
        sorted(
            pd.to_datetime(emisiones.fecha_emision, errors="coerce")
            .dropna()
            .dt.normalize()
            .astype(str)
        )
    )
    campania = (
        str(emisiones.campania.iloc[0])
        if "campania" in emisiones and not emisiones.empty
        else _campania_defecto(datos)
    )
    clave = (campania, fechas, int(horizonte_semanas), _firma_snapshot(datos))
    cache = getattr(datos, "_hibrido_panel_cache", None)
    if cache is None:
        cache = {}
        datos._hibrido_panel_cache = cache
    if clave not in cache:
        cache[clave] = construir_panel_fenologico(
            datos, emisiones, horizonte_semanas=horizonte_semanas
        )
    return cache[clave]


def panel_corte_replay(datos, panel: pd.DataFrame, fecha: pd.Timestamp) -> pd.DataFrame:
    """Reduce un replay a la historia evaluable y la emisión que se está probando.

    La curva legacy solo necesita calibrarse con una parametrización as-of por lote para
    cada corte evaluado. Mantener todas las emisiones históricas dentro de ``_legacy_panel``
    multiplicaba innecesariamente las optimizaciones, sin aportar información adicional al
    ajuste residual del corte actual.
    """

    del datos  # Se conserva en la firma por compatibilidad con la fachada legacy.
    fecha = pd.Timestamp(fecha).normalize()
    emisiones = pd.to_datetime(panel.fecha_emision, errors="coerce").dt.normalize()
    objetivos = pd.to_datetime(panel.fecha_objetivo, errors="coerce").dt.normalize()
    actual = panel.loc[emisiones.eq(fecha)].copy()
    historia = panel.loc[emisiones.lt(fecha) & objetivos.lt(fecha) & panel.real_kg.notna()].copy()
    claves = ["campania", "lote_id", "fecha_objetivo"]
    if not historia.empty:
        historia = historia.sort_values("fecha_emision").drop_duplicates(claves, keep="last")
    return pd.concat([historia, actual], ignore_index=True, sort=False)


def backtest_hibrido_v1(
    datos,
    emisiones: pd.DataFrame,
    *,
    campania: str | None = None,
    horizonte_semanas: int = 10,
    minimo_entrenamiento: int = 30,
    max_cortes: int | None = 8,
) -> tuple[pd.DataFrame, list[str]]:
    """Replay rolling-origin del híbrido con real unido después de generar."""

    campania = str(campania or _campania_defecto(datos))
    emisiones_n = _normalizar_emisiones(emisiones, campania)
    if emisiones_n.empty:
        return pd.DataFrame(), ["No hay emisiones para el replay híbrido."]
    panel = panel_replay_cache(datos, emisiones_n, horizonte_semanas)
    evaluables = []
    for fecha in sorted(emisiones_n.fecha_emision.unique()):
        parte = panel[pd.to_datetime(panel.fecha_emision).dt.normalize().eq(pd.Timestamp(fecha))]
        if parte.real_kg.notna().any():
            evaluables.append(pd.Timestamp(fecha))
    advertencias = []
    if max_cortes and len(evaluables) > max_cortes:
        evaluables = evaluables[-max_cortes:]
    parametros_iniciales: dict[tuple[str, str], ParametrosBhattacharya] = {}
    predicciones = []
    for fecha in evaluables:
        panel_corte = panel_corte_replay(datos, panel, fecha)
        precalculado = _legacy_panel(
            panel_corte,
            datos,
            fecha_emision=fecha,
            parametros_iniciales=parametros_iniciales,
        )
        salida = proyectar_hibrido_v1(
            panel_corte,
            datos,
            fecha,
            minimo_entrenamiento=minimo_entrenamiento,
            _precalculado=precalculado,
        )
        if salida.empty:
            continue
        real = panel[pd.to_datetime(panel.fecha_emision).dt.normalize().eq(fecha)][
            [
                "campania",
                "lote_id",
                "fecha_objetivo",
                "real_kg",
                "peso_real_g",
                "frutos_reales_por_planta_catalogo",
                "plantas_reales",
            ]
        ].copy()
        claves = ["campania", "lote_id", "fecha_objetivo"]
        salida = salida.drop(columns=[c for c in ("real_kg",) if c in salida])
        salida = salida.merge(real, on=claves, how="left", validate="1:1")
        predicciones.append(salida)
    if not predicciones:
        advertencias.append("No hay emisiones híbridas con objetivos reales cerrados.")
        return pd.DataFrame(), advertencias
    resultado = pd.concat(predicciones, ignore_index=True, sort=False)
    resultado["banda_horizonte"] = resultado.horizonte_semanas.map(banda_horizonte)
    resultado["es_replay_ciego"] = True
    resultado["origen_emision"] = resultado.fecha_emision
    return resultado, advertencias


def backtest_macro_legacy_v1(
    datos,
    emisiones: pd.DataFrame,
    *,
    campania: str | None = None,
    horizonte_semanas: int = 10,
    max_cortes: int | None = 8,
) -> tuple[pd.DataFrame, list[str]]:
    """Replay de la curva legacy pura, con el mismo corte que el híbrido."""

    campania = str(campania or _campania_defecto(datos))
    emisiones_n = _normalizar_emisiones(emisiones, campania)
    if emisiones_n.empty:
        return pd.DataFrame(), ["No hay emisiones para el replay legacy."]
    panel = panel_replay_cache(datos, emisiones_n, horizonte_semanas)
    evaluables = []
    for fecha in sorted(emisiones_n.fecha_emision.unique()):
        parte = panel[pd.to_datetime(panel.fecha_emision).dt.normalize().eq(pd.Timestamp(fecha))]
        if parte.real_kg.notna().any():
            evaluables.append(pd.Timestamp(fecha))
    if max_cortes and len(evaluables) > max_cortes:
        evaluables = evaluables[-max_cortes:]
    parametros_iniciales: dict[tuple[str, str], ParametrosBhattacharya] = {}
    predicciones = []
    for fecha in evaluables:
        panel_corte = panel_corte_replay(datos, panel, fecha)
        precalculado = _legacy_panel(
            panel_corte,
            datos,
            fecha_emision=fecha,
            parametros_iniciales=parametros_iniciales,
        )
        salida = proyectar_macro_legacy_v1(panel_corte, datos, fecha, _precalculado=precalculado)
        if salida.empty:
            continue
        real = panel[pd.to_datetime(panel.fecha_emision).dt.normalize().eq(fecha)][
            [
                "campania",
                "lote_id",
                "fecha_objetivo",
                "real_kg",
                "peso_real_g",
                "frutos_reales_por_planta_catalogo",
                "plantas_reales",
            ]
        ].copy()
        salida = salida.drop(columns=[c for c in ("real_kg",) if c in salida])
        salida = salida.merge(
            real,
            on=["campania", "lote_id", "fecha_objetivo"],
            how="left",
            validate="1:1",
        )
        predicciones.append(salida)
    if not predicciones:
        return pd.DataFrame(), ["No hay emisiones legacy con objetivos reales cerrados."]
    resultado = pd.concat(predicciones, ignore_index=True, sort=False)
    resultado["banda_horizonte"] = resultado.horizonte_semanas.map(banda_horizonte)
    resultado["es_replay_ciego"] = True
    resultado["origen_emision"] = resultado.fecha_emision
    return resultado, []


def construir_curva_historica(
    predicciones: pd.DataFrame,
    *,
    modelos: tuple[str, ...] = ("R09_publicado", "HibridoLegacyResidual_v1"),
    real: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Construye una curva vintage usando la última emisión previa a cada semana."""

    if predicciones.empty:
        return pd.DataFrame()
    tabla = predicciones.copy()
    tabla["fecha_emision"] = pd.to_datetime(tabla.fecha_emision, errors="coerce")
    tabla["fecha_objetivo"] = pd.to_datetime(tabla.fecha_objetivo, errors="coerce")
    tabla = tabla[tabla.modelo.isin(modelos)].dropna(subset=["fecha_emision", "fecha_objetivo"])
    claves = [c for c in ("campania", "lote_id", "fecha_objetivo", "modelo") if c in tabla]
    tabla = tabla[tabla.fecha_emision < tabla.fecha_objetivo].copy()
    tabla = tabla.sort_values([*claves, "fecha_emision"])
    if claves:
        tabla = tabla.drop_duplicates(claves, keep="last")
    agregada = tabla.groupby(
        ["campania", "fecha_objetivo", "modelo"], dropna=False, as_index=False
    ).agg(
        p10_kg=("p10_kg", "sum"),
        p50_kg=("p50_kg", "sum"),
        p90_kg=("p90_kg", "sum"),
        real_kg=("real_kg", "sum"),
        origen_emision_min=("fecha_emision", "min"),
        origen_emision_max=("fecha_emision", "max"),
        n_lotes=("lote_id", "nunique"),
    )
    agregada["tipo_curva"] = "vintage_historico"
    if real is not None and not real.empty:
        r = real.copy()
        r["fecha_objetivo"] = pd.to_datetime(r.fecha_objetivo, errors="coerce")
        columnas = [c for c in ("campania", "fecha_objetivo", "real_kg") if c in r]
        r = r[columnas].groupby(["campania", "fecha_objetivo"], as_index=False).real_kg.sum()
        r["modelo"] = "Real cosechado"
        r["p10_kg"] = r.real_kg
        r["p50_kg"] = r.real_kg
        r["p90_kg"] = r.real_kg
        r["tipo_curva"] = "observado_completo"
        r["origen_emision_min"] = pd.NaT
        r["origen_emision_max"] = pd.NaT
        r["n_lotes"] = np.nan
        agregada = pd.concat([agregada, r[agregada.columns]], ignore_index=True, sort=False)
    return agregada.sort_values(["campania", "fecha_objetivo", "modelo"]).reset_index(drop=True)


__all__ = [
    "backtest_hibrido_v1",
    "backtest_macro_legacy_v1",
    "construir_curva_historica",
    "panel_corte_replay",
    "panel_replay_cache",
]

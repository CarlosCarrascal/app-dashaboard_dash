"""Proyecciones del modelo híbrido legacy.

Este módulo contiene el motor común que necesitan tanto el servicio público
como el replay. Mantenerlo separado evita que el replay tenga que volver a
importar la implementación del servicio, sin modificar las fórmulas ni las
firmas históricas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ...nucleo.bhattacharya import ParametrosBhattacharya
from ..contratos import validar_predicciones_componentes
from . import residual as _residual
from .macro import parametros_desde_bhattacharya, proyectar_macro
from .priors import (
    ParametroLegacyAsOf,
    calibrar_parametros_legacy_asof,
)

_ajustar_residuales = _residual.ajustar_residuales

NOMBRE_MODELO = "HibridoLegacyResidual_v1"
VERSION_MODELO = "legacy_residual_postgres_auto_asof_v2"


def _legacy_panel(
    panel: pd.DataFrame,
    datos,
    fecha_emision: pd.Timestamp | None = None,
    parametros_iniciales: dict[tuple[str, str], ParametrosBhattacharya] | None = None,
) -> tuple[pd.DataFrame, dict[str, ParametroLegacyAsOf]]:
    """Añade la curva legacy calibrada con el corte de cada emisión.

    En un replay el panel contiene varias emisiones. Calibrar todo con el último corte
    filtraría cosecha futura en las filas de entrenamiento, por lo que la fecha de corte
    se toma del grupo de emisión salvo que se entregue un override explícito.
    """

    salida = panel.copy()
    salida["legacy_frutos_por_planta"] = np.nan
    salida["legacy_peso_baya_g"] = np.nan
    salida["legacy_kg"] = np.nan
    salida["legacy_fuente_parametros"] = None
    salida["legacy_n_observaciones"] = 0
    parametros: dict[str, ParametroLegacyAsOf] = {}
    parametros_iniciales = parametros_iniciales if parametros_iniciales is not None else {}
    filas = []
    columnas_grupo = ["campania", "lote_id"]
    if fecha_emision is None:
        columnas_grupo.append("fecha_emision")
    for claves, grupo in salida.groupby(columnas_grupo, dropna=False):
        campania, lote_id = claves[:2]
        emision_grupo = claves[2] if len(claves) > 2 else fecha_emision
        corte = pd.Timestamp(
            fecha_emision if fecha_emision is not None else emision_grupo
        ).normalize()
        clave = f"{campania}|{lote_id}|{corte:%Y-%m-%d}"
        clave_lote = (str(campania), str(lote_id))
        prior_excel = parametros_iniciales.get(clave_lote)
        parametro = calibrar_parametros_legacy_asof(
            datos,
            str(campania),
            lote_id,
            corte,
            inicial=prior_excel,
        )
        # La optimización as-of puede mover X/O/N/A/B, pero no debe perder la
        # procedencia del prior Excel que le dio el punto de partida. Se conserva
        # en el mismo snapshot para que una predicción pueda volver a su libro y hash.
        if prior_excel is not None:
            parametro.parametros.archivo_fuente = prior_excel.archivo_fuente
            parametro.parametros.sha256_fuente = prior_excel.sha256_fuente
            parametro.parametros.fecha_vigencia = prior_excel.fecha_vigencia
        parametros_iniciales[clave_lote] = parametro.parametros
        parametros[clave] = parametro
        ventanas = grupo[["fecha_objetivo"]].copy()
        ventanas["fecha_inicio"] = pd.to_datetime(ventanas.fecha_objetivo) - pd.Timedelta(days=7)
        macro = proyectar_macro(
            parametros_desde_bhattacharya(
                parametro.parametros,
                area_ha=float(
                    pd.to_numeric(grupo.get("area_ha", pd.Series([1.0])), errors="coerce")
                    .dropna()
                    .iloc[0]
                )
                if "area_ha" in grupo
                and pd.to_numeric(grupo.area_ha, errors="coerce").notna().any()
                else 1.0,
            ),
            ventanas[["fecha_inicio", "fecha_objetivo"]],
        )
        macro.index = grupo.index
        macro["campania"] = campania
        macro["lote_id"] = lote_id
        macro["legacy_fuente_parametros"] = parametro.fuente
        macro["legacy_n_observaciones"] = parametro.n_observaciones
        macro["legacy_archivo_fuente"] = getattr(parametro.parametros, "archivo_fuente", None)
        macro["legacy_sha256_fuente"] = getattr(parametro.parametros, "sha256_fuente", None)
        macro["legacy_fecha_vigencia"] = getattr(parametro.parametros, "fecha_vigencia", None)
        macro["legacy_parametros_base"] = [
            prior_excel.to_dict() if prior_excel is not None else parametro.parametros.to_dict()
        ] * len(macro)
        filas.append(macro)
    if not filas:
        return salida, parametros
    calculado = pd.concat(filas).sort_index()
    for columna in ("frutos_por_planta", "peso_baya_g", "kg"):
        salida[f"legacy_{columna}"] = calculado[columna].to_numpy(float)
    salida["legacy_fuente_parametros"] = calculado.legacy_fuente_parametros.to_numpy()
    salida["legacy_n_observaciones"] = calculado.legacy_n_observaciones.to_numpy(int)
    return salida, parametros


def proyectar_hibrido_v1(
    panel: pd.DataFrame,
    datos,
    fecha_emision: object,
    *,
    minimo_entrenamiento: int = 30,
    _precalculado: tuple[pd.DataFrame, dict[str, ParametroLegacyAsOf]] | None = None,
) -> pd.DataFrame:
    """Genera una emisión híbrida sin mirar resultados posteriores al corte."""

    fecha = pd.Timestamp(fecha_emision).normalize()
    emision = panel[pd.to_datetime(panel.fecha_emision).dt.normalize().eq(fecha)].copy()
    if emision.empty:
        return pd.DataFrame()
    completo, parametros = (
        _precalculado if _precalculado is not None else _legacy_panel(panel, datos)
    )
    entrenamiento = completo[
        (pd.to_datetime(completo.fecha_emision) < fecha)
        & (pd.to_datetime(completo.fecha_objetivo) < fecha)
        & completo.real_kg.notna()
    ].copy()
    correccion = _ajustar_residuales(entrenamiento, minimo_entrenamiento)
    salida = completo[pd.to_datetime(completo.fecha_emision).dt.normalize().eq(fecha)].copy()
    features_frutos = [c for c in correccion.features_frutos if c in salida]
    features_peso = [c for c in correccion.features_peso if c in salida]
    factor_frutos = np.ones(len(salida), dtype=float)
    factor_peso = np.ones(len(salida), dtype=float)
    if correccion.modelo_frutos is not None and features_frutos:
        factor_frutos = np.exp(
            np.clip(correccion.modelo_frutos.predict(salida[features_frutos]), -1.5, 1.5)
        )
    if correccion.modelo_peso is not None and features_peso:
        factor_peso = np.exp(
            np.clip(correccion.modelo_peso.predict(salida[features_peso]), -0.7, 0.7)
        )
    frutos = np.maximum(0.0, salida.legacy_frutos_por_planta.to_numpy(float) * factor_frutos)
    peso = np.maximum(0.0, salida.legacy_peso_baya_g.to_numpy(float) * factor_peso)
    plantas = pd.to_numeric(salida.plantas, errors="coerce").to_numpy(float)
    kg = plantas * frutos * peso / 1000.0
    salida["modelo"] = NOMBRE_MODELO
    salida["version_fuente"] = VERSION_MODELO
    salida["frutos_por_planta"] = frutos
    salida["peso_baya_g"] = peso
    salida["plantas"] = plantas
    salida["p50_kg"] = np.maximum(0.0, kg)
    if np.isfinite(correccion.q10_kg) and np.isfinite(correccion.q90_kg):
        salida["p10_kg"] = salida.p50_kg * np.exp(correccion.q10_kg)
        salida["p90_kg"] = salida.p50_kg * np.exp(correccion.q90_kg)
    else:
        salida["p10_kg"] = np.nan
        salida["p90_kg"] = np.nan
    salida["real_kg"] = np.nan
    salida["base_plantas"] = "catalogo"
    salida["confianza"] = np.select(
        [
            salida.legacy_fuente_parametros.astype(str).str.startswith("postgres_auto_asof")
            & salida.legacy_n_observaciones.ge(4),
            salida.legacy_n_observaciones.ge(1),
        ],
        ["media", "baja"],
        default="baja",
    )
    salida["componentes"] = [
        {
            "modelo": NOMBRE_MODELO,
            "formula": "plantas_asof × frutos_hibridos/planta × peso_hibrido / 1000",
            "modelo_base": "MacroLegacy_v1",
            "modelo_correccion": "Ridge_spline_residual_asof",
            "features_frutos": features_frutos,
            "features_peso": features_peso,
            "n_entrenamiento": correccion.n_entrenamiento,
            "parametros_legacy_fuente": str(fila.legacy_fuente_parametros),
            "parametros_legacy_n": int(fila.legacy_n_observaciones),
            "etiqueta_causal": False,
            "limitacion": (
                "Corrección asociativa calibrada con residuos anteriores; no es efecto causal."
            ),
        }
        for fila in salida.itertuples(index=False)
    ]
    salida["correccion_frutos_factor"] = factor_frutos
    salida["correccion_peso_factor"] = factor_peso
    salida["parametros_legacy"] = [
        parametros.get(f"{fila.campania}|{fila.lote_id}|{fecha:%Y-%m-%d}").parametros.to_dict()
        if f"{fila.campania}|{fila.lote_id}|{fecha:%Y-%m-%d}" in parametros
        else {}
        for fila in salida.itertuples(index=False)
    ]
    salida = validar_predicciones_componentes(salida)
    return salida


def proyectar_macro_legacy_v1(
    panel: pd.DataFrame,
    datos,
    fecha_emision: object,
    *,
    _precalculado: tuple[pd.DataFrame, dict[str, ParametroLegacyAsOf]] | None = None,
) -> pd.DataFrame:
    """Emisión de la curva legacy sin corrección ML, para la comparación ciega."""

    fecha = pd.Timestamp(fecha_emision).normalize()
    parte = panel[pd.to_datetime(panel.fecha_emision).dt.normalize().eq(fecha)].copy()
    if parte.empty:
        return pd.DataFrame()
    salida, parametros = _precalculado if _precalculado is not None else _legacy_panel(panel, datos)
    salida = salida[pd.to_datetime(salida.fecha_emision).dt.normalize().eq(fecha)].copy()
    salida["modelo"] = "MacroLegacy_v1"
    salida["version_fuente"] = "macro_legacy_postgres_auto_asof_v2"
    salida["plantas"] = pd.to_numeric(salida.plantas, errors="coerce")
    salida["frutos_por_planta"] = salida.legacy_frutos_por_planta
    salida["peso_baya_g"] = salida.legacy_peso_baya_g
    salida["p50_kg"] = salida.plantas * salida.frutos_por_planta * salida.peso_baya_g / 1000
    salida["p10_kg"] = np.nan
    salida["p90_kg"] = np.nan
    salida["real_kg"] = np.nan
    salida["base_plantas"] = "catalogo"
    salida["confianza"] = np.where(
        salida.legacy_fuente_parametros.astype(str).str.startswith("postgres_auto_asof"),
        "media",
        "baja",
    )
    salida["componentes"] = [
        {
            "modelo": "MacroLegacy_v1",
            "formula": "tres oleadas normales + peso exponencial + plantas × frutos × peso / 1000",
            "fuente_parametros": str(fila.legacy_fuente_parametros),
            "n_observaciones_asof": int(fila.legacy_n_observaciones),
            "etiqueta_causal": False,
        }
        for fila in salida.itertuples(index=False)
    ]
    salida["parametros_legacy"] = [
        parametros.get(f"{fila.campania}|{fila.lote_id}|{fecha:%Y-%m-%d}").parametros.to_dict()
        if f"{fila.campania}|{fila.lote_id}|{fecha:%Y-%m-%d}" in parametros
        else {}
        for fila in salida.itertuples(index=False)
    ]
    return validar_predicciones_componentes(salida)


__all__ = [
    "proyectar_hibrido_v1",
    "proyectar_macro_legacy_v1",
]

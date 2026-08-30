"""Ejecución de emisiones y backtest rolling-origin del challenger as-of."""

from __future__ import annotations

from typing import Any

import pandas as pd

from analitica.aplicacion.parametros.contratos import (
    CLAVES,
    NOMBRE_MODELO,
    ConfiguracionParametrosAsOf,
)
from analitica.aplicacion.parametros.desplazamientos import (
    _desplazamiento_gdd_por_fila,
    aprender_desplazamiento,
    seleccionar_gdd_config,
)
from analitica.aplicacion.parametros.mezcla import (
    _completar_gdd,
    _interpolar_componentes,
    _mezclar_componentes,
)
from analitica.aplicacion.parametros.normalizacion import _parametros_excel_asof
from analitica.aplicacion.parametros.snapshots import construir_snapshot_parametros
from analitica.dominio.modelos.hibrido.priors import _campania_defecto, _normalizar_emisiones
from analitica.dominio.modelos.hibrido.proyecciones import (
    _legacy_panel,
    proyectar_hibrido_v1,
    proyectar_macro_legacy_v1,
)
from analitica.dominio.modelos.hibrido.replay import (
    panel_corte_replay as _panel_corte_replay,
)
from analitica.dominio.modelos.hibrido.replay import (
    panel_replay_cache as _panel_replay_cache,
)
from analitica.dominio.versiones import banda_horizonte


def ejecutar_emision_parametros_asof(
    panel: pd.DataFrame,
    datos,
    fecha_emision: object,
    *,
    historial: pd.DataFrame | None = None,
    config: ConfiguracionParametrosAsOf | None = None,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """Genera una emisión sin consultar información posterior al corte."""

    config = config or ConfiguracionParametrosAsOf()
    fecha = pd.Timestamp(fecha_emision).normalize()
    panel_corte = _panel_corte_replay(datos, panel, fecha)
    iniciales = _parametros_excel_asof(datos, panel_corte, fecha)
    precalculado = _legacy_panel(
        panel_corte,
        datos,
        fecha_emision=fecha,
        parametros_iniciales=iniciales,
    )
    macro = proyectar_macro_legacy_v1(panel_corte, datos, fecha, _precalculado=precalculado)
    residual = proyectar_hibrido_v1(
        panel_corte,
        datos,
        fecha,
        minimo_entrenamiento=config.minimo_entrenamiento,
        _precalculado=precalculado,
    )
    if macro.empty or residual.empty:
        return pd.DataFrame(), {"fecha_emision": fecha, "advertencia": "sin_salida"}, {}
    historico = historial if historial is not None else pd.DataFrame()
    salida, pesos = _mezclar_componentes(macro, residual, historico, config)
    desplazamiento, detalle_shift = aprender_desplazamiento(
        historico, max_shift_days=config.max_shift_days
    )
    gdd_base, gdd_ventana, detalle_gdd = seleccionar_gdd_config(historico, config)
    # El modelo solo deja que GDD modifique la fase si la relación fue admitida
    # por un holdout temporal. En caso contrario se conserva el desplazamiento
    # robusto aprendido de la curva real anterior.
    desplazamiento_gdd = _desplazamiento_gdd_por_fila(salida, desplazamiento, detalle_gdd)
    salida = _interpolar_componentes(salida, desplazamiento_gdd)
    salida = _completar_gdd(salida, gdd_base, gdd_ventana)
    salida["desplazamiento_dias"] = pd.to_numeric(
        salida["desplazamiento_dias"], errors="coerce"
    ).fillna(float(desplazamiento))
    gdd_aplicado = detalle_gdd.get("estado") == "admitido_oos"
    salida["componentes"] = [
        {
            "modelo": NOMBRE_MODELO,
            "formula": "plantas_asof × frutos_hibridos/planta × peso_hibrido / 1000",
            "modelo_base": "MacroLegacy_v1",
            "modelo_residual": "HibridoLegacyResidual_v1",
            "kg_legacy": float(fila.kg_legacy),
            "kg_residual": float(fila.kg_residual) if pd.notna(fila.kg_residual) else None,
            "peso_macro": float(fila.peso_macro),
            "correccion_frutos": float(fila.correccion_frutos_factor),
            "correccion_peso": float(fila.correccion_peso_factor),
            "desplazamiento_dias": int(round(float(fila.desplazamiento_dias))),
            "gdd_base": fila.gdd_base,
            "gdd_ventana": fila.gdd_ventana,
            "gdd_aplicado": gdd_aplicado,
            "gdd_estado": detalle_gdd.get("estado", "no_evaluado"),
            "gdd_nota": (
                "Desplazamiento fenológico admitido por validación OOS."
                if gdd_aplicado
                else "Candidato evaluado OOS; sin efecto en p50."
            ),
            "probabilidad_ocurrencia": None,
            "nivel_calibracion": str(fila.legacy_fuente_parametros),
            "n_observaciones_asof": int(fila.legacy_n_observaciones),
            "archivo_fuente": getattr(fila, "legacy_archivo_fuente", None),
            "sha256_fuente": getattr(fila, "legacy_sha256_fuente", None),
            "etiqueta_causal": False,
        }
        for fila in salida.itertuples(index=False)
    ]
    salida["parametros_legacy"] = [
        precalculado[1].get(f"{fila.campania}|{fila.lote_id}|{fecha:%Y-%m-%d}").parametros.to_dict()
        if f"{fila.campania}|{fila.lote_id}|{fecha:%Y-%m-%d}" in precalculado[1]
        else {}
        for fila in salida.itertuples(index=False)
    ]
    salida["banda_horizonte"] = salida.horizonte_semanas.map(banda_horizonte)
    salida["es_replay_ciego"] = True
    salida["origen_emision"] = salida.fecha_emision
    meta = {
        "fecha_emision": fecha,
        "pesos_macro": pesos,
        "desplazamiento": detalle_shift,
        "gdd": detalle_gdd,
        "n_parametros_excel_prior": len(iniciales),
        "sin_r09_predictor": True,
    }
    return salida, meta, precalculado[1]


def backtest_hibrido_parametros_asof(
    datos,
    emisiones: pd.DataFrame,
    *,
    campania: str | None = None,
    horizonte_semanas: int = 10,
    config: ConfiguracionParametrosAsOf | None = None,
    max_cortes: int | None = None,
) -> tuple[pd.DataFrame, list[str], pd.DataFrame]:
    """Replay rolling-origin del challenger con historia actualizada después de predecir."""

    config = config or ConfiguracionParametrosAsOf()
    campania = str(campania or _campania_defecto(datos))
    emisiones_n = _normalizar_emisiones(emisiones, campania)
    if emisiones_n.empty:
        return (
            pd.DataFrame(),
            ["No hay emisiones para el replay de parámetros as-of."],
            pd.DataFrame(),
        )
    panel = _panel_replay_cache(datos, emisiones_n, horizonte_semanas)
    fechas = sorted(pd.to_datetime(emisiones_n.fecha_emision).dropna().unique())
    evaluables = [
        pd.Timestamp(fecha)
        for fecha in fechas
        if panel.loc[
            pd.to_datetime(panel.fecha_emision).dt.normalize().eq(pd.Timestamp(fecha)), "real_kg"
        ]
        .notna()
        .any()
    ]
    if max_cortes and len(evaluables) > max_cortes:
        evaluables = evaluables[-max_cortes:]
    # El replay necesita historia para calibrar, pero no necesita conservar en
    # ella los JSON pesados de parámetros ni las explicaciones por predicción.
    # Mantener la salida completa en ``historial`` hacía crecer el proceso de
    # forma cuadrática durante una campaña larga y podía agotar la memoria.
    historial = pd.DataFrame()
    historial_partes: list[pd.DataFrame] = []
    columnas_historia_fijas = [
        "campania",
        "lote_id",
        "fecha_emision",
        "fecha_objetivo",
        "horizonte_semanas",
        "banda_horizonte",
        "real_kg",
        "legacy_kg",
        "residual_kg",
        "kg_legacy",
        "kg_residual",
    ]
    salidas: list[pd.DataFrame] = []
    snapshots: list[pd.DataFrame] = []
    for fecha in evaluables:
        salida, meta, parametros = ejecutar_emision_parametros_asof(
            panel, datos, fecha, historial=historial, config=config
        )
        if salida.empty:
            continue
        reales = panel.loc[
            pd.to_datetime(panel.fecha_emision).dt.normalize().eq(fecha),
            [
                *CLAVES,
                "real_kg",
                "peso_real_g",
                "frutos_reales_por_planta_catalogo",
                "plantas_reales",
            ],
        ].drop_duplicates(CLAVES)
        salida = salida.drop(columns=["real_kg"], errors="ignore").merge(
            reales, on=CLAVES, how="left", validate="1:1"
        )
        salida["es_replay_ciego"] = True
        # El snapshot se construye antes de adelgazar la salida porque allí sí
        # deben persistirse X/O/N/A/B base, delta y parámetros finales.
        snapshots.append(construir_snapshot_parametros(salida, meta=meta))

        columnas_historia = [
            columna
            for columna in columnas_historia_fijas + list(salida.columns)
            if columna in salida.columns
            and (columna in columnas_historia_fijas or str(columna).startswith("gdd_"))
        ]
        historial_partes.append(salida.loc[:, list(dict.fromkeys(columnas_historia))].copy())
        historial = pd.concat(historial_partes, ignore_index=True, sort=False)

        # Los parámetros completos ya viven en legacy_parameter_snapshot; no
        # deben duplicarse por cada lote-semana dentro de prediction.
        salida_guardar = salida.drop(
            columns=["parametros_legacy", "legacy_parametros_base"],
            errors="ignore",
        )
        salidas.append(salida_guardar)
    if not salidas:
        return pd.DataFrame(), ["No hay emisiones con objetivos reales cerrados."], pd.DataFrame()
    resultado = pd.concat(salidas, ignore_index=True, sort=False)
    snapshots_df = (
        pd.concat(snapshots, ignore_index=True, sort=False) if snapshots else pd.DataFrame()
    )
    return resultado, [], snapshots_df


__all__ = ["ejecutar_emision_parametros_asof", "backtest_hibrido_parametros_asof"]

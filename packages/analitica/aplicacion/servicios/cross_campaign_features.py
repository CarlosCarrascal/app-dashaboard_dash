"""Features as-of del screening cross-campaign h1."""

from __future__ import annotations

import numpy as np
import pandas as pd


def construir_features_asof(panel: pd.DataFrame) -> pd.DataFrame:
    """Crea features sin leer el real de semanas no cerradas a la emisión."""

    salida = panel.copy().sort_values(
        ["fecha_objetivo", "campania", "fundo_operativo"], kind="stable"
    )
    empresa = salida.groupby(
        ["campania", "fecha_emision", "fecha_objetivo", "semana_fin"], as_index=False
    ).agg(macro_kg=("macro_kg", "sum"), real_kg=("real_kg", "sum"))
    empresa["residuo"] = np.log1p(empresa.real_kg) - np.log1p(empresa.macro_kg)
    total_macro = salida.groupby(["campania", "fecha_objetivo"]).macro_kg.transform("sum")
    salida["log_macro"] = np.log1p(salida.macro_kg)
    salida["participacion_macro"] = np.where(
        total_macro.gt(0.0), salida.macro_kg / total_macro, 0.0
    )
    dia_anio = salida.fecha_objetivo.dt.dayofyear.astype(float)
    salida["fase_sin"] = np.sin(2.0 * np.pi * dia_anio / 365.2425)
    salida["fase_cos"] = np.cos(2.0 * np.pi * dia_anio / 365.2425)

    construidas: list[dict[str, float | int]] = []
    for fila in salida.itertuples(index=False):
        misma = salida.loc[
            salida.campania.eq(fila.campania) & salida.fundo_operativo.eq(fila.fundo_operativo)
        ].sort_values("fecha_objetivo", kind="stable")
        forecasts_previos = misma.loc[misma.fecha_emision.lt(fila.fecha_emision)]
        historia = misma.loc[misma.semana_fin.lt(fila.fecha_emision)]
        historia_empresa = empresa.loc[
            empresa.campania.eq(fila.campania) & empresa.semana_fin.lt(fila.fecha_emision)
        ].sort_values("fecha_objetivo", kind="stable")

        macros = forecasts_previos.macro_kg.astype(float).tail(2).tolist()
        macro_1 = macros[-1] if macros else float(fila.macro_kg)
        macro_2 = macros[-2] if len(macros) > 1 else macro_1
        pendiente = float(np.log1p(fila.macro_kg) - np.log1p(macro_1))
        pendiente_previa = float(np.log1p(macro_1) - np.log1p(macro_2))

        empresa_actual = empresa.loc[
            empresa.campania.eq(fila.campania) & empresa.fecha_objetivo.eq(fila.fecha_objetivo),
            "macro_kg",
        ]
        empresa_prev = empresa.loc[
            empresa.campania.eq(fila.campania) & empresa.fecha_emision.lt(fila.fecha_emision)
        ].sort_values("fecha_objetivo", kind="stable")
        macro_empresa_actual = float(empresa_actual.iloc[0]) if len(empresa_actual) else 0.0
        macro_empresa_previo = (
            float(empresa_prev.macro_kg.iloc[-1]) if len(empresa_prev) else macro_empresa_actual
        )

        residuos = historia.residuo_objetivo.astype(float)
        residuos_empresa = historia_empresa.residuo.astype(float)
        reales = historia.real_kg.astype(float)
        reales_log = np.log1p(reales)
        construidas.append(
            {
                "pendiente_macro": pendiente,
                "aceleracion_macro": pendiente - pendiente_previa,
                "pendiente_macro_empresa": float(
                    np.log1p(macro_empresa_actual) - np.log1p(macro_empresa_previo)
                ),
                "residuo_fundo_ultimo": float(residuos.iloc[-1]) if len(residuos) else 0.0,
                "residuo_fundo_media3": float(residuos.tail(3).mean()) if len(residuos) else 0.0,
                "residuo_fundo_media6": float(residuos.tail(6).mean()) if len(residuos) else 0.0,
                "residuo_empresa_media3": (
                    float(residuos_empresa.tail(3).mean()) if len(residuos_empresa) else 0.0
                ),
                "log_real_ultimo": float(reales_log.iloc[-1]) if len(reales_log) else 0.0,
                "tendencia_real": (
                    float(reales_log.iloc[-1] - reales_log.iloc[-2])
                    if len(reales_log) >= 2
                    else 0.0
                ),
                "n_historia": int(len(historia)),
                "log_n_historia": float(np.log1p(len(historia))),
                "max_cierre_feature": historia.semana_fin.max() if len(historia) else pd.NaT,
            }
        )
    return pd.concat([salida.reset_index(drop=True), pd.DataFrame(construidas)], axis=1)


__all__ = ["construir_features_asof"]

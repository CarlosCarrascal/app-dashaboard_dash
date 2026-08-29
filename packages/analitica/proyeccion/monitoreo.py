"""Monitoreo cuando llegan reales y para cambios del espacio de variables as-of."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .metricas import cobertura, wape

VARIABLES_MONITOREO = (
    "dias_desde_poda",
    "flores",
    "cuajo",
    "tasa_cuajo_observada",
    "indice_estado",
    "diametro_baya_mm",
    "temp_media_7d",
    "humedad_7d",
    "radiacion_7d",
    "eto_7d",
    "lluvia_7d",
    "temp_media_28d",
    "humedad_28d",
    "radiacion_28d",
    "eto_28d",
    "lluvia_28d",
)


def _fila(regla: str, estado: str, observados: int, afectados: int, detalle: dict) -> dict:
    return {
        "regla": regla,
        "estado": estado,
        "observados": int(observados),
        "afectados": int(afectados),
        "detalle": json.dumps(detalle, ensure_ascii=False, default=str),
    }


def _psi(referencia: pd.Series, actual: pd.Series, grupos: int = 10) -> float:
    """Population Stability Index con cortes aprendidos solo en referencia."""
    ref = pd.to_numeric(referencia, errors="coerce").dropna().to_numpy(float)
    act = pd.to_numeric(actual, errors="coerce").dropna().to_numpy(float)
    if len(ref) < 20 or len(act) < 10:
        return np.nan
    cortes = np.unique(np.quantile(ref, np.linspace(0, 1, grupos + 1)))
    if len(cortes) < 3:
        # Una referencia constante seguida por otro nivel es deriva extrema, pero usamos un
        # valor finito para mantener JSON/SQL interoperables.
        return 0.0 if np.allclose(np.nanmean(ref), np.nanmean(act)) else 10.0
    cortes[0], cortes[-1] = -np.inf, np.inf
    hist_ref = np.histogram(ref, bins=cortes)[0] / len(ref)
    hist_act = np.histogram(act, bins=cortes)[0] / len(act)
    hist_ref = np.clip(hist_ref, 1e-6, None)
    hist_act = np.clip(hist_act, 1e-6, None)
    return float(np.sum((hist_act - hist_ref) * np.log(hist_act / hist_ref)))


def monitorear_llegada_reales(
    predicciones: pd.DataFrame,
    panel_asof: pd.DataFrame,
    *,
    umbral_psi: float = 0.25,
) -> pd.DataFrame:
    """Registra realización, cobertura, degradación, deriva y fuera-de-rango.

    Las métricas WAPE/MASE/sesgo se actualizan en ``analytics.metric``. Estos controles
    complementarios explican si el cambio coincide con datos nuevos o extrapolación.
    """
    filas: list[dict] = []
    base = predicciones[predicciones.modelo == "R09_publicado"].copy()
    realizados = base.dropna(subset=["real_kg", "p50_kg"])
    filas.append(
        _fila(
            "monitoreo_reales_disponibles",
            "ok" if len(realizados) else "warning",
            len(base),
            len(base) - len(realizados),
            {
                "realizados": len(realizados),
                "pendientes": len(base) - len(realizados),
                "nota": "WAPE, MASE y sesgo se recalculan al reejecutar analytics:backtest.",
            },
        )
    )
    if not realizados.empty:
        cobertura_80 = cobertura(realizados.real_kg, realizados.p10_kg, realizados.p90_kg)
        filas.append(
            _fila(
                "monitoreo_cobertura_p10_p90",
                "ok" if 0.75 <= cobertura_80 <= 0.85 else "warning",
                len(realizados),
                int(round(abs(cobertura_80 - 0.80) * len(realizados))),
                {"cobertura": cobertura_80, "rango_objetivo": [0.75, 0.85]},
            )
        )
        segmentos = []
        for (campania, banda), grupo in realizados.groupby(
            ["campania", "banda_horizonte"], dropna=False
        ):
            segmentos.append(
                {
                    "campania": str(campania),
                    "banda": str(banda),
                    "wape": wape(grupo.real_kg, grupo.p50_kg),
                    "n": len(grupo),
                }
            )
        tabla_segmentos = pd.DataFrame(segmentos)
        deterioros = []
        if not tabla_segmentos.empty:
            for _, grupo in tabla_segmentos.groupby("banda"):
                grupo = grupo.sort_values("campania")
                if len(grupo) >= 2 and grupo.iloc[-2].wape > 0:
                    deterioros.append(
                        {
                            "banda": grupo.iloc[-1].banda,
                            "campania": grupo.iloc[-1].campania,
                            "deterioro_relativo": grupo.iloc[-1].wape / grupo.iloc[-2].wape - 1,
                        }
                    )
        peor = max((d["deterioro_relativo"] for d in deterioros), default=np.nan)
        filas.append(
            _fila(
                "monitoreo_degradacion_campania_horizonte",
                "warning" if np.isfinite(peor) and peor > 0.20 else "ok",
                len(tabla_segmentos),
                sum(d["deterioro_relativo"] > 0.20 for d in deterioros),
                {"comparaciones": deterioros, "umbral_relativo": 0.20},
            )
        )

    panel = panel_asof.copy()
    variables = [c for c in VARIABLES_MONITOREO if c in panel]
    emisiones = sorted(pd.to_datetime(panel.fecha_emision, errors="coerce").dropna().unique())
    if variables and len(emisiones) >= 5:
        punto = max(1, int(np.floor(len(emisiones) * 0.8)))
        referencia = panel[pd.to_datetime(panel.fecha_emision).isin(emisiones[:punto])]
        actual = panel[pd.to_datetime(panel.fecha_emision).isin(emisiones[punto:])]
        psis = {c: _psi(referencia[c], actual[c]) for c in variables}
        psis = {c: v for c, v in psis.items() if np.isfinite(v)}
        alteradas = {c: v for c, v in psis.items() if v > umbral_psi}
        filas.append(
            _fila(
                "monitoreo_deriva_variables_psi",
                "warning" if alteradas else "ok",
                len(psis),
                len(alteradas),
                {
                    "psi": psis,
                    "umbral": umbral_psi,
                    "corte_emision": str(pd.Timestamp(emisiones[punto]))
                    if punto < len(emisiones)
                    else None,
                },
            )
        )
        fuera = pd.Series(False, index=actual.index)
        detalle_fuera = {}
        for columna in variables:
            ref = pd.to_numeric(referencia[columna], errors="coerce").dropna()
            act = pd.to_numeric(actual[columna], errors="coerce")
            if ref.empty:
                continue
            mascara = act.notna() & ((act < ref.min()) | (act > ref.max()))
            fuera |= mascara
            detalle_fuera[columna] = int(mascara.sum())
        filas.append(
            _fila(
                "monitoreo_lotes_fuera_rango_entrenamiento",
                "warning" if fuera.any() else "ok",
                len(actual),
                int(fuera.sum()),
                {"por_variable": detalle_fuera},
            )
        )
    else:
        filas.append(
            _fila(
                "monitoreo_deriva_variables_psi",
                "warning",
                len(panel),
                0,
                {"nota": "No hay al menos cinco emisiones y variables suficientes."},
            )
        )
    return pd.DataFrame(filas)

"""Evaluación, selección y contrato de ejecución cross-campaign h1."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from .cross_campaign_features import construir_features_asof
from .cross_campaign_lectura import (
    CIERRE_CERTIFICADO_C2026,
    FUNDOS,
    MACRO_RUN_ID,
    R09_ACCESS_DEFAULT,
    REAL_ACCESS_DEFAULT,
    SEMANA_DESARROLLO_C2026,
    SEMANAS_HOLDOUT_C2026,
    construir_panel,
    leer_macro_h1,
    leer_r09_access,
    leer_reales_access,
)
from .cross_campaign_persistencia import sha256_archivo
from .cross_campaign_prediccion import (
    FEATURE_SETS,
    Configuracion,
    configuraciones,
    predecir_rolling,
)


def _metricas(tabla: pd.DataFrame, columna: str, grano: Iterable[str]) -> dict[str, float | int]:
    agregado = tabla.groupby(list(grano), as_index=False, dropna=False).agg(
        pred_kg=(columna, "sum"), real_kg=("real_kg", "sum")
    )
    error = agregado.pred_kg - agregado.real_kg
    denominador = float(agregado.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / denominador) if denominador else np.nan,
        "sesgo": float(error.sum() / denominador) if denominador else np.nan,
        "mae_kg": float(error.abs().mean()) if len(agregado) else np.nan,
        "rmse_kg": float(np.sqrt(np.mean(np.square(error)))) if len(agregado) else np.nan,
        "n": int(len(agregado)),
        "real_kg": float(agregado.real_kg.sum()),
        "pred_kg": float(agregado.pred_kg.sum()),
    }


def bootstrap_pareado(
    tabla: pd.DataFrame,
    candidato: str,
    referencia: str,
    repeticiones: int = 5_000,
) -> dict[str, object] | None:
    columnas = ["campania", "fecha_objetivo", "real_kg", candidato, referencia]
    bloque = tabla[columnas].dropna(subset=[candidato, referencia]).copy()
    if bloque.empty:
        return None
    semanal = bloque.groupby(["campania", "fecha_objetivo"], as_index=False).agg(
        real_kg=("real_kg", "sum"),
        candidato_kg=(candidato, "sum"),
        referencia_kg=(referencia, "sum"),
    )
    error_c = (semanal.candidato_kg - semanal.real_kg).abs().to_numpy(float)
    error_r = (semanal.referencia_kg - semanal.real_kg).abs().to_numpy(float)
    real = semanal.real_kg.abs().to_numpy(float)
    rng = np.random.default_rng(20260825)
    diferencias: list[float] = []
    for _ in range(repeticiones):
        indices = rng.integers(0, len(semanal), len(semanal))
        den = float(real[indices].sum())
        if den:
            diferencias.append(float((error_c[indices].sum() - error_r[indices].sum()) / den))
    intervalo = np.quantile(diferencias, [0.025, 0.975]) if diferencias else [np.nan, np.nan]
    den_total = float(real.sum())
    return {
        "n_semanas": int(len(semanal)),
        "diferencia_wape_pp": float(100.0 * (error_c.sum() - error_r.sum()) / den_total),
        "ic95_diferencia_wape_pp": [float(100.0 * intervalo[0]), float(100.0 * intervalo[1])],
        "semanas_ganadas": int((error_c < error_r).sum()),
        "semanas_empatadas": int(np.isclose(error_c, error_r).sum()),
    }


def _por_fundo(tabla: pd.DataFrame, columna: str) -> dict[str, dict[str, float | int]]:
    return {
        fundo: _metricas(
            tabla.loc[tabla.fundo_operativo.eq(fundo)],
            columna,
            ("fecha_objetivo", "fundo_operativo"),
        )
        for fundo in FUNDOS
    }


def _bootstrap_por_fundo(
    tabla: pd.DataFrame, candidato: str, referencia: str
) -> dict[str, dict[str, object] | None]:
    return {
        fundo: bootstrap_pareado(tabla.loc[tabla.fundo_operativo.eq(fundo)], candidato, referencia)
        for fundo in FUNDOS
    }


def _resumen_periodo(tabla: pd.DataFrame) -> dict[str, object]:
    salida: dict[str, object] = {
        "rango": {
            "desde": str(tabla.fecha_objetivo.min().date()) if len(tabla) else None,
            "hasta": str(tabla.fecha_objetivo.max().date()) if len(tabla) else None,
            "semanas": int(tabla.fecha_objetivo.nunique()),
        },
        "empresa": {
            "candidato": _metricas(tabla, "candidate_kg", ("fecha_objetivo",)),
            "macro": _metricas(tabla, "macro_kg", ("fecha_objetivo",)),
        },
        "fundo": {
            "candidato": _metricas(tabla, "candidate_kg", ("fecha_objetivo", "fundo_operativo")),
            "macro": _metricas(tabla, "macro_kg", ("fecha_objetivo", "fundo_operativo")),
            "por_fundo_candidato": _por_fundo(tabla, "candidate_kg"),
            "por_fundo_macro": _por_fundo(tabla, "macro_kg"),
        },
        "bootstrap_vs_macro": bootstrap_pareado(tabla, "candidate_kg", "macro_kg"),
        "bootstrap_por_fundo_vs_macro": _bootstrap_por_fundo(tabla, "candidate_kg", "macro_kg"),
        "cobertura": {
            "filas": float(tabla.candidate_kg.notna().mean()) if len(tabla) else np.nan,
            "volumen_macro_positivo": (
                float(tabla.loc[tabla.macro_kg.gt(0), "real_kg"].sum() / tabla.real_kg.sum())
                if tabla.real_kg.sum()
                else np.nan
            ),
        },
    }
    comun = tabla.loc[tabla.r09_kg.notna()].copy() if "r09_kg" in tabla else tabla.iloc[0:0]
    if len(comun):
        salida["r09_mismo_universo"] = {
            "empresa": {
                "candidato": _metricas(comun, "candidate_kg", ("fecha_objetivo",)),
                "macro": _metricas(comun, "macro_kg", ("fecha_objetivo",)),
                "r09": _metricas(comun, "r09_kg", ("fecha_objetivo",)),
            },
            "fundo": {
                "candidato": _metricas(
                    comun, "candidate_kg", ("fecha_objetivo", "fundo_operativo")
                ),
                "r09": _metricas(comun, "r09_kg", ("fecha_objetivo", "fundo_operativo")),
                "por_fundo_r09": _por_fundo(comun, "r09_kg"),
            },
            "bootstrap_vs_r09": bootstrap_pareado(comun, "candidate_kg", "r09_kg"),
            "bootstrap_por_fundo_vs_r09": _bootstrap_por_fundo(comun, "candidate_kg", "r09_kg"),
            "n_filas_comunes": int(len(comun)),
            "n_semanas_comunes": int(comun.fecha_objetivo.nunique()),
        }
    else:
        salida["r09_mismo_universo"] = None
    return salida


def mascara_seleccion(tabla: pd.DataFrame) -> pd.Series:
    return tabla.campania.eq("C2025") | (
        tabla.campania.eq("C2026") & tabla.semana_iso.le(SEMANA_DESARROLLO_C2026)
    )


def seleccionar_configuracion(
    panel: pd.DataFrame,
) -> tuple[Configuracion, pd.DataFrame, pd.DataFrame]:
    """Selecciona con C2025 y C2026<=S30; nunca consulta S31--S33 ni R09."""

    ranking: list[dict[str, object]] = []
    predicciones: dict[str, pd.DataFrame] = {}
    for config in configuraciones():
        pred = predecir_rolling(panel, config)
        predicciones[config.id] = pred
        c25 = pred.loc[pred.campania.eq("C2025")]
        c26 = pred.loc[pred.campania.eq("C2026") & pred.semana_iso.le(30)]
        m25e = _metricas(c25, "candidate_kg", ("fecha_objetivo",))
        m25f = _metricas(c25, "candidate_kg", ("fecha_objetivo", "fundo_operativo"))
        m26e = _metricas(c26, "candidate_kg", ("fecha_objetivo",))
        m26f = _metricas(c26, "candidate_kg", ("fecha_objetivo", "fundo_operativo"))
        macro25 = _metricas(c25, "macro_kg", ("fecha_objetivo",))
        macro26 = _metricas(c26, "macro_kg", ("fecha_objetivo",))
        score = (
            0.30 * float(m25e["wape"])
            + 0.15 * float(m25f["wape"])
            + 0.35 * float(m26e["wape"])
            + 0.20 * float(m26f["wape"])
            + 0.10 * (abs(float(m25e["sesgo"])) + abs(float(m26e["sesgo"])))
        )
        ranking.append(
            {
                "configuracion_id": config.id,
                "estimador": config.estimador,
                "score_seleccion": score,
                "c2025_wape_empresa": m25e["wape"],
                "c2025_bias_empresa": m25e["sesgo"],
                "c2025_wape_fundo": m25f["wape"],
                "c2025_macro_wape_empresa": macro25["wape"],
                "c2025_delta_vs_macro_pp": 100.0 * (m25e["wape"] - macro25["wape"]),
                "c2026_dev_wape_empresa": m26e["wape"],
                "c2026_dev_bias_empresa": m26e["sesgo"],
                "c2026_dev_wape_fundo": m26f["wape"],
                "c2026_dev_macro_wape_empresa": macro26["wape"],
                "c2026_dev_delta_vs_macro_pp": 100.0 * (m26e["wape"] - macro26["wape"]),
                "proporcion_ajustada": float(
                    pred.loc[mascara_seleccion(pred), "modelo_ajustado"].mean()
                ),
            }
        )
    orden = pd.DataFrame(ranking)
    elegibles = orden.loc[
        orden.c2025_bias_empresa.abs().le(0.20)
        & orden.c2026_dev_bias_empresa.abs().le(0.20)
        & orden.proporcion_ajustada.ge(0.50)
        & orden.c2025_delta_vs_macro_pp.le(0.0)
        & orden.c2026_dev_delta_vs_macro_pp.le(0.0)
    ].sort_values(["score_seleccion", "c2026_dev_wape_empresa"], kind="stable")
    pasa_gate = not elegibles.empty
    if elegibles.empty:
        elegibles = orden.sort_values(["score_seleccion", "c2026_dev_wape_empresa"], kind="stable")
    ganador_id = str(elegibles.iloc[0].configuracion_id)
    mapa = {config.id: config for config in configuraciones()}
    ranking_final = elegibles.reset_index(drop=True)
    ranking_final.attrs["pasa_gate_desarrollo"] = pasa_gate
    return mapa[ganador_id], predicciones[ganador_id], ranking_final


def _keyset_sha256(tabla: pd.DataFrame) -> str:
    columnas = ["campania", "fecha_emision", "fecha_objetivo", "fundo_operativo"]
    texto = (
        tabla[columnas]
        .sort_values(columnas, kind="stable")
        .astype(str)
        .agg("|".join, axis=1)
        .str.cat(sep="\n")
    )
    return hashlib.sha256(texto.encode()).hexdigest()


def ejecutar(
    *,
    real_access: Path = REAL_ACCESS_DEFAULT,
    r09_access: Path = R09_ACCESS_DEFAULT,
    run_id: int = MACRO_RUN_ID,
) -> tuple[dict[str, object], pd.DataFrame]:
    macro = leer_macro_h1(run_id)
    reales, maximos = leer_reales_access(real_access)
    panel = construir_features_asof(construir_panel(macro, reales, maximos))
    ganador, prediccion, ranking = seleccionar_configuracion(panel)

    # R09 se incorpora recién después de congelar ganador y predicciones.
    r09 = leer_r09_access(r09_access)[
        ["campania", "fecha_objetivo", "fundo_operativo", "r09_kg", "fecha_emision", "version"]
    ].rename(columns={"fecha_emision": "fecha_emision_r09", "version": "version_r09"})
    final = prediccion.merge(
        r09,
        on=["campania", "fecha_objetivo", "fundo_operativo"],
        how="left",
        validate="one_to_one",
    )
    if (
        final.loc[final.r09_kg.notna(), "fecha_emision_r09"]
        .ge(final.loc[final.r09_kg.notna(), "fecha_objetivo"])
        .any()
    ):
        raise AssertionError("R09 contemporáneo entró al contrato presemana")

    periodos = {
        "c2025_out_of_campaign": final.campania.eq("C2025"),
        "c2026_desarrollo_s13_s30": final.campania.eq("C2026") & final.semana_iso.le(30),
        "c2026_holdout_s31_s33": final.campania.eq("C2026")
        & final.semana_iso.isin(SEMANAS_HOLDOUT_C2026),
        "c2026_completo_cerrado": final.campania.eq("C2026"),
    }
    metricas = {
        nombre: _resumen_periodo(final.loc[mascara]) for nombre, mascara in periodos.items()
    }
    holdout = metricas["c2026_holdout_s31_s33"]
    holdout_candidato = holdout["empresa"]["candidato"]
    holdout_macro = holdout["empresa"]["macro"]
    r09_holdout = holdout.get("r09_mismo_universo")
    pasa_macro = (
        float(holdout_candidato["wape"]) <= float(holdout_macro["wape"])
        and abs(float(holdout_candidato["sesgo"])) <= 0.15
    )
    pasa_r09 = False
    if isinstance(r09_holdout, dict):
        comparacion = r09_holdout["empresa"]
        pasa_r09 = float(comparacion["candidato"]["wape"]) <= float(comparacion["r09"]["wape"])

    resultado: dict[str, object] = {
        "schema": "screening-cross-campaign-h1-v1",
        "candidate_only": True,
        "persistido": False,
        "publicado": False,
        "macro_run_id": int(run_id),
        "seleccion": "C2025 externo + C2026 S13-S30; C2026 S31-S33 reservado",
        "configuracion_ganadora": asdict(ganador),
        "configuracion_id": ganador.id,
        "seleccion_supera_macro_c2025_y_c2026_desarrollo": bool(
            ranking.attrs.get("pasa_gate_desarrollo", False)
        ),
        "features": list(FEATURE_SETS.get(ganador.feature_set, ())),
        "usa_r09_como_predictor": False,
        "fuentes": {
            "reales_access": str(real_access),
            "reales_sha256": sha256_archivo(real_access),
            "r09_access_oficial": str(r09_access),
            "r09_sha256": sha256_archivo(r09_access),
            "macro": f"analytics.prediction run_id={run_id} MacroLegacy_v1 h1",
        },
        "evaluation_contract": {
            "keyset_sha256": _keyset_sha256(final),
            "n_filas_fundo_semana": int(len(final)),
            "n_semanas": int(final[["campania", "fecha_objetivo"]].drop_duplicates().shape[0]),
            "cierre_c2026": str(CIERRE_CERTIFICADO_C2026.date()),
            "regla_r09": (
                "fecha_emision_derivada < lunes_objetivo; última variante numérica elegible"
            ),
        },
        "metricas": metricas,
        "ranking_seleccion": ranking.to_dict("records"),
        "veredicto_holdout": {
            "mejora_o_iguala_macro": bool(pasa_macro),
            "mejora_o_iguala_r09_mismo_universo": bool(pasa_r09),
            "aprobado_para_persistir": False,
            "nota": "screening aislado; requiere gates externos antes de persistir",
        },
    }
    detalle = final[
        [
            "campania",
            "fecha_emision",
            "fecha_objetivo",
            "semana_fin",
            "semana_iso",
            "fundo_operativo",
            "macro_kg",
            "candidate_kg",
            "real_kg",
            "r09_kg",
            "fecha_emision_r09",
            "version_r09",
            "correccion_log",
            "modelo_ajustado",
            "n_entrenamiento",
            "max_cierre_entrenamiento",
        ]
    ].copy()
    return resultado, detalle


__all__ = [
    "bootstrap_pareado",
    "ejecutar",
    "mascara_seleccion",
    "seleccionar_configuracion",
]

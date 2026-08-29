"""Evaluación contractual y de calidad para candidatos no publicados."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from ..compartido import identidad as _identidad
from .contratos import (
    CLAVES_EVALUACION,
    EXIT_CONTRACT_REJECTED,
    EXIT_OK,
    EXIT_QUALITY_REJECTED,
    HORIZONTES_MICRO,
    UmbralesPreflight,
)

_limpio_json = _identidad._limpio_json
sha256_dataframe = _identidad.sha256_dataframe


def _semana_inicio(fechas: pd.Series) -> pd.Series:
    serie = pd.to_datetime(fechas, errors="coerce").dt.normalize()
    return serie - pd.to_timedelta(serie.dt.weekday, unit="D")


def _normalizar_predicciones(tabla: pd.DataFrame, campania: str) -> pd.DataFrame:
    t = tabla.copy()
    t = t[t.campania.astype(str).eq(str(campania))]
    t["fecha_emision"] = pd.to_datetime(t.fecha_emision, errors="coerce").dt.normalize()
    t["fecha_objetivo"] = pd.to_datetime(t.fecha_objetivo, errors="coerce").dt.normalize()
    t["horizonte_semanas"] = pd.to_numeric(t.horizonte_semanas, errors="coerce")
    t["p50_kg"] = pd.to_numeric(t.p50_kg, errors="coerce")
    t["real_kg"] = pd.to_numeric(t.real_kg, errors="coerce")
    t["semana_inicio"] = _semana_inicio(t.fecha_objetivo)
    t["semana_fin"] = t.semana_inicio + pd.to_timedelta(6, unit="D")
    return t


def _metricas_modelo(universo: pd.DataFrame, predicciones: pd.DataFrame) -> dict[str, Any]:
    claves = list(CLAVES_EVALUACION)
    pred = predicciones[claves + ["p50_kg"]].drop_duplicates(claves)
    alineado = universo.merge(pred, on=claves, how="left", validate="1:1")
    emitio = alineado.p50_kg.notna()
    alineado["pred_kg"] = alineado.p50_kg.fillna(0.0).clip(lower=0.0)
    real_total = float(alineado.real_kg.abs().sum())
    lotes_total = int(alineado.lote_id.nunique())
    lotes_emitidos = int(alineado.loc[emitio, "lote_id"].nunique())
    semanal = alineado.groupby(
        ["fecha_emision", "fecha_objetivo", "horizonte_semanas"], as_index=False
    ).agg(real_kg=("real_kg", "sum"), pred_kg=("pred_kg", "sum"))
    denominador = float(semanal.real_kg.abs().sum())
    wape = (
        float((semanal.pred_kg - semanal.real_kg).abs().sum() / denominador)
        if denominador
        else np.nan
    )
    sesgo = (
        float((semanal.pred_kg - semanal.real_kg).sum() / denominador) if denominador else np.nan
    )
    volumen_emitido = float(alineado.loc[emitio, "real_kg"].abs().sum())
    falso_cero = float(alineado.loc[alineado.pred_kg.le(0), "real_kg"].clip(lower=0).sum())
    por_horizonte: dict[str, dict[str, float | int]] = {}
    for horizonte, grupo in semanal.groupby("horizonte_semanas"):
        denom = float(grupo.real_kg.abs().sum())
        por_horizonte[str(int(horizonte))] = {
            "n": int(len(grupo)),
            "wape": float((grupo.pred_kg - grupo.real_kg).abs().sum() / denom) if denom else np.nan,
            "sesgo": float((grupo.pred_kg - grupo.real_kg).sum() / denom) if denom else np.nan,
        }
    return {
        "n_lote_emision_semana": int(len(alineado)),
        "n_semanas_empresa": int(len(semanal)),
        "volumen_real_kg": real_total,
        "volumen_predicho_kg": float(alineado.pred_kg.sum()),
        "wape": wape,
        "sesgo": sesgo,
        "cobertura_lotes": float(lotes_emitidos / lotes_total) if lotes_total else np.nan,
        "cobertura_volumen": float(volumen_emitido / real_total) if real_total else np.nan,
        "falsos_ceros_volumen": float(falso_cero / real_total) if real_total else np.nan,
        "por_horizonte": por_horizonte,
    }


def evaluar_preflight(
    candidato: pd.DataFrame,
    baselines: Mapping[str, pd.DataFrame],
    *,
    campania: str,
    cosecha: pd.DataFrame,
    baseline_run_ids: Mapping[str, int],
    modelo_macro: str = "MacroLegacy_v1",
    horizontes: tuple[int, ...] = HORIZONTES_MICRO,
    umbrales: UmbralesPreflight | None = None,
    hashes_esperados: Mapping[str, str] | None = None,
    expected_keyset_sha256: str | None = None,
    cerrado_hasta: str | pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Evalua contratos y calidad sin escribir en PostgreSQL."""

    umbrales = umbrales or UmbralesPreflight()
    errores_contrato: list[dict[str, Any]] = []
    gates: list[dict[str, Any]] = []
    c = _normalizar_predicciones(candidato, campania)
    baselines_n = {
        modelo: _normalizar_predicciones(tabla, campania) for modelo, tabla in baselines.items()
    }
    for columna in ("fecha_emision", "fecha_objetivo", "horizonte_semanas", "p50_kg"):
        invalidas = int(c[columna].isna().sum())
        if invalidas:
            errores_contrato.append({"regla": f"{columna}_valido", "afectados": invalidas})
    horizonte = c["horizonte_semanas"].dropna()
    if not horizonte.empty and (
        not np.isfinite(horizonte).all() or not horizonte.eq(horizonte.round()).all()
    ):
        errores_contrato.append(
            {"regla": "horizonte_entero_finito", "afectados": int(len(horizonte))}
        )
    p50 = c["p50_kg"].dropna()
    negativos = int(p50.lt(0).sum())
    infinitos = int((~np.isfinite(p50)).sum())
    if negativos or infinitos:
        errores_contrato.append(
            {
                "regla": "p50_no_negativo_finito",
                "afectados": negativos + infinitos,
            }
        )
    duplicados = c.duplicated(list(CLAVES_EVALUACION), keep=False)
    if duplicados.any():
        errores_contrato.append({"regla": "clave_unica", "afectados": int(duplicados.sum())})
    contemporaneas = c.fecha_emision.ge(c.semana_inicio)
    if contemporaneas.any():
        errores_contrato.append(
            {"regla": "emision_estrictamente_anterior", "afectados": int(contemporaneas.sum())}
        )
    h = cosecha[cosecha.campania.astype(str).eq(str(campania))].copy()
    h["fecha"] = pd.to_datetime(h.fecha, errors="coerce").dt.normalize()
    watermark_fuente = h.fecha.max()
    if cerrado_hasta is not None:
        watermark_contrato = pd.Timestamp(cerrado_hasta).normalize()
        if pd.isna(watermark_fuente) or watermark_contrato > watermark_fuente:
            errores_contrato.append(
                {
                    "regla": "cierre_no_supera_fuente_real",
                    "cerrado_hasta": watermark_contrato,
                    "watermark_fuente": watermark_fuente,
                }
            )
        watermark = (
            min(watermark_contrato, watermark_fuente)
            if pd.notna(watermark_fuente)
            else watermark_contrato
        )
    else:
        watermark = watermark_fuente
    c["semana_cerrada"] = c.semana_fin.le(watermark) if pd.notna(watermark) else False
    c["semana_parcial"] = (
        c.semana_inicio.le(watermark) & c.semana_fin.gt(watermark) if pd.notna(watermark) else False
    )
    parciales = int(c.semana_parcial.sum())
    candidato_evaluable = c[c.semana_cerrada & c.horizonte_semanas.isin(horizontes)].copy()
    presentes = tuple(sorted(candidato_evaluable.horizonte_semanas.dropna().astype(int).unique()))
    faltantes_h = sorted(set(horizontes) - set(presentes))
    if faltantes_h:
        errores_contrato.append({"regla": "horizontes_micro_completos", "faltantes": faltantes_h})

    # El universo lo fija Macro congelada, no el challenger. Si el candidato omite
    # lotes-semana, esas filas permanecen y se penalizan como falta de cobertura.
    macro_fuente = baselines_n.get(modelo_macro, pd.DataFrame()).copy()
    if macro_fuente.empty:
        errores_contrato.append({"regla": "baseline_macro_requerido", "modelo": modelo_macro})
    else:
        macro_fuente = macro_fuente[
            macro_fuente.fecha_emision.isin(c.fecha_emision.dropna().unique())
            & macro_fuente.horizonte_semanas.isin(horizontes)
        ].copy()
        macro_fuente["semana_cerrada"] = (
            macro_fuente.semana_fin.le(watermark) if pd.notna(watermark) else False
        )
        macro_fuente = macro_fuente[macro_fuente.semana_cerrada & macro_fuente.real_kg.notna()]
    if macro_fuente.empty:
        errores_contrato.append({"regla": "universo_evaluable_no_vacio", "afectados": 0})
    universo = macro_fuente[list(CLAVES_EVALUACION) + ["real_kg"]].drop_duplicates(
        list(CLAVES_EVALUACION)
    )
    if not candidato_evaluable.empty and not universo.empty:
        extras = candidato_evaluable[list(CLAVES_EVALUACION)].merge(
            universo[list(CLAVES_EVALUACION)],
            on=list(CLAVES_EVALUACION),
            how="left",
            indicator=True,
        )
        n_extras = int(extras._merge.eq("left_only").sum())
        if n_extras:
            errores_contrato.append(
                {"regla": "candidato_fuera_del_universo", "afectados": n_extras}
            )
    keyset_sha = sha256_dataframe(universo, list(CLAVES_EVALUACION))
    if expected_keyset_sha256 and expected_keyset_sha256 != keyset_sha:
        errores_contrato.append(
            {
                "regla": "universo_inmutable",
                "esperado": expected_keyset_sha256,
                "observado": keyset_sha,
            }
        )
    calendario_sha = sha256_dataframe(
        macro_fuente[["semana_inicio", "semana_fin"]].drop_duplicates(),
        ["semana_inicio", "semana_fin"],
    )
    resultado: dict[str, Any] = {
        "schema_version": "candidate-preflight-v1",
        "campania": str(campania),
        "modelo": str(c.modelo.dropna().iloc[0])
        if "modelo" in c and c.modelo.notna().any()
        else None,
        "watermark_real": watermark,
        "watermark_fuente_real": watermark_fuente,
        "semana_parcial_excluida_filas": parciales,
        "horizontes_solicitados": list(horizontes),
        "horizontes_presentes": list(presentes),
        "baseline_run_ids": {k: int(v) for k, v in sorted(baseline_run_ids.items())},
        "keyset_sha256": keyset_sha,
        "closed_calendar_sha256": calendario_sha,
        "candidate_sha256": sha256_dataframe(
            c, [*CLAVES_EVALUACION, "modelo", "version_modelo", "p50_kg", "real_kg"]
        ),
        "contratos": errores_contrato,
        "gates": gates,
        "metricas": {},
        "baseline_hashes": {},
    }
    if errores_contrato:
        resultado.update({"estado": "contract_rejected", "exit_code": EXIT_CONTRACT_REJECTED})
        return _limpio_json(resultado)

    metricas_candidato = _metricas_modelo(universo, candidato_evaluable)
    resultado["metricas"]["candidato"] = metricas_candidato
    for modelo, b in sorted(baselines_n.items()):
        b = b[
            b.fecha_emision.isin(c.fecha_emision.unique())
            & b.horizonte_semanas.isin(horizontes)
            & b.fecha_objetivo.isin(universo.fecha_objetivo.unique())
        ].copy()
        huella = sha256_dataframe(b, [*CLAVES_EVALUACION, "modelo", "version_modelo", "p50_kg"])
        resultado["baseline_hashes"][modelo] = huella
        esperado = (hashes_esperados or {}).get(modelo)
        if esperado and esperado != huella:
            errores_contrato.append(
                {
                    "regla": "hash_baseline_inmutable",
                    "modelo": modelo,
                    "esperado": esperado,
                    "observado": huella,
                }
            )
        resultado["metricas"][modelo] = _metricas_modelo(universo, b)
    if errores_contrato:
        resultado["contratos"] = errores_contrato
        resultado.update({"estado": "contract_rejected", "exit_code": EXIT_CONTRACT_REJECTED})
        return _limpio_json(resultado)

    def gate(regla: str, valor: float, umbral: float, operador: str, pasa: bool, **extra):
        gates.append(
            {
                "regla": regla,
                "valor": valor,
                "umbral": umbral,
                "operador": operador,
                "pasa": bool(pasa),
                **extra,
            }
        )

    mc = metricas_candidato
    gate("wape_absoluto", mc["wape"], umbrales.wape_max, "<", mc["wape"] < umbrales.wape_max)
    gate(
        "sesgo_absoluto",
        abs(mc["sesgo"]),
        umbrales.sesgo_abs_max,
        "<=",
        abs(mc["sesgo"]) <= umbrales.sesgo_abs_max,
    )
    gate(
        "cobertura_volumen",
        mc["cobertura_volumen"],
        umbrales.cobertura_volumen_min,
        ">=",
        mc["cobertura_volumen"] >= umbrales.cobertura_volumen_min,
    )
    gate(
        "cobertura_lotes",
        mc["cobertura_lotes"],
        umbrales.cobertura_lotes_min,
        ">=",
        mc["cobertura_lotes"] >= umbrales.cobertura_lotes_min,
    )
    gate(
        "falsos_ceros_volumen",
        mc["falsos_ceros_volumen"],
        umbrales.falsos_ceros_volumen_max,
        "<=",
        mc["falsos_ceros_volumen"] <= umbrales.falsos_ceros_volumen_max,
    )
    macro = resultado["metricas"][modelo_macro]
    deterioro = (
        (mc["wape"] - macro["wape"]) / macro["wape"]
        if macro["wape"]
        else (0.0 if mc["wape"] == 0 else np.inf)
    )
    gate(
        "deterioro_global_macro",
        deterioro,
        umbrales.deterioro_macro_max,
        "<=",
        deterioro <= umbrales.deterioro_macro_max,
    )
    for horizonte in horizontes:
        clave = str(horizonte)
        if clave not in mc["por_horizonte"] or clave not in macro["por_horizonte"]:
            continue
        w_c = mc["por_horizonte"][clave]["wape"]
        w_m = macro["por_horizonte"][clave]["wape"]
        deterioro_h = (w_c - w_m) / w_m if w_m else (0.0 if w_c == 0 else np.inf)
        gate(
            "deterioro_horizonte_macro",
            deterioro_h,
            umbrales.deterioro_horizonte_max,
            "<=",
            deterioro_h <= umbrales.deterioro_horizonte_max,
            horizonte=horizonte,
        )
    rechazados = [g for g in gates if not g["pasa"]]
    resultado.update(
        {
            "estado": "passed" if not rechazados else "quality_rejected",
            "exit_code": EXIT_OK if not rechazados else EXIT_QUALITY_REJECTED,
            "gates": gates,
        }
    )
    return _limpio_json(resultado)


__all__ = ["evaluar_preflight"]

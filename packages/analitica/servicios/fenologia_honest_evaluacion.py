"""Métricas, selección, gates y ejecución del screening."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd
import psycopg

from analitica.settings import postgres_dsn

from .fenologia_honest_contratos import (
    RUNS_EXTERNOS,
    SEMANA_DESARROLLO_FINAL,
    SEMANA_INICIAL,
    SEMANAS_HOLDOUT,
    SQL_MACRO,
    TBASES,
    VENTANAS,
    Configuracion,
)
from .fenologia_honest_fuentes import (
    _leer_dataframe,
    agregar_curvas_fundo,
    construir_clima_asof,
    construir_fenologia_asof,
    preparar_clima,
    preparar_macro,
)
from .fenologia_honest_modelo import (
    aplicar_desplazamientos,
    calcular_desplazamientos,
    construir_panel_features,
)
from .fenologia_honest_salida import construir_resultado


def _filtro_scope(tabla: pd.DataFrame, scope: str) -> pd.Series:
    if scope == "h1":
        return tabla.horizonte_semanas.eq(1)
    if scope == "h2_6":
        return tabla.horizonte_semanas.between(2, 6)
    if scope == "h1_6":
        return tabla.horizonte_semanas.between(1, 6)
    raise ValueError(f"Scope desconocido: {scope}")


def metricas(
    tabla: pd.DataFrame,
    columna: str,
    *,
    split: str | tuple[str, ...],
    scope: str,
) -> dict[str, float | int]:
    splits = (split,) if isinstance(split, str) else split
    muestra = tabla[tabla.split.isin(splits) & _filtro_scope(tabla, scope)].copy()
    muestra = muestra[muestra.real_kg.notna() & muestra[columna].notna()]
    empresa = muestra.groupby(
        ["campania", "fecha_emision", "fecha_objetivo", "horizonte_semanas"],
        as_index=False,
    ).agg(real_kg=("real_kg", "sum"), pred_kg=(columna, "sum"))
    denominador = float(empresa.real_kg.abs().sum())
    errores = empresa.pred_kg - empresa.real_kg
    return {
        "n": int(len(empresa)),
        "wape": float(errores.abs().sum() / denominador) if denominador else np.nan,
        "bias_pct": float(errores.sum() / denominador) if denominador else np.nan,
        "mae_kg": float(errores.abs().mean()) if len(empresa) else np.nan,
        "real_kg": float(empresa.real_kg.sum()),
        "pred_kg": float(empresa.pred_kg.sum()),
    }


def metricas_por_fundo(
    tabla: pd.DataFrame, columna: str, *, split: str, scope: str
) -> dict[str, dict[str, float | int]]:
    salida: dict[str, dict[str, float | int]] = {}
    for fundo, bloque in tabla.groupby("fundo_operativo"):
        salida[str(fundo)] = metricas(bloque, columna, split=split, scope=scope)
    return salida


def _configuraciones() -> list[Configuracion]:
    coeficientes = (-1.0, -0.75, -0.5, -0.25, 0.25, 0.5, 0.75, 1.0)
    configs: list[Configuracion] = [Configuracion("sin_desplazamiento")]
    for variable in ("temp", "dpv", "eto"):
        for ventana in VENTANAS:
            for coef in coeficientes:
                configs.append(
                    Configuracion(
                        familia="clima_univariado",
                        variable_clima=variable,
                        ventana_dias=ventana,
                        coef_clima=coef,
                    )
                )
    for base in TBASES:
        for ventana in VENTANAS:
            for coef in coeficientes:
                configs.append(
                    Configuracion(
                        familia="gdd",
                        variable_clima="gdd",
                        tbase=base,
                        ventana_dias=ventana,
                        coef_clima=coef,
                    )
                )
    for variable in ("indice_estado", "prop_e45", "flores_por_planta", "tasa_cuajo"):
        for coef in coeficientes:
            configs.append(
                Configuracion(
                    familia="fenologia",
                    variable_fenologia=variable,
                    coef_fenologia=coef,
                )
            )
    # La combinación se mantiene deliberadamente pequeña: cada componente ya
    # compitió de forma univariada y no hay muestra independiente para justificar
    # cientos de interacciones.
    combinados = (-0.5, 0.5)
    for base in TBASES:
        for ventana in VENTANAS:
            for coef_gdd in combinados:
                for coef_fen in combinados:
                    configs.append(
                        Configuracion(
                            familia="gdd_mas_estado",
                            variable_clima="gdd",
                            tbase=base,
                            ventana_dias=ventana,
                            coef_clima=coef_gdd,
                            variable_fenologia="indice_estado",
                            coef_fenologia=coef_fen,
                        )
                    )
    return configs


def _resumen_config(
    curvas: pd.DataFrame,
    panel: pd.DataFrame,
    config: Configuracion,
    *,
    scope: str,
) -> tuple[dict[str, Any], dict[str, tuple[float, float]], pd.DataFrame]:
    desplazamientos, escalas = calcular_desplazamientos(panel, config)
    candidato = aplicar_desplazamientos(curvas, desplazamientos)
    temprano = metricas(candidato, "candidate_kg", split="desarrollo_temprano", scope=scope)
    tardio = metricas(candidato, "candidate_kg", split="desarrollo_tardio", scope=scope)
    macro_temprano = metricas(candidato, "macro_kg", split="desarrollo_temprano", scope=scope)
    macro_tardio = metricas(candidato, "macro_kg", split="desarrollo_tardio", scope=scope)
    wapes = np.asarray([temprano["wape"], tardio["wape"]], dtype=float)
    score = np.nanmean(wapes) if not np.isnan(wapes).all() else np.nan
    deterioro_max = max(
        float(temprano["wape"] - macro_temprano["wape"]),
        float(tardio["wape"] - macro_tardio["wape"]),
    )
    resumen = {
        "configuracion": asdict(config),
        "config_id": config.id,
        "scope": scope,
        "score_desarrollo": float(score),
        "deterioro_max_pp": float(deterioro_max),
        "desarrollo_temprano": temprano,
        "desarrollo_tardio": tardio,
        "macro_temprano": macro_temprano,
        "macro_tardio": macro_tardio,
    }
    return resumen, escalas, candidato


def seleccionar_configuracion(
    curvas: pd.DataFrame,
    panel: pd.DataFrame,
    *,
    scope: str,
    configuraciones: Iterable[Configuracion] | None = None,
) -> tuple[Configuracion, dict[str, tuple[float, float]], list[dict[str, Any]]]:
    """Selecciona solo con S13-S30; nunca consulta el holdout ni R09."""

    resultados: list[tuple[dict[str, Any], Configuracion, dict[str, tuple[float, float]]]] = []
    for config in configuraciones or _configuraciones():
        resumen, escalas, _ = _resumen_config(curvas, panel, config, scope=scope)
        resultados.append((resumen, config, escalas))
    resultados.sort(
        key=lambda item: (
            item[0]["deterioro_max_pp"] > 0.05,
            item[0]["score_desarrollo"],
            item[0]["deterioro_max_pp"],
            item[0]["config_id"],
        )
    )
    mejor_resumen, mejor_config, mejores_escalas = resultados[0]
    top = [fila[0] for fila in resultados[:20]]
    if mejor_resumen["deterioro_max_pp"] > 0.05:
        mejor_config = Configuracion("sin_desplazamiento")
        _, mejores_escalas, _ = _resumen_config(curvas, panel, mejor_config, scope=scope)
    return mejor_config, mejores_escalas, top


def evaluar_gates(
    candidato: pd.DataFrame,
    *,
    scope: str,
    cobertura_minima: float = 0.80,
) -> dict[str, Any]:
    macro = metricas(candidato, "macro_kg", split="holdout_s31_s33", scope=scope)
    nuevo = metricas(candidato, "candidate_kg", split="holdout_s31_s33", scope=scope)
    filas_holdout = candidato[
        candidato.split.eq("holdout_s31_s33") & _filtro_scope(candidato, scope)
    ]
    cobertura = (
        float(
            filas_holdout[["fecha_emision", "fundo_operativo", "feature_usable"]]
            .drop_duplicates()
            .feature_usable.mean()
        )
        if len(filas_holdout)
        else 0.0
    )
    macro_fundos = metricas_por_fundo(candidato, "macro_kg", split="holdout_s31_s33", scope=scope)
    candidato_fundos = metricas_por_fundo(
        candidato, "candidate_kg", split="holdout_s31_s33", scope=scope
    )
    deterioros = {
        fundo: (
            float(candidato_fundos[fundo]["wape"] / valores["wape"] - 1.0)
            if valores["wape"] and np.isfinite(valores["wape"])
            else np.nan
        )
        for fundo, valores in macro_fundos.items()
    }
    mejora_relativa = (
        float((macro["wape"] - nuevo["wape"]) / macro["wape"])
        if macro["wape"] and np.isfinite(macro["wape"])
        else np.nan
    )
    razones: list[str] = []
    if cobertura < cobertura_minima:
        razones.append(f"cobertura temporal {cobertura:.1%} < {cobertura_minima:.0%}")
    if not np.isfinite(mejora_relativa) or mejora_relativa < 0.02:
        razones.append("mejora holdout <2% frente a Macro")
    if abs(float(nuevo["bias_pct"])) > 0.15:
        razones.append("|sesgo holdout| >15%")
    peores = [f for f, valor in deterioros.items() if np.isfinite(valor) and valor > 0.10]
    if peores:
        razones.append("deteriora >10% los fundos: " + ", ".join(peores))
    return {
        "scope": scope,
        "macro": macro,
        "candidato": nuevo,
        "mejora_relativa": mejora_relativa,
        "cobertura_feature": cobertura,
        "por_fundo_macro": macro_fundos,
        "por_fundo_candidato": candidato_fundos,
        "deterioro_relativo_por_fundo": deterioros,
        "aceptado": not razones,
        "razones_rechazo": razones,
    }


def _cobertura_fuentes(panel: pd.DataFrame) -> dict[str, Any]:
    salida: dict[str, Any] = {}
    for split, bloque in panel.groupby(
        np.select(
            [
                panel.semana_h1.between(SEMANA_INICIAL, SEMANA_DESARROLLO_FINAL),
                panel.semana_h1.isin(SEMANAS_HOLDOUT),
            ],
            ["desarrollo", "holdout"],
            default="fuera",
        )
    ):
        if split == "fuera":
            continue
        salida[split] = {
            "emision_fundo": int(len(bloque)),
            "clima": {
                f"{ventana}d": float(bloque[f"clima_cobertura_{ventana}d"].ge(0.80).mean())
                for ventana in VENTANAS
            },
            "estados": float(bloque.cobertura_estados.ge(0.30).mean()),
            "flores": float(bloque.cobertura_flores.ge(0.30).mean()),
            "mediana_cobertura_lotes_estados": float(bloque.cobertura_estados.median()),
            "mediana_cobertura_lotes_flores": float(bloque.cobertura_flores.median()),
        }
    return salida


def _evaluar_externa(
    config: Configuracion,
    escalas: dict[str, tuple[float, float]],
    *,
    scope: str,
    clima: pd.DataFrame,
    estados: pd.DataFrame,
    flores: pd.DataFrame,
) -> dict[str, Any]:
    resultados: dict[str, Any] = {}
    for campania, run_id in RUNS_EXTERNOS.items():
        with psycopg.connect(postgres_dsn(), connect_timeout=8) as conexion:
            conexion.execute("SET TRANSACTION READ ONLY")
            with conexion.cursor() as cursor:
                macro = _leer_dataframe(cursor, SQL_MACRO, (run_id, campania))
        try:
            base = preparar_macro(macro, campania=campania, limitar_c2026=False)
        except ValueError as exc:
            resultados[campania] = {"evaluable": False, "razon": str(exc)}
            continue
        base = base[base.real_kg.notna()].copy()
        if base.empty:
            resultados[campania] = {"evaluable": False, "razon": "sin reales"}
            continue
        emisiones = base.fecha_emision.unique()
        dimension = base[["lote_id", "fundo_operativo"]].drop_duplicates()
        clima_asof = construir_clima_asof(emisiones, clima)
        fen_asof = construir_fenologia_asof(emisiones, dimension, estados, flores)
        panel = construir_panel_features(base, clima_asof, fen_asof)
        desplazamientos, _ = calcular_desplazamientos(panel, config, escalas=escalas)
        curvas = agregar_curvas_fundo(base)
        candidato = aplicar_desplazamientos(curvas, desplazamientos)
        macro_m = metricas(candidato, "macro_kg", split="externa", scope=scope)
        nuevo_m = metricas(candidato, "candidate_kg", split="externa", scope=scope)
        cobertura = float(desplazamientos.feature_usable.mean())
        mejora = (
            float((macro_m["wape"] - nuevo_m["wape"]) / macro_m["wape"])
            if macro_m["wape"]
            else np.nan
        )
        resultados[campania] = {
            "evaluable": cobertura >= 0.80 and macro_m["n"] >= 12,
            "cobertura_feature": cobertura,
            "macro": macro_m,
            "candidato": nuevo_m,
            "mejora_relativa": mejora,
            "razon": (
                None
                if cobertura >= 0.80 and macro_m["n"] >= 12
                else "cobertura temporal <80% o menos de 12 predicciones agregadas"
            ),
        }
    return resultados


def evaluar(
    macro: pd.DataFrame,
    clima: pd.DataFrame,
    estados: pd.DataFrame,
    flores: pd.DataFrame,
    *,
    evaluar_externas: bool = True,
) -> dict[str, Any]:
    base = preparar_macro(macro)
    diario = preparar_clima(clima)
    emisiones = base.fecha_emision.unique()
    dimension = base[["lote_id", "fundo_operativo"]].drop_duplicates()
    clima_asof = construir_clima_asof(emisiones, diario)
    fen_asof = construir_fenologia_asof(emisiones, dimension, estados, flores)
    panel = construir_panel_features(base, clima_asof, fen_asof)
    curvas = agregar_curvas_fundo(base)

    salidas_scope: dict[str, Any] = {}
    for scope in ("h1", "h2_6"):
        config, escalas, top = seleccionar_configuracion(curvas, panel, scope=scope)
        desplazamientos, _ = calcular_desplazamientos(panel, config, escalas=escalas)
        candidato = aplicar_desplazamientos(curvas, desplazamientos)
        gates = evaluar_gates(candidato, scope=scope)
        externas = (
            _evaluar_externa(
                config,
                escalas,
                scope=scope,
                clima=diario,
                estados=estados,
                flores=flores,
            )
            if evaluar_externas and config.familia != "sin_desplazamiento"
            else {}
        )
        externas_validas = [v for v in externas.values() if v.get("evaluable")]
        mejora_externa = sum(v.get("mejora_relativa", -np.inf) > 0 for v in externas_validas)
        admitido = bool(gates["aceptado"] and len(externas_validas) >= 2 and mejora_externa >= 2)
        razones = list(gates["razones_rechazo"])
        if gates["aceptado"] and not admitido:
            razones.append("no mejora en dos campañas externas con cobertura suficiente")
        salidas_scope[scope] = {
            "configuracion_seleccionada": asdict(config),
            "config_id": config.id,
            "escalas_entrenamiento": escalas,
            "top_desarrollo": top,
            "holdout": gates,
            "campanias_externas": externas,
            "admitido_para_modelo": admitido,
            "razones_rechazo_final": razones,
        }

    return construir_resultado(
        base,
        diario,
        fen_asof,
        estados,
        flores,
        _cobertura_fuentes(panel),
        salidas_scope,
    )

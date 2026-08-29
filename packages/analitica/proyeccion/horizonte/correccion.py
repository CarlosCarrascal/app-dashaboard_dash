"""Normalización y corrección residual as-of por horizonte."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from .contratos import CLAVES, ConfiguracionCorreccionHorizonte


def normalizar_panel(tabla: pd.DataFrame) -> pd.DataFrame:
    """Valida el contrato sin convertir resultados desconocidos a cero."""

    requeridas = set(CLAVES) | {"fundo", "modulo", "p50_kg", "real_kg"}
    faltantes = sorted(requeridas.difference(tabla.columns))
    if faltantes:
        raise ValueError(f"Faltan columnas para corrección de horizonte: {faltantes}")
    t = tabla.copy()
    for columna in ("fecha_emision", "fecha_objetivo"):
        t[columna] = pd.to_datetime(t[columna], errors="raise").dt.normalize()
    horizonte = pd.to_numeric(t["horizonte_semanas"], errors="raise")
    if not np.isfinite(horizonte).all() or not horizonte.eq(horizonte.round()).all():
        raise ValueError("horizonte_semanas debe contener enteros finitos")
    t["horizonte_semanas"] = horizonte.astype(int)
    t["p50_kg"] = pd.to_numeric(t["p50_kg"], errors="coerce")
    t["real_kg"] = pd.to_numeric(t["real_kg"], errors="coerce")
    if t["p50_kg"].isna().any() or t["p50_kg"].lt(0).any():
        raise ValueError("p50_kg debe ser numérico, conocido y no negativo")
    if t.duplicated(list(CLAVES)).any():
        raise ValueError("El panel repite campaña, emisión, objetivo, horizonte y lote")
    if t["fecha_emision"].ge(t["fecha_objetivo"]).any():
        raise ValueError("Hay una emisión contemporánea o posterior al objetivo")
    t["semana_cierre"] = t["fecha_objetivo"] + pd.Timedelta(days=6)
    t["fundo"] = t["fundo"].fillna("__sin_fundo__").astype(str)
    t["modulo"] = t["modulo"].fillna("__sin_modulo__").astype(str)
    return t.sort_values(["campania", "fecha_emision", "fecha_objetivo", "lote_id"])


def _promedio_robusto(valores: pd.Series) -> float:
    x = pd.to_numeric(valores, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if x.empty:
        return 0.0
    mediana = float(x.median())
    mad = float(np.median(np.abs(x.to_numpy(float) - mediana)))
    if mad > 0:
        x = x[np.abs(x - mediana) <= 4.0 * 1.4826 * mad]
    return float(x.median()) if len(x) else mediana


def _historial_canonico(
    panel: pd.DataFrame, config: ConfiguracionCorreccionHorizonte
) -> pd.DataFrame:
    """Obtiene un error por objetivo usando una sola emisión previa por lote."""

    observadas = panel.loc[panel["real_kg"].notna()].copy()
    observadas = observadas.loc[observadas["fecha_emision"].lt(observadas["fecha_objetivo"])]
    # Si una misma semana fue emitida varias veces, se toma la última emisión
    # estrictamente anterior al objetivo, igual que la decisión operativa.
    observadas = observadas.sort_values("fecha_emision").drop_duplicates(
        ["campania", "lote_id", "fecha_objetivo", "horizonte_semanas"],
        keep="last",
    )
    dimensiones = ["campania", "fecha_objetivo", "horizonte_semanas"]
    if config.nivel == "fundo":
        dimensiones.append("fundo")
    elif config.nivel == "modulo":
        dimensiones.extend(["fundo", "modulo"])
    historico = observadas.groupby(dimensiones, as_index=False, dropna=False).agg(
        pred_kg=("p50_kg", "sum"), real_kg=("real_kg", "sum")
    )
    valido = historico["pred_kg"].gt(0) | historico["real_kg"].gt(0)
    historico = historico.loc[valido].copy()
    historico["residuo_log"] = np.log1p(historico["real_kg"].clip(lower=0)) - np.log1p(
        historico["pred_kg"].clip(lower=0)
    )
    historico["semana_cierre"] = historico["fecha_objetivo"] + pd.Timedelta(days=6)
    return historico


def _factor_para_fila(
    historico: pd.DataFrame,
    fila: pd.Series,
    config: ConfiguracionCorreccionHorizonte,
) -> tuple[float, int, str]:
    """Calcula el factor con datos cerrados antes de la emisión de ``fila``."""

    if config.nivel == "ninguno":
        global_h = historico
    else:
        global_h = historico.drop(columns=[c for c in ("fundo", "modulo") if c in historico])
    mascara_global = global_h["campania"].astype(str).eq(str(fila["campania"])) & global_h[
        "semana_cierre"
    ].lt(fila["fecha_emision"])
    if config.por_horizonte:
        mascara_global &= global_h["horizonte_semanas"].eq(int(fila["horizonte_semanas"]))
    global_h = global_h.loc[mascara_global].sort_values("fecha_objetivo").tail(config.ventana)

    local = pd.DataFrame()
    if config.nivel == "fundo":
        mascara_local = (
            historico["campania"].astype(str).eq(str(fila["campania"]))
            & historico["fundo"].eq(str(fila["fundo"]))
            & historico["semana_cierre"].lt(fila["fecha_emision"])
        )
        if config.por_horizonte:
            mascara_local &= historico["horizonte_semanas"].eq(int(fila["horizonte_semanas"]))
        local = historico.loc[mascara_local].sort_values("fecha_objetivo").tail(config.ventana)
    elif config.nivel == "modulo":
        mascara_local = (
            historico["campania"].astype(str).eq(str(fila["campania"]))
            & historico["fundo"].eq(str(fila["fundo"]))
            & historico["modulo"].eq(str(fila["modulo"]))
            & historico["semana_cierre"].lt(fila["fecha_emision"])
        )
        if config.por_horizonte:
            mascara_local &= historico["horizonte_semanas"].eq(int(fila["horizonte_semanas"]))
        local = historico.loc[mascara_local].sort_values("fecha_objetivo").tail(config.ventana)

    n_global = len(global_h)
    if n_global == 0:
        return 1.0, 0, "sin_historia"
    log_global = _promedio_robusto(global_h["residuo_log"])
    if config.nivel == "ninguno" or len(local) < config.minimo_observaciones:
        return (
            float(np.clip(np.exp(log_global), config.factor_min, config.factor_max)),
            n_global,
            "global",
        )

    log_local = _promedio_robusto(local["residuo_log"])
    peso_local = len(local) / (len(local) + config.regularizacion)
    log_factor = peso_local * log_local + (1 - peso_local) * log_global
    return (
        float(np.clip(np.exp(log_factor), config.factor_min, config.factor_max)),
        len(local),
        config.nivel,
    )


def aplicar_correccion_horizonte(
    panel: pd.DataFrame,
    config: ConfiguracionCorreccionHorizonte | None = None,
    *,
    panel_historial: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Devuelve un candidato sin persistir y sin tocar el baseline."""

    config = config or ConfiguracionCorreccionHorizonte()
    base = normalizar_panel(panel)
    historial_base = normalizar_panel(panel_historial) if panel_historial is not None else base
    if config.nivel == "ninguno" and config.peso_correccion == 0:
        return _aplicar_normalizado(base, config)
    reducido_historial = historial_base
    return _aplicar_normalizado(
        base, config, historico=_historial_canonico(reducido_historial, config)
    )


def _aplicar_normalizado(
    base: pd.DataFrame,
    config: ConfiguracionCorreccionHorizonte,
    historico: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Evita normalizar y construir el historial en cada candidato."""

    if config.nivel == "ninguno" and config.peso_correccion == 0:
        salida = base.copy()
        salida["pred_kg"] = salida["p50_kg"]
        salida["factor_horizonte_asof"] = 1.0
        salida["n_calibracion_asof"] = 0
        salida["nivel_calibracion_horizonte"] = "sin_correccion"
        salida["configuracion_horizonte"] = [asdict(config)] * len(salida)
        return salida

    historico = historico if historico is not None else _historial_canonico(base, config)
    dimensiones_factor = ["campania", "fecha_emision", "horizonte_semanas"]
    if config.nivel == "fundo":
        dimensiones_factor.append("fundo")
    elif config.nivel == "modulo":
        dimensiones_factor.extend(["fundo", "modulo"])
    grupos_factor = base[dimensiones_factor].drop_duplicates().reset_index(drop=True)
    factores: list[dict[str, Any]] = []
    # El factor sólo cambia por emisión, horizonte y nivel de calibración; no por
    # cada lote. Esto mantiene el screening en segundos aun con cientos de miles
    # de filas de predicción.
    for _, fila in grupos_factor.iterrows():
        factor, n, nivel = _factor_para_fila(historico, fila, config)
        factores.append(
            {
                **{columna: fila[columna] for columna in dimensiones_factor},
                "factor_horizonte_asof": factor,
                "n_calibracion_asof": n,
                "nivel_calibracion_horizonte": nivel,
            }
        )
    salida = base.merge(
        pd.DataFrame(factores),
        on=dimensiones_factor,
        how="left",
        validate="many_to_one",
    )
    # La corrección es multiplicativa sobre la curva base. No usamos log1p
    # para no crear kilos cuando la predicción legacy es exactamente cero:
    # 0 kg × cualquier factor sigue siendo 0 kg.
    factor = np.exp(
        np.log(salida["factor_horizonte_asof"].clip(lower=1e-12)) * float(config.peso_correccion)
    )
    salida["pred_kg"] = (salida["p50_kg"] * factor).clip(lower=0.0)
    salida["configuracion_horizonte"] = [asdict(config)] * len(salida)
    return salida

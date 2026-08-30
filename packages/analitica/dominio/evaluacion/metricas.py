"""Métricas de punto, escala e intervalo para backtesting temporal."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd


def _pares(real, pred) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(real, dtype=float)
    p = np.asarray(pred, dtype=float)
    ok = np.isfinite(y) & np.isfinite(p)
    return y[ok], p[ok]


def mae(real, pred) -> float:
    y, p = _pares(real, pred)
    return float(np.mean(np.abs(y - p))) if len(y) else np.nan


def wape(real, pred) -> float:
    y, p = _pares(real, pred)
    denominador = np.abs(y).sum()
    return float(np.abs(y - p).sum() / denominador) if denominador > 0 else np.nan


def sesgo(real, pred) -> float:
    y, p = _pares(real, pred)
    denominador = np.abs(y).sum()
    return float((p - y).sum() / denominador) if denominador > 0 else np.nan


def metricas_cobertura_operacional(tabla: pd.DataFrame) -> dict[str, float | int]:
    """Separa error matemático de ausencia de una emisión.

    ``emitio_prediccion`` debe ser falso cuando la rejilla común contiene un
    lote-semana para el que la fuente no publicó valor. El WAPE operacional lo
    penaliza como cero; el condicionado evalúa únicamente las filas emitidas.
    """

    if tabla.empty:
        return {
            "wape_operacional": np.nan,
            "wape_condicionado": np.nan,
            "cobertura_lotes": np.nan,
            "cobertura_volumen": np.nan,
            "filas_evaluadas": 0,
            "filas_emitidas": 0,
        }
    t = tabla.copy()
    t["real_kg"] = pd.to_numeric(t["real_kg"], errors="coerce").fillna(0.0)
    t["p50_kg"] = pd.to_numeric(t["p50_kg"], errors="coerce").fillna(0.0)
    emitio = t.get("emitio_prediccion", pd.Series(True, index=t.index)).fillna(False).astype(bool)
    total_real = float(t["real_kg"].abs().sum())
    condicionado = t.loc[emitio]
    lotes_total = int(t["lote_id"].nunique()) if "lote_id" in t else len(t)
    lotes_emitidos = (
        int(condicionado["lote_id"].nunique()) if "lote_id" in condicionado else len(condicionado)
    )
    return {
        "wape_operacional": wape(t["real_kg"], t["p50_kg"]),
        "wape_condicionado": wape(condicionado["real_kg"], condicionado["p50_kg"]),
        "cobertura_lotes": float(lotes_emitidos / lotes_total) if lotes_total else np.nan,
        "cobertura_volumen": (
            float(condicionado["real_kg"].abs().sum() / total_real) if total_real else np.nan
        ),
        "filas_evaluadas": int(len(t)),
        "filas_emitidas": int(emitio.sum()),
    }


def r2(real, pred) -> float:
    y, p = _pares(real, pred)
    if len(y) < 2 or np.allclose(y, y.mean()):
        return np.nan
    return float(1 - np.square(y - p).sum() / np.square(y - y.mean()).sum())


def _escala_naive(tabla: pd.DataFrame, cuadratica: bool = False, columna: str = "real_kg") -> float:
    """Error del método más simple: repetir el valor de la semana anterior de esa serie.

    `columna` se parametriza para poder escalar también las métricas de los componentes
    (frutos por planta, peso de baya) con su propia serie observada; por omisión mantiene
    el comportamiento sobre kilos.
    """
    if columna not in tabla:
        return np.nan
    diferencias: list[float] = []
    for _, grupo in tabla.sort_values("fecha_objetivo").groupby("serie_id", dropna=False):
        valores = grupo.drop_duplicates("fecha_objetivo")[columna].dropna().to_numpy(float)
        if len(valores) > 1:
            delta = np.diff(valores)
            diferencias.extend(np.square(delta) if cuadratica else np.abs(delta))
    if not diferencias:
        return np.nan
    base = float(np.mean(diferencias))
    return np.sqrt(base) if cuadratica else base


def pinball(real, pred, cuantil: float) -> float:
    y, p = _pares(real, pred)
    error = y - p
    return float(np.mean(np.maximum(cuantil * error, (cuantil - 1) * error))) if len(y) else np.nan


def cobertura(real, inferior, superior) -> float:
    y = np.asarray(real, dtype=float)
    lo = np.asarray(inferior, dtype=float)
    hi = np.asarray(superior, dtype=float)
    ok = np.isfinite(y) & np.isfinite(lo) & np.isfinite(hi)
    return float(np.mean((y[ok] >= lo[ok]) & (y[ok] <= hi[ok]))) if ok.any() else np.nan


def interval_score(real, inferior, superior, alpha: float = 0.2) -> float:
    y = np.asarray(real, dtype=float)
    lo = np.asarray(inferior, dtype=float)
    hi = np.asarray(superior, dtype=float)
    ok = np.isfinite(y) & np.isfinite(lo) & np.isfinite(hi)
    if not ok.any():
        return np.nan
    y, lo, hi = y[ok], lo[ok], hi[ok]
    score = hi - lo
    score += (2 / alpha) * (lo - y) * (y < lo)
    score += (2 / alpha) * (y - hi) * (y > hi)
    return float(score.mean())


def _metricas_componentes(g: pd.DataFrame) -> dict[str, float]:
    """Error de frutos por planta y de peso de baya, cada uno con su propio denominador.

    Dos cuidados que no son opcionales:

    1. **La base de plantas.** `frutos_reales_por_planta` se despeja sobre las plantas
       cosechadas y `frutos_reales_por_planta_catalogo` sobre las del maestro. Un modelo
       que predice sobre catálogo debe compararse contra la serie de catálogo; si no, la
       métrica recoge la diferencia entre ambas definiciones y no el error del modelo. La
       columna `base_plantas` de cada fila declara cuál corresponde.
    2. **El sesgo, no solo la magnitud.** Un modelo puede acertar los kilos con muchos
       frutos pequeños o pocos frutos grandes. Solo el sesgo por componente distingue el
       acierto real de la compensación entre dos errores de signo contrario.
    """
    base = "catalogo"
    if "base_plantas" in g and g.base_plantas.notna().any():
        base = str(g.base_plantas.dropna().iloc[0])
    columna_frutos = (
        "frutos_reales_por_planta_catalogo" if base == "catalogo" else "frutos_reales_por_planta"
    )
    if columna_frutos not in g:
        columna_frutos = "frutos_reales_por_planta"

    salida: dict[str, float] = {"base_plantas_evaluada": base}
    for prefijo, real, pred in (
        ("frutos_por_planta", columna_frutos, "frutos_por_planta"),
        ("peso_baya_g", "peso_real_g", "peso_baya_g"),
    ):
        if {real, pred} - set(g):
            salida.update(
                {
                    f"mae_{prefijo}": np.nan,
                    f"wape_{prefijo}": np.nan,
                    f"sesgo_pct_{prefijo}": np.nan,
                    f"mase_{prefijo}": np.nan,
                    f"n_{prefijo}": 0,
                }
            )
            continue
        pares = g[[real, pred, "serie_id", "fecha_objetivo"]].dropna(subset=[real, pred])
        escala = _escala_naive(pares.rename(columns={real: "real_kg"}))
        error = np.abs(pares[real] - pares[pred])
        salida.update(
            {
                f"mae_{prefijo}": float(error.mean()) if len(pares) else np.nan,
                f"wape_{prefijo}": wape(pares[real], pares[pred]),
                f"sesgo_pct_{prefijo}": 100 * sesgo(pares[real], pares[pred]),
                f"mase_{prefijo}": (
                    float(error.mean() / escala) if escala and escala > 0 else np.nan
                ),
                f"n_{prefijo}": len(pares),
            }
        )

    # Cuánto se aparta el kg publicado del producto de las tres piezas. Cerca de cero
    # significa que la fila reconstruye su propia identidad; grande, que los componentes
    # que acompañan a esa predicción no son los que la produjeron.
    salida["residuo_identidad_pct"] = np.nan
    if {"plantas", "frutos_por_planta", "peso_baya_g", "p50_kg"} <= set(g):
        producto = g.plantas * g.frutos_por_planta * g.peso_baya_g / 1000
        if "probabilidad_cosecha" in g:
            producto = producto * pd.to_numeric(g.probabilidad_cosecha, errors="coerce")
        denominador = g.p50_kg.abs().clip(lower=1)
        residuo = (producto - g.p50_kg).abs() / denominador
        if residuo.notna().any():
            salida["residuo_identidad_pct"] = float(100 * residuo.mean())
    return salida


def metricas_pronostico(tabla: pd.DataFrame) -> pd.DataFrame:
    """Una fila por modelo y segmento; todas las métricas usan las mismas observaciones."""
    if tabla.empty:
        return pd.DataFrame()
    t = tabla.copy()
    if "serie_id" in t:
        serie = t["serie_id"]
    elif "lote" in t:
        serie = t["lote"]
    else:
        serie = pd.Series("TOTAL", index=t.index)
    t["serie_id"] = serie.fillna("TOTAL").astype(str)
    grupos = ["modelo", "banda_horizonte"]
    filas = []
    for claves, g in t.groupby(grupos, dropna=False):
        g = g.dropna(subset=["real_kg", "p50_kg"])
        if g.empty:
            continue
        escala_abs = _escala_naive(g)
        escala_rms = _escala_naive(g, cuadratica=True)
        error_abs = np.abs(g.real_kg - g.p50_kg)
        rmse = float(np.sqrt(np.mean(np.square(g.real_kg - g.p50_kg))))
        error_plantas = (
            np.abs(g.plantas_reales - g.plantas).mean()
            if {"plantas_reales", "plantas"} <= set(g)
            else np.nan
        )
        componentes = _metricas_componentes(g)
        filas.append(
            {
                "modelo": claves[0],
                "banda_horizonte": claves[1],
                "n": len(g),
                "volumen_real_kg": float(g.real_kg.sum()),
                "wape": wape(g.real_kg, g.p50_kg),
                "mae_kg": mae(g.real_kg, g.p50_kg),
                "sesgo_pct": 100 * sesgo(g.real_kg, g.p50_kg),
                "mase": (
                    float(error_abs.mean() / escala_abs)
                    if escala_abs and escala_abs > 0
                    else np.nan
                ),
                "rmsse": float(rmse / escala_rms) if escala_rms and escala_rms > 0 else np.nan,
                "r2": r2(g.real_kg, g.p50_kg),
                "pinball_p10": pinball(g.real_kg, g.p10_kg, 0.1),
                "pinball_p50": pinball(g.real_kg, g.p50_kg, 0.5),
                "pinball_p90": pinball(g.real_kg, g.p90_kg, 0.9),
                "cobertura_80": cobertura(g.real_kg, g.p10_kg, g.p90_kg),
                "ancho_intervalo_kg": float((g.p90_kg - g.p10_kg).mean()),
                "interval_score_80": interval_score(g.real_kg, g.p10_kg, g.p90_kg),
                "mae_plantas": float(error_plantas),
                **componentes,
            }
        )
    return pd.DataFrame(filas)


def metricas_pareadas_modelos(
    tabla: pd.DataFrame,
    *,
    modelo_base: str,
    modelo_candidato: str,
) -> pd.DataFrame:
    """Mide dos modelos sobre exactamente los mismos cortes, lotes y semanas."""

    if tabla.empty:
        return pd.DataFrame()
    claves = [c for c in ("campania", "lote_id", "fecha_emision", "fecha_objetivo") if c in tabla]
    if len(claves) < 3:
        raise ValueError("La comparación pareada necesita campaña/lote/emisión/objetivo")
    base = tabla[tabla.modelo.eq(modelo_base)].copy()
    candidato = tabla[tabla.modelo.eq(modelo_candidato)].copy()
    for nombre, parte in ((modelo_base, base), (modelo_candidato, candidato)):
        if parte.duplicated(claves).any():
            raise ValueError(f"{nombre} repite claves dentro del universo comparable")
    comunes = (
        base[claves]
        .drop_duplicates()
        .merge(candidato[claves].drop_duplicates(), on=claves, how="inner")
    )
    if comunes.empty:
        return pd.DataFrame()
    reales = base[claves + ["real_kg"]].merge(
        candidato[claves + ["real_kg"]],
        on=claves,
        how="inner",
        suffixes=("_base", "_candidato"),
    )
    # La verdad observada pertenece al lote-semana, no al modelo. La rejilla del
    # challenger explicita los ceros sin cosecha que R09 puede dejar nulos; usar una
    # única serie real evita que dos modelos supuestamente pareados terminen con n y
    # volumen distintos.
    reales["real_comun_kg"] = reales.real_kg_candidato.combine_first(reales.real_kg_base)
    reales = reales[claves + ["real_comun_kg"]].dropna(subset=["real_comun_kg"])
    base = base.merge(reales, on=claves, how="inner")
    candidato = candidato.merge(reales, on=claves, how="inner")
    base["real_kg"] = base.pop("real_comun_kg")
    candidato["real_kg"] = candidato.pop("real_comun_kg")
    pareadas = pd.concat([base, candidato], ignore_index=True, sort=False)
    metricas = metricas_pronostico(pareadas)
    if metricas.empty:
        return metricas
    metricas["modelo_base"] = modelo_base
    metricas["universo"] = "mismo run, emision, lote y semana objetivo"
    columnas = [
        "modelo_base",
        "modelo",
        "banda_horizonte",
        "n",
        "wape",
        "mase",
        "mae_kg",
        "sesgo_pct",
        "cobertura_80",
        "volumen_real_kg",
        "universo",
    ]
    return metricas[[c for c in columnas if c in metricas]]


def bootstrap_bloques(
    tabla: pd.DataFrame,
    metrica: Callable[[pd.Series, pd.Series], float] = wape,
    repeticiones: int = 500,
    longitud_bloque: int = 3,
    semilla: int = 0,
) -> tuple[float, float]:
    """IC percentil re-muestreando bloques contiguos de fechas de emisión."""
    fechas = np.array(sorted(pd.to_datetime(tabla.fecha_emision.dropna().unique())))
    if len(fechas) < 3:
        return np.nan, np.nan
    bloques = [
        fechas[i : i + longitud_bloque] for i in range(max(1, len(fechas) - longitud_bloque + 1))
    ]
    rng = np.random.default_rng(semilla)
    valores = []
    for _ in range(repeticiones):
        muestra = np.concatenate(
            [
                bloques[i]
                for i in rng.integers(
                    0, len(bloques), size=int(np.ceil(len(fechas) / longitud_bloque))
                )
            ]
        )[: len(fechas)]
        partes = [tabla[tabla.fecha_emision == fecha] for fecha in muestra]
        boot = pd.concat(partes, ignore_index=True)
        valores.append(metrica(boot.real_kg, boot.p50_kg))
    return tuple(map(float, np.quantile(valores, [0.025, 0.975])))


def bootstrap_diferencia_wape_pareada(
    predicciones: pd.DataFrame,
    candidato: str,
    *,
    base: str = "R09_publicado",
    repeticiones: int = 500,
    longitud_bloque: int = 3,
    semilla: int = 42,
) -> tuple[float, float]:
    """IC de ``WAPE(candidato) - WAPE(base)`` preservando bloques de emisión.

    La tabla debe contener únicamente claves comparables. Un intervalo completamente bajo
    cero respalda una mejora; un intervalo que cruza cero comunica incertidumbre del ranking.
    """
    claves = ["campania", "lote_id", "fecha_emision", "fecha_objetivo"]
    necesarias = {*claves, "modelo", "real_kg", "p50_kg"}
    if predicciones.empty or not necesarias <= set(predicciones):
        return np.nan, np.nan
    t = predicciones[predicciones.modelo.isin([base, candidato])].copy()
    reales = t.drop_duplicates(claves).set_index(claves).real_kg.rename("real_kg")
    ancha = t.pivot_table(index=claves, columns="modelo", values="p50_kg", aggfunc="first")
    if base not in ancha or candidato not in ancha:
        return np.nan, np.nan
    pares = ancha[[base, candidato]].join(reales).dropna()
    if pares.empty:
        return np.nan, np.nan
    fechas = np.array(sorted(pares.index.get_level_values("fecha_emision").unique()))
    if len(fechas) < 3:
        return np.nan, np.nan
    por_fecha = {
        fecha: (
            grupo.real_kg.to_numpy(float),
            grupo[base].to_numpy(float),
            grupo[candidato].to_numpy(float),
        )
        for fecha, grupo in pares.reset_index().groupby("fecha_emision")
    }
    bloques = [
        fechas[i : i + longitud_bloque] for i in range(max(1, len(fechas) - longitud_bloque + 1))
    ]
    rng = np.random.default_rng(semilla)
    diferencias = []
    for _ in range(repeticiones):
        muestra = np.concatenate(
            [
                bloques[i]
                for i in rng.integers(
                    0, len(bloques), size=int(np.ceil(len(fechas) / longitud_bloque))
                )
            ]
        )[: len(fechas)]
        reales_b = np.concatenate([por_fecha[fecha][0] for fecha in muestra])
        base_b = np.concatenate([por_fecha[fecha][1] for fecha in muestra])
        cand_b = np.concatenate([por_fecha[fecha][2] for fecha in muestra])
        diferencias.append(wape(reales_b, cand_b) - wape(reales_b, base_b))
    return tuple(map(float, np.quantile(diferencias, [0.025, 0.975])))


def porcentaje_series_ganadas(
    predicciones: pd.DataFrame,
    candidato: str,
    *,
    base: str = "R09_publicado",
) -> float:
    """Fracción de campaña-lotes donde el WAPE del candidato vence al baseline."""
    claves = ["campania", "lote_id", "fecha_emision", "fecha_objetivo"]
    t = predicciones[predicciones.modelo.isin([base, candidato])].copy()
    if t.empty:
        return np.nan
    reales = t.drop_duplicates(claves).set_index(claves).real_kg.rename("real_kg")
    ancha = t.pivot_table(index=claves, columns="modelo", values="p50_kg", aggfunc="first")
    if base not in ancha or candidato not in ancha:
        return np.nan
    pares = ancha[[base, candidato]].join(reales).dropna().reset_index()
    resultados = []
    for _, grupo in pares.groupby(["campania", "lote_id"], dropna=False):
        resultados.append(wape(grupo.real_kg, grupo[candidato]) < wape(grupo.real_kg, grupo[base]))
    return float(np.mean(resultados)) if resultados else np.nan

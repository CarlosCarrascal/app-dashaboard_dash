"""Backtest rolling-origin del forecast publicado y sus baselines."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analitica.dominio.compartido import lunes_semana
from analitica.dominio.contratos import validar_backtest
from analitica.dominio.versiones import (
    banda_horizonte,
    fecha_emision_desde_objetivo,
    parsear_version,
)

IDENTIDAD = ["campania", "lote_id", "empresa", "fundo", "modulo", "lote"]


def seleccionar_versiones_oficiales(forecast: pd.DataFrame) -> pd.DataFrame:
    f = forecast.copy()
    parsed = f.version.map(parsear_version)
    f["semana_emision"] = [v.semana_emision for v in parsed]
    f["iteracion"] = [v.iteracion for v in parsed]
    f["escenario"] = [v.escenario for v in parsed]
    f = f[f.escenario.isna() & f.semana_emision.notna()].copy()
    if f.empty:
        return f
    max_iter = f.groupby(["campania", "semana_emision"], dropna=False).iteracion.transform("max")
    return f[f.iteracion.eq(max_iter)].copy()


def preparar_r09(forecast: pd.DataFrame, cosecha: pd.DataFrame) -> pd.DataFrame:
    """Una fila comparable por lote, emisión y semana objetivo."""
    if forecast.empty:
        raise ValueError("La fuente no contiene historial versionado R09.")
    f = seleccionar_versiones_oficiales(forecast)
    f["fecha_objetivo"] = lunes_semana(f.fecha_cos)
    f["fecha_emision"] = [
        fecha_emision_desde_objetivo(objetivo, int(semana))
        for objetivo, semana in zip(f.fecha_objetivo, f.semana_emision, strict=True)
    ]
    f["horizonte_semanas"] = ((f.fecha_objetivo - f.fecha_emision).dt.days // 7).astype(int)
    f["kg_componentes"] = (
        pd.to_numeric(f.frutos_total, errors="coerce")
        * pd.to_numeric(f.peso_baya, errors="coerce")
        / 1000
    )
    # El compromiso comienza una semana después de emitir. Horizonte 0 es nowcast y no
    # participa en la regla de promoción definida por el plan.
    f = f[f.horizonte_semanas.between(1, 10)].copy()
    claves = [*IDENTIDAD, "fecha_emision", "fecha_objetivo", "horizonte_semanas", "version"]
    r09 = (
        f.groupby(claves, dropna=False, as_index=False)
        .agg(
            p50_kg=("kg", "sum"),
            plantas=("plantas_maestro", "max"),
            frutos_por_planta=("frutos_por_planta", "mean"),
            peso_baya_g=("peso_baya", "mean"),
            kg_componentes=("kg_componentes", "sum"),
        )
        .rename(columns={"version": "version_fuente"})
    )

    h = cosecha.copy()
    h["fecha_objetivo"] = lunes_semana(h.fecha)
    real = h.groupby(["campania", "lote_id", "fecha_objetivo"], as_index=False, dropna=False).agg(
        real_kg=("kg", "sum"),
        peso_real_g=("peso_baya", "mean"),
        plantas_reales=("plantas_cosechadas", "max"),
    )
    r09 = r09.merge(real, on=["campania", "lote_id", "fecha_objetivo"], how="left")
    # Dos bases distintas para el mismo concepto, y hay que conservar las dos.
    # `plantas_reales` viene de la cosecha: solo se sabe después, así que sirve para
    # evaluar pero no para predecir. `plantas` es el maestro del lote, conocido siempre en
    # la fecha de emisión, y es la base sobre la que puede trabajar un modelo. Comparar un
    # pronóstico hecho sobre catálogo contra un observado calculado sobre cosechadas mide
    # la diferencia entre ambas definiciones, no el error del modelo.
    r09["frutos_reales_por_planta"] = (
        r09.real_kg * 1000 / (r09.plantas_reales * r09.peso_real_g).replace(0, np.nan)
    )
    r09["frutos_reales_por_planta_catalogo"] = (
        r09.real_kg * 1000 / (r09.plantas * r09.peso_real_g).replace(0, np.nan)
    )
    r09["modelo"] = "R09_publicado"
    r09["banda_horizonte"] = r09.horizonte_semanas.map(banda_horizonte)
    r09["p10_kg"] = np.nan
    r09["p90_kg"] = np.nan
    return r09


def _estadistica_pasada(
    tabla: pd.DataFrame, fecha: pd.Timestamp, banda: str, minimo: int = 20
) -> tuple[float, float, float, int]:
    pasada = tabla[(tabla.fecha_emision < fecha) & tabla.real_kg.notna()].copy()
    especifica = pasada[pasada.banda_horizonte == banda]
    muestra = especifica if len(especifica) >= minimo else pasada
    residuos = (muestra.real_kg - muestra.p50_kg).dropna()
    if len(residuos) < minimo:
        return 0.0, np.nan, np.nan, len(residuos)
    return (
        float(residuos.median()),
        float(residuos.quantile(0.1)),
        float(residuos.quantile(0.9)),
        len(residuos),
    )


def intervalos_y_sesgo(r09: pd.DataFrame) -> pd.DataFrame:
    """Genera R09 publicado y corregido sin usar residuos de la emisión evaluada."""
    base = r09.sort_values(["fecha_emision", "fecha_objetivo", "lote_id"]).copy()
    filas_calibracion = []
    for fecha, banda in (
        base[["fecha_emision", "banda_horizonte"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    ):
        correccion, q10, q90, n = _estadistica_pasada(base, fecha, banda)
        filas_calibracion.append(
            {
                "fecha_emision": fecha,
                "banda_horizonte": banda,
                "correccion": correccion,
                "q10": q10,
                "q90": q90,
                "n_calibracion": n,
            }
        )
    base = base.merge(pd.DataFrame(filas_calibracion), on=["fecha_emision", "banda_horizonte"])
    sin_calibrar = base.q10.isna()
    base.loc[sin_calibrar, "q10"] = -0.5 * base.loc[sin_calibrar, "p50_kg"].clip(lower=1)
    base.loc[sin_calibrar, "q90"] = 0.5 * base.loc[sin_calibrar, "p50_kg"].clip(lower=1)
    base["confianza"] = np.where(base.n_calibracion >= 50, "media", "baja")
    base["p10_kg"] = np.minimum(base.p50_kg, (base.p50_kg + base.q10).clip(lower=0))
    base["p90_kg"] = np.maximum(base.p50_kg, base.p50_kg + base.q90)

    corregido = base.copy()
    corregido["modelo"] = "R09_corregido_sesgo"
    corregido["p50_kg"] = (corregido.p50_kg + corregido.correccion).clip(lower=0)
    corregido["p10_kg"] = np.minimum(corregido.p50_kg, (base.p50_kg + base.q10).clip(lower=0))
    corregido["p90_kg"] = np.maximum(corregido.p50_kg, base.p50_kg + base.q90)
    return pd.concat([base, corregido], ignore_index=True).drop(
        columns=["correccion", "q10", "q90"]
    )


def _historico_anterior(
    historia: pd.DataFrame, lote_id: object, fecha_emision: pd.Timestamp
) -> pd.DataFrame:
    return historia[(historia.lote_id == lote_id) & (historia.fecha_objetivo < fecha_emision)]


def agregar_baselines(tabla: pd.DataFrame, cosecha: pd.DataFrame) -> pd.DataFrame:
    """Naive, SeasonalNaive e HistoricAverage calculados solo con historia previa."""
    h = cosecha.copy()
    h["fecha_objetivo"] = lunes_semana(h.fecha)
    h = h.groupby(["lote_id", "fecha_objetivo"], as_index=False).kg.sum()
    h = h.rename(columns={"kg": "real_hist_kg"}).sort_values(["lote_id", "fecha_objetivo"])
    objetivos = tabla[tabla.modelo == "R09_publicado"].copy().reset_index(drop=True)
    salidas = [tabla]

    # Último valor conocido: merge_asof global por fecha y restringido por lote.
    izquierda = objetivos.reset_index(names="__id").sort_values(["fecha_emision", "lote_id"])
    derecha = h.rename(columns={"fecha_objetivo": "fecha_hist"}).sort_values(
        ["fecha_hist", "lote_id"]
    )
    izquierda["fecha_emision"] = izquierda.fecha_emision.astype("datetime64[ns]")
    derecha["fecha_hist"] = derecha.fecha_hist.astype("datetime64[ns]")
    naive = pd.merge_asof(
        izquierda,
        derecha,
        left_on="fecha_emision",
        right_on="fecha_hist",
        by="lote_id",
        direction="backward",
        allow_exact_matches=False,
    ).sort_values("__id")
    predicciones = {"Naive": naive.real_hist_kg}

    estacional = objetivos.reset_index(names="__id").copy()
    estacional["fecha_estacional"] = estacional.fecha_objetivo - pd.Timedelta(weeks=52)
    estacional = estacional.merge(
        h.rename(columns={"fecha_objetivo": "fecha_estacional"}),
        on=["lote_id", "fecha_estacional"],
        how="left",
    ).sort_values("__id")
    predicciones["SeasonalNaive"] = estacional.real_hist_kg

    historicos = []
    objetivos["semana_iso"] = objetivos.fecha_objetivo.dt.isocalendar().week.astype(int)
    for fecha, grupo in objetivos.groupby("fecha_emision"):
        grupo = grupo.reset_index(names="__id")
        pasado = h[h.fecha_objetivo < fecha].copy()
        pasado["semana_iso"] = pasado.fecha_objetivo.dt.isocalendar().week.astype(int)
        media_semana = pasado.groupby(["lote_id", "semana_iso"], as_index=False).real_hist_kg.mean()
        media_lote = pasado.groupby("lote_id").real_hist_kg.mean().rename("media_lote")
        g = grupo.merge(media_semana, on=["lote_id", "semana_iso"], how="left")
        g = g.merge(media_lote, on="lote_id", how="left")
        historicos.append(g.set_index("__id").real_hist_kg.fillna(g.set_index("__id").media_lote))
    predicciones["HistoricAverage"] = pd.concat(historicos).sort_index()

    for modelo, valores in predicciones.items():
        nueva = objetivos.copy()
        nueva["p50_kg"] = valores.reindex(nueva.index).clip(lower=0)
        nueva = nueva[nueva.p50_kg.notna()].copy()
        nueva["modelo"] = modelo
        nueva["version_fuente"] = "calculado_asof"
        nueva["p10_kg"] = 0.5 * nueva.p50_kg
        nueva["p90_kg"] = 1.5 * nueva.p50_kg
        nueva["confianza"] = "baja"
        salidas.append(nueva)
    return pd.concat(salidas, ignore_index=True)


def construir_backtest(forecast: pd.DataFrame, cosecha: pd.DataFrame) -> pd.DataFrame:
    r09 = preparar_r09(forecast, cosecha)
    completo = agregar_baselines(intervalos_y_sesgo(r09), cosecha)
    for columna in ("p10_kg", "p50_kg", "p90_kg", "real_kg"):
        completo[columna] = pd.to_numeric(completo[columna], errors="coerce").astype(float)
    return validar_backtest(completo)


def construir_backtest_r09(forecast: pd.DataFrame, cosecha: pd.DataFrame) -> pd.DataFrame:
    """Alias público estable para consumidores que solo necesitan R09 y sus baselines."""
    return construir_backtest(forecast, cosecha)

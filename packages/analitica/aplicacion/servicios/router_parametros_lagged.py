"""Servicio de negocio para el screening del router de parámetros rezagados.

El servicio mantiene el replay candidate-only del router: reemplaza el h1 de
Macro únicamente cuando existe un snapshot completo de los cuatro fundos en la
emisión anterior. El peso de la estabilización naive se vuelve a seleccionar
en cada origen usando solamente semanas ya cerradas.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from analitica.aplicacion.procesos.hibrido_parametros_lagged import (
    ConfiguracionHibridoParametrosLagged,
    seleccionar_peso_parametros_asof,
)
from analitica.aplicacion.servicios.parametros_replay import ACCESS_DEFAULT, cargar_reales_y_r09
from analitica.aplicacion.servicios.router_horizonte import agregar, leer

ARTEFACTO_LAGGED = (
    Path(__file__).resolve().parents[1] / ".tmp" / "screening_parameter_lagged_closed_pg.json"
)


def _metricas(tabla: pd.DataFrame, columna: str) -> dict[str, float | int]:
    error = tabla[columna] - tabla.real_kg
    denominador = float(tabla.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / denominador),
        "sesgo": float(error.sum() / denominador),
        "mae_kg": float(error.abs().mean()),
        "n": int(len(tabla)),
    }


def _bootstrap_beneficio(
    tabla: pd.DataFrame, *, repeticiones: int = 4_000, semilla: int = 20260825
) -> dict[str, float]:
    if len(tabla) < 4:
        return {"p05": np.nan, "p50": np.nan, "p95": np.nan}
    rng = np.random.default_rng(semilla)
    beneficios = []
    valores = tabla.reset_index(drop=True)
    for _ in range(repeticiones):
        muestra = valores.iloc[rng.integers(0, len(valores), size=len(valores))]
        denominador = float(muestra.real_kg.abs().sum())
        if denominador <= 0:
            continue
        w_candidato = float((muestra.candidate_kg - muestra.real_kg).abs().sum() / denominador)
        w_r09 = float((muestra.r09_kg - muestra.real_kg).abs().sum() / denominador)
        beneficios.append(w_r09 - w_candidato)
    if not beneficios:
        return {"p05": np.nan, "p50": np.nan, "p95": np.nan}
    return dict(
        zip(("p05", "p50", "p95"), np.quantile(beneficios, [0.05, 0.5, 0.95]), strict=False)
    )


def ejecutar(
    *,
    access: Path = ACCESS_DEFAULT,
    artefacto_lagged: Path = ARTEFACTO_LAGGED,
) -> dict[str, object]:
    campania = "C2026"
    macro_h1 = agregar(leer(76, campania, "MacroLegacy_v1", (1,)), "macro_kg")
    r09_h1 = agregar(leer(76, campania, "R09_publicado", (1,)), "r09_kg")
    macro_largo = agregar(leer(73, campania, "MacroLegacy_v1", (2, 3, 4, 5)), "macro_kg")
    r09_largo = agregar(leer(73, campania, "R09_publicado", (2, 3, 4, 5)), "r09_kg")
    claves = ["campania", "fecha_emision", "fecha_objetivo", "horizonte_semanas"]
    h1 = macro_h1.merge(
        r09_h1.drop(columns="real_kg"), on=claves, how="inner", validate="one_to_one"
    )
    h1["candidate_kg"] = h1.macro_kg
    h1["ruta"] = "macro_fallback"
    h1["peso_parametros"] = np.nan

    reales, _ = cargar_reales_y_r09(access, campania)
    contenido = json.loads(artefacto_lagged.read_text(encoding="utf-8"))
    lagged = pd.DataFrame(
        [fila for fila in contenido["detalle"] if fila.get("bloque") == "ninguno"]
    ).sort_values("semana_objetivo")
    historial: list[dict[str, object]] = []
    reemplazos = []
    cfg = ConfiguracionHibridoParametrosLagged()
    for fila in lagged.itertuples():
        objetivo = int(fila.semana_objetivo)
        emision = int(fila.semana_emision)
        # La emisión Sxx ocurre el lunes de su semana ISO. El domingo de la
        # semana xx-1 es el último cierre que puede entrar al calibrador.
        fecha_emision = pd.Timestamp.fromisocalendar(2026, emision, 1)
        peso = (
            seleccionar_peso_parametros_asof(
                pd.DataFrame(historial), fecha_emision=fecha_emision, config=cfg
            )
            if historial
            else 1.0
        )
        naive_kg = float(reales[emision - 1])
        prediccion = peso * float(fila.candidato_kg) + (1.0 - peso) * naive_kg
        mascara = h1.fecha_objetivo.dt.isocalendar().week.astype(int).eq(objetivo)
        if int(mascara.sum()) != 1:
            continue
        h1.loc[mascara, "candidate_kg"] = prediccion
        h1.loc[mascara, "ruta"] = "parametros_lagged_online"
        h1.loc[mascara, "peso_parametros"] = peso
        reemplazos.append(
            {
                "semana_emision": emision,
                "semana_objetivo": objetivo,
                "peso_parametros": peso,
                "lagged_kg": float(fila.candidato_kg),
                "naive_kg": naive_kg,
                "candidate_kg": prediccion,
                "real_kg": float(fila.real_kg),
                "r09_kg": float(fila.r09_kg),
            }
        )
        cierre = pd.Timestamp.fromisocalendar(2026, objetivo, 7)
        historial.append(
            {
                "lagged_total_kg": float(fila.candidato_kg),
                "naive_total_kg": naive_kg,
                "real_kg": float(fila.real_kg),
                "fecha_cierre_real": cierre,
            }
        )

    largo = macro_largo.merge(
        r09_largo.drop(columns="real_kg"), on=claves, how="inner", validate="one_to_one"
    )
    largo["candidate_kg"] = largo.macro_kg
    largo["ruta"] = "macro_congelada_h2_h5"
    largo["peso_parametros"] = np.nan
    comun = pd.concat([h1, largo], ignore_index=True).sort_values(claves)

    resumen = {
        "candidato": _metricas(comun, "candidate_kg"),
        "macro": _metricas(comun, "macro_kg"),
        "r09": _metricas(comun, "r09_kg"),
    }
    por_horizonte = {}
    for horizonte, grupo in comun.groupby("horizonte_semanas"):
        por_horizonte[str(int(horizonte))] = {
            "candidato": _metricas(grupo, "candidate_kg"),
            "macro": _metricas(grupo, "macro_kg"),
            "r09": _metricas(grupo, "r09_kg"),
        }
    h1_reemplazado = comun.loc[comun.ruta.eq("parametros_lagged_online")]
    return {
        "schema": "screening-router-parametros-lagged-v1",
        "campania": campania,
        "formula": "h1 parámetros Sxx-1 + peso online as-of; h2-h5 Macro congelada",
        "usa_r09_como_predictor": False,
        "resumen": resumen,
        "por_horizonte": por_horizonte,
        "n_reemplazos_h1": int(len(h1_reemplazado)),
        "reemplazos_h1": reemplazos,
        "bootstrap_beneficio_wape_vs_r09": _bootstrap_beneficio(comun),
        "detalle": comun.to_dict("records"),
        "publicable": False,
    }


__all__ = [
    "ACCESS_DEFAULT",
    "ARTEFACTO_LAGGED",
    "ConfiguracionHibridoParametrosLagged",
    "agregar",
    "cargar_reales_y_r09",
    "ejecutar",
    "leer",
    "seleccionar_peso_parametros_asof",
]

"""Construcción y caché del único candidato HibridoParametrosAsOf."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import pandas as pd


def cargar_priors_excel(
    datos_candidato: Any,
    emisiones: pd.DataFrame,
    excel_root: str | None,
    *,
    loader: Callable[..., Any],
) -> dict[str, Any]:
    """Adjunta priors únicamente al clon candidate-only."""

    if not excel_root:
        return {"estado": "no_solicitado", "filas": 0, "manifiesto": 0, "faltantes": 0}
    fechas = {
        int(pd.Timestamp(fecha).isocalendar().week): pd.Timestamp(fecha).normalize()
        for fecha in pd.to_datetime(emisiones.fecha_emision).dropna().unique()
    }
    parametros, manifiesto, faltantes = loader(
        excel_root,
        semanas=tuple(sorted(fechas)),
        fechas_emision=fechas,
    )
    datos_candidato.parametros_legacy = parametros.copy(deep=True)
    return {
        "estado": "cargado",
        "filas": int(len(parametros)),
        "manifiesto": int(len(manifiesto)),
        "faltantes": int(len(faltantes)),
        "archivos": manifiesto.to_dict("records"),
        "fondos_sin_datos": faltantes.to_dict("records"),
    }


def completar_candidato(
    tabla: pd.DataFrame,
    *,
    nombre_modelo: str,
    version_modelo: str,
) -> pd.DataFrame:
    if tabla.empty:
        return tabla.copy()
    salida = tabla.copy()
    salida["modelo"] = nombre_modelo
    salida["version_modelo"] = version_modelo
    salida["version_fuente"] = version_modelo
    salida["fecha_emision"] = pd.to_datetime(salida.fecha_emision).dt.normalize()
    salida["fecha_objetivo"] = pd.to_datetime(salida.fecha_objetivo).dt.normalize()
    salida["origen_emision"] = salida.fecha_emision
    salida["tipo_prediccion"] = "replay"
    salida["es_replay_ciego"] = True
    salida["es_curva_stitched"] = False
    salida["estado_evaluacion"] = salida.real_kg.notna().map(
        {True: "evaluada", False: "pendiente"}
    )
    for columna in ("p10_kg", "p90_kg"):
        if columna not in salida:
            salida[columna] = salida.p50_kg
    return salida


def construir_candidato(
    datos: Any,
    emisiones: pd.DataFrame,
    *,
    campania: str,
    horizonte: int,
    max_cortes: int | None,
    excel_root: str | None,
    clonar_datos: Callable[[Any], Any],
    cargar_priors: Callable[[Any, pd.DataFrame, str | None], dict[str, Any]],
    backtest: Callable[..., Any],
    nombre_modelo: str,
    version_modelo: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Calcula exclusivamente HPA sobre un clon del contrato fuente."""

    datos_candidato = clonar_datos(datos)
    priors = cargar_priors(datos_candidato, emisiones, excel_root)
    inicio = time.perf_counter()
    predicciones, avisos, snapshots = backtest(
        datos_candidato,
        emisiones,
        campania=str(campania),
        horizonte_semanas=int(horizonte),
        max_cortes=max_cortes,
    )
    predicciones = completar_candidato(
        predicciones,
        nombre_modelo=nombre_modelo,
        version_modelo=version_modelo,
    )
    modelos = set(predicciones.modelo.dropna().astype(str)) if not predicciones.empty else set()
    if modelos - {nombre_modelo}:
        raise ValueError(
            f"El constructor candidate-only produjo otros modelos: {sorted(modelos)}"
        )
    return (
        predicciones,
        snapshots,
        {
            "modelo": nombre_modelo,
            "version_modelo": version_modelo,
            "segundos": round(time.perf_counter() - inicio, 3),
            "filas": int(len(predicciones)),
            "snapshots_parametros": int(len(snapshots)),
            "advertencias": list(avisos),
            "parametros_excel": priors,
        },
    )


def candidate_cache(
    datos: Any,
    emisiones: pd.DataFrame,
    *,
    campania: str,
    horizonte: int,
    max_cortes: int | None,
    excel_root: str | None,
    cache: Any,
    fase: str,
    nombre_modelo: str,
    version_modelo: str,
    firma_directorio: Callable[[str | None], str | None],
    sha256_dataframe: Callable[[pd.DataFrame, list[str]], str],
    clave_cache: Callable[[dict[str, Any]], str],
    obtener_cache: Callable[..., Any],
    construir: Callable[..., Any],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Obtiene o construye un artefacto candidate-only por identidad estable."""

    configuracion = {
        "schema": "hpa-candidate-cache-v1",
        "fase": fase,
        "modelo": nombre_modelo,
        "version": version_modelo,
        "campania": str(campania),
        "horizonte": int(horizonte),
        "max_cortes": max_cortes,
        "fuente_firma": datos.fuente.firma,
        "emisiones_sha256": sha256_dataframe(emisiones, ["campania", "fecha_emision"]),
        "excel_tree_sha256": firma_directorio(excel_root),
    }
    clave = clave_cache(configuracion)
    return obtener_cache(
        cache,
        clave,
        lambda: construir(
            datos,
            emisiones,
            campania=campania,
            horizonte=horizonte,
            max_cortes=max_cortes,
            excel_root=excel_root,
        ),
    )


__all__ = [
    "candidate_cache",
    "cargar_priors_excel",
    "completar_candidato",
    "construir_candidato",
]

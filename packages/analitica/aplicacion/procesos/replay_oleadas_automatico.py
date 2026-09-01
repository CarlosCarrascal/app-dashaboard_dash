"""Replay rolling-origin de la ruta automática de oleadas.

La ruta automática debe probarse con la misma disciplina que R09: el modelo solo
puede conocer lo anterior a la emisión y cada semana objetivo se evalúa únicamente
cuando ya cerró en H01. Este módulo no selecciona ni publica un modelo; produce
evidencia para decidir si vale la pena calibrarlo con contexto continuo.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from analitica.dominio.compartido import lunes_semana

from ..parametros.oleadas_candidato import (
    NOMBRE_MODELO,
    proyectar_universo_automatico_oleadas,
)

_CLAVES = ("campania", "modulo", "turno", "lote")


def _alias(tabla: pd.DataFrame, nombres: Sequence[str]) -> str | None:
    indice = {str(columna).strip().casefold(): str(columna) for columna in tabla.columns}
    for nombre in nombres:
        encontrada = indice.get(str(nombre).strip().casefold())
        if encontrada is not None:
            return encontrada
    return None


def _texto(serie: pd.Series) -> pd.Series:
    salida = serie.astype("string").str.strip()
    return salida.mask(
        salida.isna() | salida.eq("") | salida.str.casefold().isin({"nan", "none", "nat"})
    )


def _identidad(tabla: pd.DataFrame) -> pd.DataFrame:
    salida = tabla.copy()
    aliases = {
        "campania": ("campania", "campaña", "campana"),
        "modulo": ("modulo", "módulo", "modulo_id"),
        "turno": ("turno", "turno_id"),
        "lote": ("lote", "lote_codigo"),
    }
    for canonico, nombres in aliases.items():
        if canonico not in salida:
            columna = _alias(salida, nombres)
            salida[canonico] = salida[columna] if columna is not None else pd.NA
        salida[canonico] = _texto(salida[canonico])
    return salida


def _normalizar_cosecha(cosecha: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(cosecha, pd.DataFrame):
        raise TypeError("cosecha debe ser un DataFrame")
    tabla = _identidad(cosecha)
    columna_fecha = _alias(tabla, ("fecha", "fecha_cosecha", "fecha_real", "fecha_dato"))
    columna_kg = _alias(tabla, ("kg", "real_kg", "kilogramos", "volumen_kg"))
    if columna_fecha is None or columna_kg is None:
        raise ValueError("cosecha requiere una fecha y una columna kg")
    tabla["fecha"] = pd.to_datetime(tabla[columna_fecha], errors="coerce").dt.normalize()
    tabla["kg"] = pd.to_numeric(tabla[columna_kg], errors="coerce")
    validas = tabla.fecha.notna() & tabla.kg.notna() & tabla[list(_CLAVES)].notna().all(axis=1)
    tabla = tabla.loc[validas, [*_CLAVES, "fecha", "kg"]].copy()
    if tabla.empty:
        return pd.DataFrame(columns=[*_CLAVES, "fecha_objetivo", "real_kg"])
    tabla["fecha_objetivo"] = lunes_semana(tabla.fecha)
    return tabla.groupby([*_CLAVES, "fecha_objetivo"], as_index=False).kg.sum().rename(
        columns={"kg": "real_kg"}
    )


def _normalizar_emisiones(fechas_emision: Sequence[object]) -> tuple[pd.Timestamp, ...]:
    fechas = tuple(pd.Timestamp(fecha).normalize() for fecha in fechas_emision)
    if not fechas or any(pd.isna(fecha) for fecha in fechas):
        raise ValueError("fechas_emision debe contener fechas válidas")
    if len(set(fechas)) != len(fechas):
        raise ValueError("fechas_emision no puede repetir fechas")
    return tuple(sorted(fechas))


def _contexto_emision(
    contexto_por_emision: Mapping[object, Mapping[tuple[str, ...], Mapping[str, Any]]] | None,
    fecha: pd.Timestamp,
) -> Mapping[tuple[str, ...], Mapping[str, Any]] | None:
    if contexto_por_emision is None:
        return None
    for clave, valor in contexto_por_emision.items():
        if pd.Timestamp(clave).normalize() == fecha:
            return valor
    return None


def _metricas(tabla: pd.DataFrame, columna: str) -> dict[str, Any]:
    valida = tabla.loc[tabla.incluye_en_metricas & tabla[columna].notna()].copy()
    if valida.empty:
        return {
            "filas": 0,
            "lotes": 0,
            "real_kg": 0.0,
            "pred_kg": 0.0,
            "error_kg": 0.0,
            "wape": np.nan,
            "bias_pct": np.nan,
        }
    error = valida[columna] - valida.real_kg
    real_total = float(valida.real_kg.sum())
    return {
        "filas": int(len(valida)),
        "lotes": int(valida.lote_id.nunique()),
        "real_kg": real_total,
        "pred_kg": float(valida[columna].sum()),
        "error_kg": float(error.sum()),
        "wape": float(error.abs().sum() / real_total) if real_total else np.nan,
        "bias_pct": float(error.sum() / real_total) if real_total else np.nan,
    }


def _metricas_por_grupo(
    tabla: pd.DataFrame,
    columna: str,
    claves: Sequence[str],
) -> dict[str, dict[str, Any]]:
    if tabla.empty:
        return {}
    salida = {}
    for clave, grupo in tabla.groupby(list(claves), sort=True, dropna=False):
        clave = clave if isinstance(clave, tuple) else (clave,)
        etiqueta = "|".join(str(valor) for valor in clave)
        salida[etiqueta] = _metricas(grupo, columna)
    return salida


def _comparar_r09(
    predicciones: pd.DataFrame,
    panel_r09: pd.DataFrame,
) -> dict[str, Any]:
    requeridas = {
        "campania",
        "lote_id",
        "fecha_emision",
        "fecha_objetivo",
        "horizonte_semanas",
        "p50_kg",
        "real_kg",
    }
    faltantes = sorted(requeridas - set(panel_r09.columns))
    if faltantes:
        raise ValueError("panel_r09 no contiene: " + ", ".join(faltantes))
    claves = ["campania", "lote_id", "fecha_emision", "fecha_objetivo", "horizonte_semanas"]
    base = panel_r09[list(claves)].copy()
    base["r09_p50_kg"] = pd.to_numeric(panel_r09["p50_kg"], errors="coerce")
    base["real_panel_kg"] = pd.to_numeric(panel_r09["real_kg"], errors="coerce")
    izquierda = predicciones.merge(
        base,
        on=claves,
        how="inner",
        validate="many_to_one",
    )
    izquierda["incluye_en_metricas"] = izquierda["real_panel_kg"].notna()
    izquierda["real_kg"] = izquierda["real_panel_kg"]
    return {
        "filas_comunes": int(len(izquierda)),
        "filas_evaluables": int(izquierda.incluye_en_metricas.sum()),
        "automatico": _metricas(izquierda, "p50_kg"),
        "r09": _metricas(izquierda.rename(columns={"r09_p50_kg": "r09"}), "r09"),
        "automatico_por_horizonte": _metricas_por_grupo(
            izquierda, "p50_kg", ("horizonte_semanas",)
        ),
        "r09_por_horizonte": _metricas_por_grupo(
            izquierda.rename(columns={"r09_p50_kg": "r09"}), "r09", ("horizonte_semanas",)
        ),
    }


def replay_automatico_oleadas_asof(
    lotes: pd.DataFrame,
    cosecha: pd.DataFrame,
    fechas_emision: Sequence[object],
    *,
    semanas: int = 6,
    panel_r09: pd.DataFrame | None = None,
    modelo_contexto: Any | None = None,
    contexto_por_emision: Mapping[
        object, Mapping[tuple[str, ...], Mapping[str, Any]]
    ]
    | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Evalúa la ruta automática por emisión y horizonte.

    Las semanas objetivo sin cierre completo quedan en la salida, pero no entran en
    las métricas. La cosecha faltante dentro de una semana ya cerrada se interpreta
    como cero: esto distingue «el lote no cosechó» de «todavía no se podía evaluar».
    """

    if not isinstance(lotes, pd.DataFrame) or lotes.empty:
        raise ValueError("lotes debe ser un DataFrame no vacío")
    if not 6 <= int(semanas) <= 52:
        raise ValueError("semanas debe estar entre 6 y 52")
    emisiones = _normalizar_emisiones(fechas_emision)
    historia = _normalizar_cosecha(cosecha)
    columna_fecha_cosecha = _alias(
        cosecha, ("fecha", "fecha_cosecha", "fecha_real", "fecha_dato")
    )
    fecha_max_observada = (
        pd.to_datetime(cosecha[columna_fecha_cosecha], errors="coerce").dt.normalize().max()
        if columna_fecha_cosecha is not None
        else pd.NaT
    )
    if historia.empty or pd.isna(fecha_max_observada):
        fecha_cierre = None
        ultima_semana_completa = None
    else:
        fecha_cierre = pd.Timestamp(fecha_max_observada)
        ultima_semana_completa = lunes_semana(fecha_cierre - pd.Timedelta(6, unit="D"))

    pivote_columna = _alias(lotes, ("fecha_pivote", "fecha_poda", "fecha_inicio", "FPoda"))
    if pivote_columna is None:
        raise ValueError("lotes requiere fecha_pivote, fecha_poda o fecha_inicio")
    pivotes = pd.to_datetime(lotes[pivote_columna], errors="coerce").dt.normalize()
    salidas: list[pd.DataFrame] = []
    manifiestos_emision: list[dict[str, Any]] = []
    for emision in emisiones:
        activos = lotes.loc[pivotes.notna() & pivotes.lt(emision)].copy()
        contexto = _contexto_emision(contexto_por_emision, emision)
        prediccion, metadata = proyectar_universo_automatico_oleadas(
            activos,
            cosecha,
            emision,
            semanas=semanas,
            fecha_corte=emision,
            modelo_contexto=modelo_contexto,
            contexto_por_lote=contexto,
        )
        prediccion = prediccion.copy()
        prediccion["p50_kg"] = pd.to_numeric(prediccion["kg"], errors="coerce")
        prediccion["lote_id"] = (
            prediccion["modulo"].astype(str)
            + "|"
            + prediccion["turno"].astype(str)
            + "|"
            + prediccion["lote"].astype(str)
        )
        if ultima_semana_completa is None:
            prediccion["incluye_en_metricas"] = False
        else:
            prediccion["incluye_en_metricas"] = prediccion.fecha_objetivo.le(
                ultima_semana_completa
            )
        prediccion["fecha_cierre_real"] = fecha_cierre
        prediccion = prediccion.merge(
            historia,
            on=["campania", "modulo", "turno", "lote", "fecha_objetivo"],
            how="left",
            validate="many_to_one",
        )
        prediccion["real_observado"] = prediccion.real_kg.notna()
        prediccion["real_kg"] = prediccion.real_kg.fillna(0.0)
        # Una fila con objetivo ya cerrado y sin cosecha es un cero real; una fila
        # futura conserva NaN para que no se cuele en los denominadores.
        prediccion.loc[~prediccion.incluye_en_metricas, "real_kg"] = np.nan
        prediccion["modelo"] = NOMBRE_MODELO
        prediccion["fecha_emision"] = emision
        salidas.append(prediccion)
        manifiestos_emision.append(
            {
                "fecha_emision": emision.strftime("%Y-%m-%d"),
                "lotes_activos": int(len(activos)),
                "lotes_con_historia_asof": int(metadata["lotes_con_historia_asof"]),
                "lotes_sin_historia": int(len(metadata["lotes_sin_historia"])),
                "lotes_con_modelo_contexto": int(
                    metadata["lotes_con_modelo_contexto"]
                ),
                "filas_evaluables": int(prediccion.incluye_en_metricas.sum()),
                "advertencias": list(metadata["advertencias"]),
            }
        )
    predicciones = pd.concat(salidas, ignore_index=True, sort=False)
    metadatos: dict[str, Any] = {
        "modelo": NOMBRE_MODELO,
        "version": "automatico_oleadas_asof_rolling_origin_h6_v1",
        "semanas": int(semanas),
        "emisiones": [fecha.strftime("%Y-%m-%d") for fecha in emisiones],
        "fecha_cierre_real": fecha_cierre.strftime("%Y-%m-%d") if fecha_cierre else None,
        "ultima_semana_completa": (
            ultima_semana_completa.strftime("%Y-%m-%d")
            if ultima_semana_completa is not None
            else None
        ),
        "filas_predicciones": int(len(predicciones)),
        "filas_evaluables": int(predicciones.incluye_en_metricas.sum()),
        "metricas": _metricas(predicciones, "p50_kg"),
        "metricas_por_horizonte": _metricas_por_grupo(
            predicciones, "p50_kg", ("horizonte_semanas",)
        ),
        "metricas_por_emision": _metricas_por_grupo(
            predicciones, "p50_kg", ("fecha_emision",)
        ),
        "emisiones_detalle": manifiestos_emision,
        "publicable": False,
        "sin_fuga": True,
    }
    if panel_r09 is not None:
        metadatos["comparacion_r09"] = _comparar_r09(predicciones, panel_r09)
    return predicciones, metadatos


__all__ = ["replay_automatico_oleadas_asof"]

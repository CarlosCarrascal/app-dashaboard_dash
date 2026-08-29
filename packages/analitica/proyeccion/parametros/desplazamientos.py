"""Aprendizaje as-of de desplazamientos semanales y señales GDD."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from .contratos import ConfiguracionParametrosAsOf


def _deduplicar_historial(historial: pd.DataFrame) -> pd.DataFrame:
    if historial is None or historial.empty:
        return pd.DataFrame()
    tabla = historial.copy()
    if "fecha_emision" in tabla:
        tabla["fecha_emision"] = pd.to_datetime(tabla.fecha_emision, errors="coerce")
        tabla = tabla.sort_values("fecha_emision")
    claves = [c for c in ("campania", "lote_id", "fecha_objetivo") if c in tabla]
    if claves:
        tabla = tabla.drop_duplicates(claves, keep="last")
    return tabla


def aprender_desplazamiento(
    historial: pd.DataFrame,
    *,
    max_shift_days: int = 14,
) -> tuple[int, dict[str, Any]]:
    """Aprende un desplazamiento semanal solo si mejora el error histórico.

    Un desplazamiento positivo significa que la curva se mueve hacia adelante: para
    predecir ``t`` se consulta la curva legacy en ``t - desplazamiento``.
    """

    tabla = _deduplicar_historial(historial)
    requeridas = {"lote_id", "fecha_objetivo", "real_kg", "legacy_kg"}
    if tabla.empty or not requeridas <= set(tabla):
        return 0, {"n": 0, "metodo": "sin_historia"}
    tabla["fecha_objetivo"] = pd.to_datetime(tabla.fecha_objetivo, errors="coerce")
    tabla = tabla.dropna(subset=["fecha_objetivo", "real_kg", "legacy_kg"])
    if len(tabla) < 12:
        return 0, {"n": int(len(tabla)), "metodo": "insuficiente"}
    tabla["real_kg"] = pd.to_numeric(tabla.real_kg, errors="coerce")
    tabla["legacy_kg"] = pd.to_numeric(tabla.legacy_kg, errors="coerce")
    base = tabla.set_index(["lote_id", "fecha_objetivo"]).legacy_kg
    candidatos = sorted(set(range(-abs(max_shift_days), abs(max_shift_days) + 1, 7)) | {0})
    scores: dict[int, float] = {}
    for shift in candidatos:
        esperados = []
        reales = []
        for fila in tabla.itertuples(index=False):
            clave = (fila.lote_id, fila.fecha_objetivo - pd.Timedelta(days=shift))
            valor = base.get(clave, np.nan)
            if pd.notna(valor):
                esperados.append(float(valor))
                reales.append(float(fila.real_kg))
        scores[shift] = (
            float(np.abs(np.asarray(esperados) - np.asarray(reales)).sum()) if reales else np.inf
        )
    if not np.isfinite(scores.get(0, np.inf)):
        return 0, {"n": int(len(tabla)), "metodo": "sin_pares"}
    elegido = min(scores, key=scores.get)
    mejora = 1 - scores[elegido] / max(scores[0], 1e-9)
    if elegido != 0 and mejora < 0.05:
        elegido = 0
    return int(elegido), {
        "n": int(len(tabla)),
        "scores": scores,
        "mejora_relativa": float(mejora),
        "metodo": "comparacion_shift_semanal",
    }


def seleccionar_gdd_config(
    historial: pd.DataFrame,
    config: ConfiguracionParametrosAsOf | None = None,
) -> tuple[float | None, int | None, dict[str, Any]]:
    """Selecciona un desplazamiento fenológico de GDD con holdout temporal.

    El objetivo de entrenamiento no es ``kg`` directamente: para cada observación
    histórica se busca qué desplazamiento discreto de la curva legacy (±0, 7 o 14
    días) habría reducido su error. La señal GDD solo se admite si predice ese
    desplazamiento en el tramo temporal reservado y mejora el error de kg. Así se
    evita convertir GDD en un multiplicador de volumen.
    """

    config = config or ConfiguracionParametrosAsOf()
    tabla = _deduplicar_historial(historial)
    requeridas = {"lote_id", "fecha_objetivo", "real_kg", "legacy_kg"}
    if tabla.empty or not requeridas <= set(tabla):
        return None, None, {"estado": "sin_historia"}
    tabla["fecha_objetivo"] = pd.to_datetime(tabla.fecha_objetivo, errors="coerce").dt.normalize()
    tabla = tabla.dropna(subset=[*requeridas]).reset_index(drop=True)
    if len(tabla) < 20:
        return None, None, {"estado": "insuficiente", "n": int(len(tabla))}

    tabla["real_kg"] = pd.to_numeric(tabla.real_kg, errors="coerce")
    tabla["legacy_kg"] = pd.to_numeric(tabla.legacy_kg, errors="coerce")
    tabla = tabla[tabla.real_kg.ge(0) & tabla.legacy_kg.ge(0)].copy()
    if len(tabla) < 20:
        return None, None, {"estado": "insuficiente", "n": int(len(tabla))}

    # La tabla ya viene deduplicada por lote/objetivo. El índice se conserva solo
    # para leer la curva legacy en fechas vecinas de la misma unidad agronómica.
    curva = {
        (str(fila.lote_id), pd.Timestamp(fila.fecha_objetivo)): float(fila.legacy_kg)
        for fila in tabla.itertuples(index=False)
    }
    desplazamientos = (-14, -7, 0, 7, 14)
    objetivos = []
    for indice, fila in tabla.iterrows():
        candidatos = []
        for desplazamiento in desplazamientos:
            valor = curva.get(
                (
                    str(fila.lote_id),
                    pd.Timestamp(fila.fecha_objetivo) - pd.Timedelta(days=desplazamiento),
                )
            )
            if valor is not None:
                candidatos.append((abs(valor - float(fila.real_kg)), desplazamiento))
        if candidatos:
            objetivos.append((indice, min(candidatos)[1]))
    if len(objetivos) < 20:
        return None, None, {"estado": "sin_curva_vecina", "n": int(len(objetivos))}
    tabla["desplazamiento_objetivo"] = np.nan
    for indice, valor in objetivos:
        tabla.loc[indice, "desplazamiento_objetivo"] = valor
    tabla = tabla.dropna(subset=["desplazamiento_objetivo"])

    candidatos: list[tuple[float, int, str]] = []
    for base in config.gdd_bases:
        for ventana in config.gdd_ventanas:
            nombre = f"gdd_{str(base).replace('.', '_')}_{ventana}d"
            columnas = [c for c in tabla.columns if c.casefold() == nombre.casefold()]
            if columnas:
                candidatos.append((base, ventana, columnas[0]))
    if not candidatos:
        return None, None, {"estado": "sin_columnas"}
    corte = max(1, int(len(tabla) * 0.7))
    mejor = None
    for base, ventana, columna in candidatos:
        x = pd.to_numeric(tabla[columna], errors="coerce").to_numpy(float)
        objetivo = tabla.desplazamiento_objetivo.to_numpy(float)
        valido = np.isfinite(x) & np.isfinite(objetivo)
        if valido.sum() < 12:
            continue
        train = np.flatnonzero(valido & (np.arange(len(tabla)) < corte))
        test = np.flatnonzero(valido & (np.arange(len(tabla)) >= corte))
        if len(train) < 8 or len(test) < 4:
            continue
        media = float(np.nanmean(x[train]))
        escala = float(np.nanstd(x[train])) or 1.0
        x_est = ((x - media) / escala)[:, None]
        modelo = Ridge(alpha=10.0).fit(x_est[train], objetivo[train])
        pred = np.clip(np.rint(modelo.predict(x_est[test]) / 7.0) * 7.0, -14, 14)
        # Evaluamos el desplazamiento directamente sobre kg, no sobre el target
        # intermedio. El baseline es no desplazar la curva.
        filas_test = tabla.iloc[test]
        error = []
        error_prior = []
        for fila, shift in zip(filas_test.itertuples(index=False), pred, strict=False):
            clave_base = (str(fila.lote_id), pd.Timestamp(fila.fecha_objetivo))
            clave_shift = (
                str(fila.lote_id),
                pd.Timestamp(fila.fecha_objetivo) - pd.Timedelta(days=float(shift)),
            )
            valor_base = curva.get(clave_base)
            valor_shift = curva.get(clave_shift)
            if valor_base is None or valor_shift is None:
                continue
            error.append(abs(valor_shift - float(fila.real_kg)))
            error_prior.append(abs(valor_base - float(fila.real_kg)))
        if len(error) < 4:
            continue
        error_oos = float(np.mean(error))
        prior = float(np.mean(error_prior))
        candidato = (
            error_oos,
            base,
            ventana,
            int(valido.sum()),
            prior,
            media,
            escala,
            float(modelo.coef_[0]),
            float(modelo.intercept_),
        )
        if mejor is None or candidato[0] < mejor[0]:
            mejor = candidato
    if mejor is None or mejor[0] >= mejor[4] * 0.95:
        return None, None, {"estado": "sin_mejora_oos"}
    return (
        float(mejor[1]),
        int(mejor[2]),
        {
            "estado": "admitido_oos",
            "error": mejor[0],
            "prior": mejor[4],
            "n": mejor[3],
            "media_gdd": mejor[5],
            "escala_gdd": mejor[6],
            "coeficiente_dias_estandarizado": mejor[7],
            "intercepto_dias": mejor[8],
            "desplazamientos_permitidos": list(desplazamientos),
            "gdd_base": float(mejor[1]),
            "gdd_ventana": int(mejor[2]),
        },
    )


def _desplazamiento_gdd_por_fila(
    tabla: pd.DataFrame,
    desplazamiento_base: int,
    detalle_gdd: dict[str, Any],
) -> int | pd.Series:
    """Calcula el desplazamiento por fila solo para una señal GDD admitida OOS."""

    if detalle_gdd.get("estado") != "admitido_oos":
        return int(desplazamiento_base)
    base = detalle_gdd.get("gdd_base")
    ventana = detalle_gdd.get("gdd_ventana")
    if base is None or ventana is None:
        return int(desplazamiento_base)
    nombre = f"gdd_{str(base).replace('.', '_')}_{ventana}d"
    if nombre not in tabla:
        return int(desplazamiento_base)
    x = pd.to_numeric(tabla[nombre], errors="coerce")
    media = float(detalle_gdd.get("media_gdd", 0.0))
    escala = float(detalle_gdd.get("escala_gdd", 1.0)) or 1.0
    coef = float(detalle_gdd.get("coeficiente_dias_estandarizado", 0.0))
    intercepto = float(detalle_gdd.get("intercepto_dias", desplazamiento_base))
    estimado = intercepto + coef * ((x - media) / escala)
    estimado = estimado.fillna(float(desplazamiento_base))
    return (np.rint(estimado / 7.0) * 7.0).clip(-14, 14).astype(float)


__all__ = [
    "aprender_desplazamiento",
    "seleccionar_gdd_config",
]

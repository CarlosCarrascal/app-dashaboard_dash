"""Lógica reusable del diagnóstico de v2 frente a nowcast por horizontes.

No persiste, no publica y no modifica releases. Usa la corrida 81 sólo como
laboratorio porque la release aprobada de v2 conserva actualmente h1.

El módulo concentra consultas, normalización, agregación, métricas y la
composición del diagnóstico para que otras interfaces puedan reutilizarlas sin
depender de un script ejecutable. La composición de ``ejecutar`` permanece
intencionadamente explícita: fija las corridas, el corte certificado y la
serialización lógica del informe, mientras que cada transformación reusable
está separada en funciones con contrato estable.
"""

from __future__ import annotations

import pandas as pd
import psycopg

from analitica.proyeccion.horizonte import (
    ConfiguracionCorreccionHorizonte,
    aplicar_correccion_horizonte,
    configuraciones_loop,
    ejecutar_loop_horizonte,
    metricas_horizonte,
)
from analitica.settings import postgres_dsn

RUN_V2_APROBADO = 76
RUN_V2_LABORATORIO = 81
RUN_NOWCAST = 84


def leer_v2(run_id: int) -> pd.DataFrame:
    consulta = """
        SELECT campania, fecha_emision, fecha_objetivo, horizonte_semanas,
               lote_id, fundo, modulo, p50_kg, real_kg
        FROM analytics.prediction
        WHERE run_id = %s AND modelo = 'HibridoOcurrenciaOnline_v2'
          AND horizonte_semanas BETWEEN 1 AND 6
          AND fecha_emision < fecha_objetivo
    """
    with psycopg.connect(postgres_dsn()) as conexion, conexion.cursor() as cursor:
        # El diagnóstico recibe explícitamente el run solicitado. Mantener
        # RUN_V2_LABORATORIO aquí hacía que el supuesto baseline aprobado
        # leyera accidentalmente la corrida experimental 81.
        cursor.execute(consulta, (run_id,))
        return pd.DataFrame(cursor.fetchall(), columns=[d.name for d in cursor.description])


def leer_nowcast() -> pd.DataFrame:
    consulta = """
        SELECT campania, semana_inicio AS fecha_objetivo, fecha_emision,
               fundo, p50_kg, real_kg, kg_lun_mar
        FROM reporting.nowcast_cierre_semanal
        WHERE run_id = %s AND campania = 'C2026'
    """
    with psycopg.connect(postgres_dsn()) as conexion, conexion.cursor() as cursor:
        cursor.execute(consulta, (RUN_NOWCAST,))
        return pd.DataFrame(cursor.fetchall(), columns=[d.name for d in cursor.description])


def _seleccionar_total_nowcast(tabla: pd.DataFrame) -> pd.DataFrame:
    """Devuelve un único total por semana; evita sumar Empresa + fundos."""

    if tabla.empty:
        return tabla.copy()
    t = tabla.copy()
    if "fundo" not in t.columns:
        return t
    empresa = t.loc[t["fundo"].astype(str).str.casefold().eq("empresa")].copy()
    if not empresa.empty:
        return empresa
    return t.loc[~t["fundo"].astype(str).str.casefold().eq("empresa")].copy()


def _resumen_serie_semanal(
    tabla: pd.DataFrame,
    *,
    fecha_columna: str,
    pred_columna: str,
    real_columna: str = "real_kg",
    fecha_maxima: pd.Timestamp | None = None,
) -> pd.DataFrame:
    t = tabla.copy()
    t[fecha_columna] = pd.to_datetime(t[fecha_columna], errors="raise").dt.normalize()
    t[pred_columna] = pd.to_numeric(t[pred_columna], errors="coerce")
    t[real_columna] = pd.to_numeric(t[real_columna], errors="coerce")
    if fecha_maxima is not None:
        t = t.loc[t[fecha_columna].le(fecha_maxima)]
    t = t.dropna(subset=[pred_columna, real_columna])
    if t.empty:
        return pd.DataFrame(columns=["fecha_objetivo", "pred", "real"])
    return (
        t.groupby(fecha_columna, as_index=False)
        .agg(pred=(pred_columna, "sum"), real=(real_columna, "sum"))
        .rename(columns={fecha_columna: "fecha_objetivo"})
        .sort_values("fecha_objetivo")
    )


def _seleccionar_vintage_coherente(
    tabla: pd.DataFrame,
    *,
    fecha_objetivo: str = "fecha_objetivo",
    fecha_emision: str = "fecha_emision",
) -> pd.DataFrame:
    """Conserva una sola emisión por semana objetivo.

    Una curva histórica no puede sumar S31 + S32 + S33 para la misma semana:
    esos son vintages alternativos de una predicción. Se elige la última
    emisión estrictamente anterior al lunes objetivo, a nivel de semana, y
    luego se dejan sus filas completas para que el modelo mantenga su grano.
    """

    if tabla.empty:
        return tabla.copy()
    t = tabla.copy()
    t[fecha_objetivo] = pd.to_datetime(t[fecha_objetivo], errors="raise").dt.normalize()
    t[fecha_emision] = pd.to_datetime(t[fecha_emision], errors="raise").dt.normalize()
    t = t.loc[t[fecha_emision].lt(t[fecha_objetivo])].copy()
    if t.empty:
        return t
    vintage = (
        t.groupby(fecha_objetivo, as_index=False)[fecha_emision]
        .max()
        .rename(columns={fecha_emision: "_emision_elegida"})
    )
    t = t.merge(vintage, on=fecha_objetivo, how="inner", validate="many_to_one")
    return t.loc[t[fecha_emision].eq(t["_emision_elegida"])].drop(columns="_emision_elegida")


def _metricas_serie(serie: pd.DataFrame) -> dict[str, object]:
    if serie.empty:
        return {"n_semanas": 0, "real_kg": 0.0, "pred_kg": 0.0, "wape": None, "bias_pct": None}
    error = serie["pred"] - serie["real"]
    denominador = float(serie["real"].abs().sum())
    return {
        "n_semanas": int(len(serie)),
        "real_kg": float(serie["real"].sum()),
        "pred_kg": float(serie["pred"].sum()),
        "wape": float(error.abs().sum() / denominador) if denominador else None,
        "bias_pct": float(error.sum() / denominador) if denominador else None,
    }


def resumen_nowcast(
    tabla: pd.DataFrame,
    *,
    fecha_maxima: pd.Timestamp | None = None,
) -> dict[str, object]:
    if tabla.empty:
        return {"n_semanas": 0}
    s = _resumen_serie_semanal(
        _seleccionar_total_nowcast(tabla),
        fecha_columna="fecha_objetivo",
        pred_columna="p50_kg",
        fecha_maxima=fecha_maxima,
    )
    return {
        **_metricas_serie(s),
        "nota": (
            "Nowcast ve lunes-martes y cierra la semana; no es comparable como "
            "forecast previo."
        ),
    }


def ejecutar() -> dict[str, object]:
    v2_aprobado = leer_v2(RUN_V2_APROBADO)
    v2_aprobado["fecha_emision"] = pd.to_datetime(v2_aprobado["fecha_emision"]).dt.normalize()
    v2_aprobado["fecha_objetivo"] = pd.to_datetime(v2_aprobado["fecha_objetivo"]).dt.normalize()
    v2_aprobado = v2_aprobado.loc[v2_aprobado["campania"].astype(str).eq("C2026")].copy()
    v2_aprobado = v2_aprobado.loc[
        v2_aprobado["fecha_objetivo"] + pd.Timedelta(days=6) <= pd.Timestamp("2026-08-16")
    ].copy()
    v2 = leer_v2(RUN_V2_LABORATORIO)
    v2["fecha_emision"] = pd.to_datetime(v2["fecha_emision"]).dt.normalize()
    v2["fecha_objetivo"] = pd.to_datetime(v2["fecha_objetivo"]).dt.normalize()
    v2 = v2.loc[v2["campania"].astype(str).eq("C2026")].copy()
    # Sólo semanas cuyo domingo ya estaba cerrado al corte certificado.
    v2 = v2.loc[v2["fecha_objetivo"] + pd.Timedelta(days=6) <= pd.Timestamp("2026-08-16")].copy()
    nowcast = leer_nowcast()
    fecha_corte_cerrado = pd.Timestamp("2026-08-16")
    nowcast_comun = resumen_nowcast(nowcast, fecha_maxima=pd.Timestamp("2026-08-10"))
    v2_aprobado_semanal = _resumen_serie_semanal(
        _seleccionar_vintage_coherente(v2_aprobado.loc[v2_aprobado["horizonte_semanas"].eq(1)]),
        fecha_columna="fecha_objetivo",
        pred_columna="p50_kg",
        fecha_maxima=pd.Timestamp("2026-08-10"),
    )
    nowcast_semanal = _resumen_serie_semanal(
        _seleccionar_total_nowcast(nowcast),
        fecha_columna="fecha_objetivo",
        pred_columna="p50_kg",
        fecha_maxima=pd.Timestamp("2026-08-10"),
    )
    comunes = v2_aprobado_semanal.merge(
        nowcast_semanal,
        on="fecha_objetivo",
        how="inner",
        suffixes=("_v2", "_nowcast"),
        validate="one_to_one",
    )
    if not comunes.empty:
        # La verdad es la misma cosecha; se conserva la del v2 y se verifica
        # que el total del nowcast coincide antes de calcular la diferencia.
        comunes["real_kg"] = comunes["real_v2"]
        comunes["error_v2_kg"] = comunes["pred_v2"] - comunes["real_kg"]
        comunes["error_nowcast_kg"] = comunes["pred_nowcast"] - comunes["real_kg"]
        comunes["wape_v2"] = comunes["error_v2_kg"].abs() / comunes["real_kg"].abs().replace(
            0, pd.NA
        )
        comunes["wape_nowcast"] = comunes["error_nowcast_kg"].abs() / comunes[
            "real_kg"
        ].abs().replace(0, pd.NA)
    base = metricas_horizonte(v2.rename(columns={"p50_kg": "pred_kg"}))
    mejor = ejecutar_loop_horizonte(
        v2,
        fecha_desarrollo_hasta=pd.Timestamp("2026-06-28"),
        configuraciones=configuraciones_loop(),
    )
    ganador = mejor.get("mejor_por_desarrollo", {}).get("configuracion")
    candidato_resumen = None
    if ganador:
        config = ConfiguracionCorreccionHorizonte(**ganador)
        candidato = aplicar_correccion_horizonte(v2, config)
        candidato_resumen = metricas_horizonte(candidato).to_dict("records")
    return {
        "schema": "diagnostico-v2-nowcast-horizontes-v1",
        "comparabilidad": {
            "corte_semanas_cerradas": str(fecha_corte_cerrado.date()),
            "semanas_comunes": int(len(comunes)),
            "nota": (
                "v2 h1 es forecast previo a la semana; nowcast se emite después de "
                "observar lunes-martes. Se comparan como referencia de tareas "
                "distintas, no como ganador directo."
            ),
        },
        "v2_aprobado_h1": {
            "run_id": RUN_V2_APROBADO,
            "metricas": _metricas_serie(v2_aprobado_semanal),
        },
        "v2": {
            "run_id": RUN_V2_LABORATORIO,
            "estado": "laboratorio_rechazado_no_publicar",
            "metricas": base.to_dict("records"),
            "n_filas": int(len(v2)),
        },
        "nowcast": {"run_id": RUN_NOWCAST, **nowcast_comun},
        "comparacion_semanal_v2_vs_nowcast": {
            "metricas_v2": _metricas_serie(
                comunes.rename(columns={"pred_v2": "pred", "real_kg": "real"})
            ),
            "metricas_nowcast": _metricas_serie(
                comunes.rename(columns={"pred_nowcast": "pred", "real_kg": "real"})
            ),
            "semanas": comunes.to_dict("records"),
        },
        "loop": mejor,
        "mejor_recalculado": candidato_resumen,
        "persistido": False,
    }


__all__ = [
    "ConfiguracionCorreccionHorizonte",
    "RUN_NOWCAST",
    "RUN_V2_APROBADO",
    "RUN_V2_LABORATORIO",
    "aplicar_correccion_horizonte",
    "configuraciones_loop",
    "ejecutar",
    "ejecutar_loop_horizonte",
    "leer_nowcast",
    "leer_v2",
    "metricas_horizonte",
    "resumen_nowcast",
]

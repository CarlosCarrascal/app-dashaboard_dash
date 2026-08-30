"""Genera la emisión operativa de ``HibridoOcurrenciaOnline_v2``.

La curva MacroLegacy de la emisión vigente se conserva como estructura de lote–paña.
El corrector v2 se ejecuta sobre una rejilla lote–semana construida con:

* cosecha real histórica disponible antes de la emisión;
* la curva MacroLegacy futura de la emisión actual.

Después, el resultado semanal del híbrido se reparte entre las pañas originales en
proporción a sus kilos MacroLegacy. Así el dashboard conserva el detalle operativo y
la suma semanal coincide exactamente con el cálculo v2.

Este script no lee Excel ni modifica R09. Crea una nueva corrida ``project``
experimental; la vista del dashboard decide explícitamente qué modelo operativo leer.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from analitica import settings
from analitica.dominio.modelos.ocurrencia_v2 import (
    NOMBRE_MODELO,
    VERSION_MODELO,
    ejecutar_replay_hibrido_ocurrencia_v2,
)
from analitica.dominio.versiones import banda_horizonte
from analitica.infraestructura.persistencia import RepositorioAnalytics

MODELO_BASE = "ModeloOperativoActual_v1"
CLAVES_SEMANA = ["campania", "lote_id", "fecha_objetivo"]


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _semana_inicio(serie: pd.Series) -> pd.Series:
    fechas = pd.to_datetime(serie, errors="raise")
    return fechas - pd.to_timedelta(fechas.dt.weekday, unit="D")


def _primero(serie: pd.Series):
    valores = serie.dropna()
    return valores.iloc[0] if not valores.empty else None


def _cargar_fuentes() -> tuple[pd.DataFrame, pd.DataFrame, int, int, pd.Timestamp]:
    """Carga la emisión base y el histórico Macro sin usar el futuro."""
    import psycopg

    dsn = settings.postgres_dsn()
    if not dsn:
        raise RuntimeError("No existe ANALYTICS_DATABASE_URL ni configuración PG utilizable")

    with psycopg.connect(dsn, connect_timeout=5) as conexion:
        actual = pd.read_sql_query(
            """
            WITH ultima AS (
                SELECT r.run_id, r.snapshot_id
                FROM analytics.forecast_run r
                JOIN analytics.prediction p USING (run_id)
                WHERE r.tipo = 'project'
                  AND r.estado IN ('succeeded', 'published')
                  AND p.modelo = 'ModeloOperativoActual_v1'
                GROUP BY r.run_id, r.snapshot_id, r.fin
                ORDER BY r.fin DESC NULLS LAST, r.run_id DESC
                LIMIT 1
            )
            SELECT p.*, u.snapshot_id AS fuente_snapshot_id,
                   u.run_id AS fuente_run_id
            FROM analytics.prediction p
            JOIN ultima u USING (run_id)
            ORDER BY p.fecha_objetivo, p.lote_id
            """,
            conexion,
        )

        if actual.empty:
            raise RuntimeError("No existe una emisión operativa MacroLegacy persistida")

        actual["fecha_objetivo"] = pd.to_datetime(actual["fecha_objetivo"], errors="raise")
        actual["fecha_emision"] = pd.to_datetime(actual["fecha_emision"], errors="raise")
        campanias = actual["campania"].dropna().astype(str).unique()
        if len(campanias) != 1:
            raise ValueError(f"La emisión operativa debe contener una campaña: {campanias}")
        campania = str(campanias[0])
        emision = actual["fecha_emision"].max().normalize()
        semana_emision = emision - pd.Timedelta(days=emision.weekday())
        fuente_run_id = int(actual["fuente_run_id"].iloc[0])
        snapshot_id = int(actual["fuente_snapshot_id"].iloc[0])

        historico = pd.read_sql_query(
            """
            WITH ultima AS (
                SELECT r.run_id
                FROM analytics.forecast_run r
                JOIN analytics.prediction p USING (run_id)
                WHERE r.tipo = 'backtest'
                  AND r.estado IN ('succeeded', 'published')
                  AND p.modelo = 'MacroLegacy_v1'
                  AND p.campania = %s
                GROUP BY r.run_id, r.fin
                ORDER BY r.fin DESC NULLS LAST, r.run_id DESC
                LIMIT 1
            )
            SELECT p.*
            FROM analytics.prediction p
            JOIN ultima u USING (run_id)
            WHERE p.modelo = 'MacroLegacy_v1'
              AND p.campania = %s
              AND p.fecha_objetivo < %s
              AND p.real_kg IS NOT NULL
            ORDER BY p.fecha_objetivo, p.lote_id
            """,
            conexion,
            params=(campania, campania, semana_emision.date()),
        )

    if historico.empty:
        raise RuntimeError(f"No existe histórico MacroLegacy as-of para {campania}")
    historico["fecha_objetivo"] = pd.to_datetime(historico["fecha_objetivo"], errors="raise")
    historico["fecha_emision"] = emision
    return actual, historico, snapshot_id, fuente_run_id, emision


def _agregar_semana(tabla: pd.DataFrame) -> pd.DataFrame:
    """Pasa de lote–paña a una fila única por lote–semana."""
    salida = tabla.copy()
    salida["fecha_objetivo"] = _semana_inicio(salida["fecha_objetivo"])
    salida["p50_kg"] = pd.to_numeric(salida["p50_kg"], errors="coerce").fillna(0.0)
    if "real_kg" not in salida:
        salida["real_kg"] = np.nan
    salida["real_kg"] = pd.to_numeric(salida["real_kg"], errors="coerce")
    agregaciones: dict[str, object] = {
        "p50_kg": "sum",
        "real_kg": "sum",
        "empresa": _primero,
        "fundo": _primero,
        "modulo": _primero,
        "lote": _primero,
        "plantas": _primero,
        "frutos_por_planta": _primero,
        "peso_baya_g": _primero,
        "fecha_emision": _primero,
        "horizonte_semanas": _primero,
        "banda_horizonte": _primero,
        "componentes": _primero,
    }
    for columna in list(agregaciones):
        if columna not in salida:
            agregaciones.pop(columna)
    return (
        salida.groupby(CLAVES_SEMANA, as_index=False, dropna=False)
        .agg(agregaciones)
        .sort_values(["fecha_objetivo", "lote_id"])
        .reset_index(drop=True)
    )


def _construir_base(
    actual: pd.DataFrame,
    historico: pd.DataFrame,
    emision: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    semana_emision = emision - pd.Timedelta(days=emision.weekday())
    futuro = actual.copy()
    futuro["fecha_objetivo"] = _semana_inicio(futuro["fecha_objetivo"])
    futuro = futuro[futuro["fecha_objetivo"] >= semana_emision].copy()
    pasado = historico.copy()
    pasado["fecha_objetivo"] = _semana_inicio(pasado["fecha_objetivo"])
    pasado = pasado[pasado["fecha_objetivo"] < semana_emision].copy()

    base = pd.concat([_agregar_semana(pasado), _agregar_semana(futuro)], ignore_index=True)
    if base.duplicated(CLAVES_SEMANA).any():
        raise ValueError("La rejilla v2 repite lote-semana después de agregar pañas")
    base["fecha_emision"] = emision
    base["real_kg"] = pd.to_numeric(base["real_kg"], errors="coerce")
    base["horizonte_semanas"] = (
        ((base["fecha_objetivo"] - semana_emision).dt.days.clip(lower=0) // 7)
        .astype(int)
        .clip(upper=52)
    )
    base["banda_horizonte"] = base["horizonte_semanas"].map(banda_horizonte)
    return base, futuro


def _componentes(valor) -> dict:
    if isinstance(valor, dict):
        return dict(valor)
    return {}


def _distribuir_a_panas(
    actual_futuro: pd.DataFrame,
    semanal_v2: pd.DataFrame,
    *,
    emision: pd.Timestamp,
    fuente_run_id: int,
    historico_run_id: int,
) -> pd.DataFrame:
    """Reparte el total v2 semanal manteniendo el detalle lote–paña de la Macro."""
    detalle = actual_futuro.copy()
    detalle["semana_inicio"] = _semana_inicio(detalle["fecha_objetivo"])
    detalle["p50_kg"] = pd.to_numeric(detalle["p50_kg"], errors="coerce").fillna(0.0)
    detalle["kg_legacy_pania"] = detalle["p50_kg"]
    grupo = detalle.groupby(["campania", "lote_id", "semana_inicio"], dropna=False)["p50_kg"]
    detalle["kg_macro_semana"] = grupo.transform("sum")
    v2 = semanal_v2.copy()
    v2["fecha_objetivo"] = pd.to_datetime(v2["fecha_objetivo"], errors="raise")
    v2 = v2.rename(columns={"p50_kg": "kg_v2_semana", "componentes": "componentes_v2"})
    v2 = v2[["campania", "lote_id", "fecha_objetivo", "kg_v2_semana", "componentes_v2"]]
    detalle = detalle.merge(
        v2,
        left_on=["campania", "lote_id", "semana_inicio"],
        right_on=["campania", "lote_id", "fecha_objetivo"],
        how="left",
        validate="many_to_one",
        suffixes=("", "_v2"),
    )
    if detalle["kg_v2_semana"].isna().any():
        faltantes = detalle.loc[detalle["kg_v2_semana"].isna(), ["lote_id", "semana_inicio"]]
        raise ValueError(
            f"v2 no produjo todas las semanas futuras: {faltantes.head().to_dict('records')}"
        )
    participacion = detalle["p50_kg"].div(detalle["kg_macro_semana"].replace(0, np.nan))
    participacion = participacion.fillna(
        1.0 / detalle.groupby(["campania", "lote_id", "semana_inicio"])["p50_kg"].transform("size")
    )
    detalle["p50_kg"] = (detalle["kg_v2_semana"] * participacion).clip(lower=0.0)
    detalle["modelo"] = NOMBRE_MODELO
    detalle["version_modelo"] = VERSION_MODELO
    detalle["version_fuente"] = f"operativo_macro_run_{fuente_run_id}_hist_run_{historico_run_id}"
    detalle["fecha_emision"] = emision
    semana_emision = emision - pd.Timedelta(days=emision.weekday())
    detalle["horizonte_semanas"] = (
        ((_semana_inicio(detalle["fecha_objetivo"]) - semana_emision).dt.days.clip(lower=0) // 7)
        .astype(int)
        .clip(upper=52)
    )
    detalle["banda_horizonte"] = detalle["horizonte_semanas"].map(banda_horizonte)
    detalle["p10_kg"] = np.nan
    detalle["p90_kg"] = np.nan
    detalle["real_kg"] = np.nan
    detalle["confianza"] = "baja"
    detalle["origen_emision"] = emision
    detalle["tipo_prediccion"] = "operativa"
    detalle["es_replay_ciego"] = False
    detalle["es_curva_stitched"] = False
    detalle["estado_evaluacion"] = "pendiente"
    detalle["componentes"] = [
        {
            **_componentes(v2_componentes),
            "modelo": NOMBRE_MODELO,
            "modelo_base": MODELO_BASE,
            "kg_legacy_pania": float(legacy_pania),
            "kg_legacy_semana": float(legacy_semana),
            "kg_hibrido_semana": float(kg_v2),
            "participacion_pania": float(participacion_i),
            "fuente_run_operativo": fuente_run_id,
            "fuente_run_historico": historico_run_id,
            "fecha_corte": emision.date().isoformat(),
            "etiqueta_causal": False,
        }
        for v2_componentes, legacy_pania, legacy_semana, kg_v2, participacion_i in zip(
            detalle["componentes_v2"],
            detalle["kg_legacy_pania"],
            detalle["kg_macro_semana"],
            detalle["kg_v2_semana"],
            participacion,
            strict=False,
        )
    ]
    return detalle.drop(
        columns=[
            "semana_inicio",
            "kg_macro_semana",
            "kg_v2_semana",
            "componentes_v2",
            "kg_legacy_pania",
            "fecha_objetivo_v2",
        ],
        errors="ignore",
    )


def construir_corrida() -> tuple[pd.DataFrame, dict[str, object]]:
    actual, historico, snapshot_id, fuente_run_id, emision = _cargar_fuentes()
    historico_run_id = int(historico["run_id"].iloc[0])
    base, futuro = _construir_base(actual, historico, emision)
    v2, resumen = ejecutar_replay_hibrido_ocurrencia_v2(base)
    semana_emision = emision - pd.Timedelta(days=emision.weekday())
    v2_futuro = v2[pd.to_datetime(v2["fecha_objetivo"]) >= semana_emision].copy()
    detalle = _distribuir_a_panas(
        futuro,
        v2_futuro,
        emision=emision,
        fuente_run_id=fuente_run_id,
        historico_run_id=historico_run_id,
    )
    if (
        len(detalle) != len(futuro)
        or detalle.duplicated(["campania", "lote_id", "fecha_objetivo"]).any()
    ):
        raise AssertionError("La emisión v2 no conserva el detalle operativo lote-paña")
    meta = {
        "modelo": NOMBRE_MODELO,
        "version_modelo": VERSION_MODELO,
        "modelo_base": MODELO_BASE,
        "campania": str(actual["campania"].iloc[0]),
        "fecha_emision": emision.date().isoformat(),
        "snapshot_id": snapshot_id,
        "fuente_run_operativo": fuente_run_id,
        "fuente_run_historico": historico_run_id,
        "filas_base_semanal": int(len(base)),
        "filas_salida_lote_pania": int(len(detalle)),
        "semanas_futuras": int(v2_futuro["fecha_objetivo"].nunique()),
        "kg_macro_futuro": float(futuro["p50_kg"].sum()),
        "kg_v2_futuro": float(v2_futuro["p50_kg"].sum()),
        "nota": "El híbrido se muestra como experimental; R09 continúa como referencia publicada.",
    }
    return detalle, meta


def persistir(dry_run: bool = False) -> dict[str, object]:
    detalle, meta = construir_corrida()
    if dry_run:
        return meta
    repo = RepositorioAnalytics(settings.postgres_dsn())
    run_id = repo.crear_run(
        int(meta["snapshot_id"]),
        "project",
        {
            "modelo_proyeccion": NOMBRE_MODELO,
            "version_modelo": VERSION_MODELO,
            "modelo_base": MODELO_BASE,
            "publicacion": "experimental",
            "fecha_emision": meta["fecha_emision"],
            "fuente_run_operativo": meta["fuente_run_operativo"],
            "fuente_run_historico": meta["fuente_run_historico"],
            "regla_detalle": (
                "resultado semanal v2 repartido proporcionalmente entre pañas MacroLegacy"
            ),
            "uso": "dashboard_operativo_experimental",
        },
    )
    try:
        repo.guardar_predicciones(run_id, detalle)
        repo.finalizar_run(run_id, "succeeded")
    except Exception as exc:
        repo.finalizar_run(run_id, "failed", str(exc))
        raise
    meta["run_id"] = run_id
    return meta


__all__ = [
    "MODELO_BASE",
    "CLAVES_SEMANA",
    "NOMBRE_MODELO",
    "VERSION_MODELO",
    "banda_horizonte",
    "construir_corrida",
    "persistir",
]

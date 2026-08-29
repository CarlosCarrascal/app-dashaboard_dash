"""Servicio reusable para validar externamente el nowcast intra-semanal.

La configuración se eligió en C2026 hasta S30. Este servicio la aplica sin
retocar parámetros a C2024 y C2025. No persiste ni publica; la interfaz CLI
histórica permanece en ``analitica.scripts.validate_intraweek_nowcast_external``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analitica.proyeccion.candidate_preflight import escribir_json_reproducible
from analitica.servicios.nowcast import (
    ACCESS_DEFAULT,
    R09_ACCESS_DEFAULT,
    Configuracion,
    calibrar_residuo_online,
    comparacion_pareada,
    leer_diario,
    metricas,
    predecir,
)
from analitica.servicios.parametros_nowcast import (
    leer_macro_h1,
    leer_reales_r09_fundo,
)

CONFIGURACION_CONGELADA = Configuracion(4, 16.0, 0.50, 0.20, 0.65)
CALIBRACION_CONGELADA = {"lookback": 2, "shrink": 8.0}
RUNS_CERTIFICADOS = {"C2024": 78, "C2025": 78, "C2026": 76}


def _construir_contrato(
    *,
    campania: str,
    run_id: int,
    access: Path,
    r09_access: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    macro_fundo = leer_macro_h1(campania, run_id=run_id)
    macro = macro_fundo.groupby(
        ["campania", "fecha_emision", "fecha_objetivo", "semana_emision", "semana_objetivo"],
        as_index=False,
    ).macro_kg.sum()
    diario = leer_diario(access, campania)
    diario["fecha_objetivo"] = diario.fecha - pd.to_timedelta(diario.dia_iso - 1, unit="D")
    semanal_fundo = diario.groupby(["fecha_objetivo", "fundo_operativo"], as_index=False).agg(
        real_kg=("kg", "sum"),
        montue_kg=("kg", lambda x: float(x[diario.loc[x.index, "dia_iso"].le(2)].sum())),
        fecha_max=("fecha", "max"),
    )
    semanal_fundo["semana_objetivo"] = (
        semanal_fundo["fecha_objetivo"].dt.isocalendar().week.astype(int)
    )
    semanal = semanal_fundo.groupby("fecha_objetivo", as_index=False).agg(
        real_kg=("real_kg", "sum"),
        montue_kg=("montue_kg", "sum"),
        fecha_max=("fecha_max", "max"),
    )
    ultima_fecha_real = semanal.fecha_max.max()
    macro = macro.loc[macro.fecha_objetivo.le(ultima_fecha_real)].copy()
    tabla = macro.merge(semanal, on="fecha_objetivo", how="left", validate="one_to_one")
    tabla[["real_kg", "montue_kg"]] = tabla[["real_kg", "montue_kg"]].fillna(0.0)

    _, r09_fundo = leer_reales_r09_fundo(r09_access, campania)
    r09 = r09_fundo.groupby(["semana_emision", "semana_objetivo"], as_index=False).r09_kg.sum()
    tabla = tabla.merge(
        r09.rename(columns={"r09_kg": "r09_previo_kg"}),
        on=["semana_emision", "semana_objetivo"],
        how="left",
        validate="many_to_one",
    )
    misma = r09.copy()
    misma["semana_emision"] = misma.semana_emision - 1
    tabla = tabla.merge(
        misma.rename(columns={"r09_kg": "r09_misma_semana_kg"}),
        on=["semana_emision", "semana_objetivo"],
        how="left",
        validate="many_to_one",
    )
    tabla = tabla.sort_values("fecha_objetivo", kind="stable").reset_index(drop=True)
    return tabla, semanal_fundo, macro_fundo


def _predecir_fundos(
    final_empresa: pd.DataFrame,
    semanal_fundo: pd.DataFrame,
    macro_fundo: pd.DataFrame,
    *,
    campania: str,
    r09_access: Path,
) -> pd.DataFrame:
    """Reconstruye la misma combinación por fundo para auditar degradaciones."""

    _, r09_fundo = leer_reales_r09_fundo(r09_access, campania)
    filas: list[dict[str, object]] = []
    for empresa in final_empresa.itertuples(index=False):
        fecha = pd.Timestamp(empresa.fecha_objetivo).normalize()
        semana = int(empresa.semana_objetivo)
        historia = semanal_fundo.loc[semanal_fundo.fecha_objetivo.lt(fecha)].copy()
        semanas = sorted(historia.fecha_objetivo.unique())[-CONFIGURACION_CONGELADA.lookback :]
        historia = historia.loc[
            historia.fecha_objetivo.isin(semanas) & historia.real_kg.gt(0)
        ].copy()
        historia["share"] = historia.montue_kg / historia.real_kg
        historia = historia.loc[
            historia.share.between(
                CONFIGURACION_CONGELADA.piso_share,
                CONFIGURACION_CONGELADA.techo_share,
            )
        ]
        global_share = None if historia.empty else float(historia.share.median())
        actual = semanal_fundo.loc[semanal_fundo.fecha_objetivo.eq(fecha)].copy()
        base = macro_fundo.loc[macro_fundo.fecha_objetivo.eq(fecha)].copy()
        universo = base[["fundo_operativo", "macro_kg"]].merge(
            actual[["fundo_operativo", "real_kg", "montue_kg"]],
            on="fundo_operativo",
            how="outer",
            validate="one_to_one",
        )
        universo[["macro_kg", "real_kg", "montue_kg"]] = universo[
            ["macro_kg", "real_kg", "montue_kg"]
        ].fillna(0.0)
        for fondo in universo.itertuples(index=False):
            local = historia.loc[historia.fundo_operativo.eq(fondo.fundo_operativo), "share"]
            if global_share is None:
                pace = float(fondo.macro_kg)
            else:
                local_share = float(local.median()) if len(local) else global_share
                peso_local = len(local) / (len(local) + CONFIGURACION_CONGELADA.shrink_fundo)
                share = peso_local * local_share + (1.0 - peso_local) * global_share
                share = float(
                    min(
                        CONFIGURACION_CONGELADA.techo_share,
                        max(CONFIGURACION_CONGELADA.piso_share, share),
                    )
                )
                pace = max(float(fondo.montue_kg), float(fondo.montue_kg) / share)
            raw = CONFIGURACION_CONGELADA.peso_ritmo * pace + (
                1.0 - CONFIGURACION_CONGELADA.peso_ritmo
            ) * float(fondo.macro_kg)
            filas.append(
                {
                    "fecha_objetivo": fecha,
                    "semana_objetivo": semana,
                    "semana_emision": int(empresa.semana_emision),
                    "fundo_operativo": fondo.fundo_operativo,
                    "real_kg": float(fondo.real_kg),
                    "macro_kg": float(fondo.macro_kg),
                    "pace_kg": pace,
                    "candidate_kg": raw * float(empresa.escala_residual),
                }
            )
    detalle = pd.DataFrame(filas)
    previo = r09_fundo.rename(columns={"r09_kg": "r09_previo_kg"})
    detalle = detalle.merge(
        previo,
        on=["semana_emision", "semana_objetivo", "fundo_operativo"],
        how="left",
        validate="many_to_one",
    )
    misma = r09_fundo.copy()
    misma["semana_emision"] = misma.semana_emision - 1
    detalle = detalle.merge(
        misma.rename(columns={"r09_kg": "r09_misma_semana_kg"}),
        on=["semana_emision", "semana_objetivo", "fundo_operativo"],
        how="left",
        validate="many_to_one",
    )
    return detalle.sort_values(["fecha_objetivo", "fundo_operativo"], kind="stable")


def _resumen_fundos(detalle: pd.DataFrame) -> dict[str, object]:
    por_fundo: dict[str, object] = {}
    for fundo, bloque in detalle.groupby("fundo_operativo"):
        por_fundo[str(fundo)] = {
            "nowcast": metricas(bloque, "candidate_kg"),
            "macro": metricas(bloque, "macro_kg"),
            "pareado_vs_r09_presemana": comparacion_pareada(bloque, "r09_previo_kg"),
            "pareado_vs_r09_misma_semana": comparacion_pareada(bloque, "r09_misma_semana_kg"),
        }
    return {
        "fundo_semana": metricas(detalle, "candidate_kg"),
        "por_fundo": por_fundo,
    }


def evaluar_campania(
    *,
    campania: str,
    run_id: int,
    access: Path,
    r09_access: Path,
) -> dict[str, object]:
    contrato, semanal_fundo, macro_fundo = _construir_contrato(
        campania=campania,
        run_id=run_id,
        access=access,
        r09_access=r09_access,
    )
    crudo = predecir(contrato, semanal_fundo, CONFIGURACION_CONGELADA)
    final = calibrar_residuo_online(crudo, **CALIBRACION_CONGELADA)
    detalle_fundo = _predecir_fundos(
        final,
        semanal_fundo,
        macro_fundo,
        campania=campania,
        r09_access=r09_access,
    )
    return {
        "campania": campania,
        "run_macro": run_id,
        "n_semanas": int(len(final)),
        "rango": [str(final.fecha_objetivo.min().date()), str(final.fecha_objetivo.max().date())],
        "real_kg": float(final.real_kg.sum()),
        "nowcast": metricas(final, "candidate_kg"),
        "macro_presemana": metricas(final, "macro_kg"),
        "pareado_vs_r09_presemana": comparacion_pareada(final, "r09_previo_kg"),
        "pareado_vs_r09_misma_semana": comparacion_pareada(final, "r09_misma_semana_kg"),
        "auditoria_fundos": _resumen_fundos(detalle_fundo),
    }


def ejecutar(
    *,
    access: Path = ACCESS_DEFAULT,
    r09_access: Path = R09_ACCESS_DEFAULT,
) -> dict[str, object]:
    resultados = {
        campania: evaluar_campania(
            campania=campania,
            run_id=run_id,
            access=access,
            r09_access=r09_access,
        )
        for campania, run_id in RUNS_CERTIFICADOS.items()
    }
    return {
        "schema": "validate-intraweek-nowcast-external-v1",
        "configuracion_congelada": CONFIGURACION_CONGELADA.id,
        "calibracion_congelada": CALIBRACION_CONGELADA,
        "seleccion": "configuración elegida solo con C2026 S13-S30",
        "fuente_reales": str(access),
        "fuente_r09": str(r09_access),
        "resultados": resultados,
        "persistencia_postgresql": False,
    }


__all__ = [
    "ACCESS_DEFAULT",
    "CALIBRACION_CONGELADA",
    "CONFIGURACION_CONGELADA",
    "Configuracion",
    "R09_ACCESS_DEFAULT",
    "RUNS_CERTIFICADOS",
    "calibrar_residuo_online",
    "comparacion_pareada",
    "ejecutar",
    "escribir_json_reproducible",
    "evaluar_campania",
    "leer_diario",
    "leer_macro_h1",
    "leer_reales_r09_fundo",
    "metricas",
    "predecir",
]

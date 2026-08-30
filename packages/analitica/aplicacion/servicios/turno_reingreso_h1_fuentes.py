"""Fuentes y preparación del contrato congelado H1 de run76."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import psycopg

from analitica.settings import postgres_dsn

RUN_ID = 76
CAMPANIA = "C2026"
SEMANA_INICIAL = 13
SEMANA_FINAL = 33
SEMANA_DESARROLLO_FINAL = 30
CIERRE_CERTIFICADO = pd.Timestamp("2026-08-16")
CONTRACT_ID = "run76-c2026-h1-s13-s33-closed"

CLAVE_LOTE = [
    "campania",
    "fecha_emision",
    "fecha_objetivo",
    "horizonte_semanas",
    "lote_id",
]

MAPEO_FUNDO = {
    "aqu anqa 1": "Arena",
    "aqu anqa 2": "Quri",
    "aqu anqa 3": "Kawsay",
    "aqu anqa 4": "Ayllu",
    "aqu anqa 5": "Kawsay",
}


def _normalizar_fundo(valor: object) -> str:
    texto = str(valor or "").strip()
    return MAPEO_FUNDO.get(texto.casefold(), texto)


def _emitio_r09(componentes: object) -> bool:
    if isinstance(componentes, dict):
        return bool(componentes.get("emitio_prediccion", False))
    if isinstance(componentes, str):
        try:
            valor = json.loads(componentes)
        except json.JSONDecodeError:
            return False
        return bool(valor.get("emitio_prediccion", False))
    return False


def leer_fuentes() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Lee run76 y H01 sin efectuar escrituras ni bloquear tablas."""

    consulta = """
        SELECT campania, fecha_emision, fecha_objetivo, horizonte_semanas,
               lote_id, fundo, modulo, p50_kg, real_kg, componentes
        FROM analytics.prediction
        WHERE run_id=%s AND campania=%s AND modelo=%s
          AND horizonte_semanas=1 AND fecha_emision < fecha_objetivo
        ORDER BY fecha_emision, lote_id
    """
    consulta_h01 = """
        SELECT campania, lote_id, fecha, turno, SUM(kg) AS kg
        FROM stg.h01_cosecha
        WHERE campania=%s
        GROUP BY campania, lote_id, fecha, turno
        ORDER BY lote_id, fecha
    """
    with psycopg.connect(postgres_dsn()) as conexion:
        macro = pd.read_sql_query(
            consulta,
            conexion,
            params=[RUN_ID, CAMPANIA, "MacroLegacy_v1"],
        )
        r09 = pd.read_sql_query(
            consulta,
            conexion,
            params=[RUN_ID, CAMPANIA, "R09_publicado"],
        )
        h01 = pd.read_sql_query(
            consulta_h01,
            conexion,
            params=[CAMPANIA],
        )
    return macro, r09, h01


def preparar_contrato(
    macro: pd.DataFrame,
    r09: pd.DataFrame,
) -> pd.DataFrame:
    """Alinea ambos baselines sin cambiar el universo real de run76."""

    if macro.empty:
        raise ValueError("run76 no contiene MacroLegacy_v1 h1 para C2026")
    requeridas = set(CLAVE_LOTE + ["fundo", "modulo", "p50_kg", "real_kg"])
    faltantes = sorted(requeridas.difference(macro.columns))
    if faltantes:
        raise ValueError(f"Macro run76 no cumple el contrato: {faltantes}")

    base = macro.copy()
    referencia = r09.copy()
    for tabla in (base, referencia):
        tabla["fecha_emision"] = pd.to_datetime(tabla.fecha_emision, errors="raise").dt.normalize()
        tabla["fecha_objetivo"] = pd.to_datetime(
            tabla.fecha_objetivo, errors="raise"
        ).dt.normalize()
        tabla["horizonte_semanas"] = pd.to_numeric(tabla.horizonte_semanas, errors="raise").astype(
            int
        )
        tabla["p50_kg"] = pd.to_numeric(tabla.p50_kg, errors="raise")
        tabla["real_kg"] = pd.to_numeric(tabla.real_kg, errors="raise")
        tabla["semana_objetivo"] = tabla.fecha_objetivo.dt.isocalendar().week.astype(int)
        tabla["semana_fin"] = tabla.fecha_objetivo + pd.Timedelta(days=6)

    base = base[
        base.semana_objetivo.between(SEMANA_INICIAL, SEMANA_FINAL)
        & base.semana_fin.le(CIERRE_CERTIFICADO)
    ].copy()
    referencia = referencia[
        referencia.semana_objetivo.between(SEMANA_INICIAL, SEMANA_FINAL)
        & referencia.semana_fin.le(CIERRE_CERTIFICADO)
    ].copy()
    if base.duplicated(CLAVE_LOTE).any() or referencia.duplicated(CLAVE_LOTE).any():
        raise ValueError("run76 contiene claves lote-emisión-semana duplicadas")

    # ``componentes`` de Macro no participa en este candidato. Se elimina antes
    # del cruce para que la única bandera de emisión sea la declarada por R09.
    base = base.drop(columns=["componentes"], errors="ignore")
    columnas_r09 = CLAVE_LOTE + ["p50_kg", "real_kg", "componentes"]
    referencia = referencia[columnas_r09].rename(
        columns={"p50_kg": "r09_kg", "real_kg": "real_r09_kg"}
    )
    contrato = base.merge(
        referencia,
        on=CLAVE_LOTE,
        how="left",
        validate="one_to_one",
    )
    if contrato.r09_kg.isna().any():
        raise ValueError("R09 run76 no cubre las mismas claves contractuales que Macro")
    if not np.allclose(contrato.real_kg, contrato.real_r09_kg, equal_nan=True):
        raise ValueError("Macro y R09 no conservan el mismo real en run76")

    contrato["fundo"] = contrato.fundo.map(_normalizar_fundo)
    fondos = set(contrato.fundo.dropna().astype(str))
    esperados = {"Arena", "Ayllu", "Kawsay", "Quri"}
    if fondos != esperados:
        raise ValueError(f"El contrato no contiene exactamente cuatro fundos: {fondos}")
    contrato["macro_kg"] = contrato.p50_kg
    contrato["r09_emitio"] = contrato.componentes.map(_emitio_r09)
    contrato["evaluation_contract_id"] = CONTRACT_ID
    contrato["modelo"] = "MacroLegacy_v1"
    contrato["version_modelo"] = "run76_congelada"
    contrato["tipo_prediccion"] = "forecast"
    contrato["incluye_en_metricas_forecast"] = True
    contrato["split"] = np.where(
        contrato.semana_objetivo.le(SEMANA_DESARROLLO_FINAL),
        "desarrollo_s13_s30",
        "holdout_s31_s33",
    )
    return contrato.reset_index(drop=True)

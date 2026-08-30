"""Fuentes y preparación del contrato congelado de run73.

Este módulo contiene la frontera de lectura y las validaciones que convierten
las filas de PostgreSQL en el contrato de evaluación H1-H6. No importa la
fachada histórica ``turno_reingreso``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import psycopg

from analitica.settings import postgres_dsn

RUN_ID = 73
CAMPANIA = "C2026"
HORIZONTE_MIN = 1
HORIZONTE_MAX = 6
SEMANA_INICIAL = 13
SEMANA_DESARROLLO_FINAL = 30
SEMANA_FINAL = 33
CIERRE_CERTIFICADO = pd.Timestamp("2026-08-16")
CONTRACT_ID = "run73-c2026-macro-h1-h6-s13-s33-closed"

CLAVE = [
    "campania",
    "fecha_emision",
    "fecha_objetivo",
    "horizonte_semanas",
    "lote_id",
]
GRUPO_CURVA = ["campania", "fecha_emision", "lote_id"]

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


def leer_fuentes() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Consulta run73 y H01 dentro de una transaccion explicitamente read-only."""

    consulta = """
        SELECT campania, fecha_emision, fecha_objetivo, horizonte_semanas,
               lote_id, fundo, modulo, p50_kg, real_kg, componentes
        FROM analytics.prediction
        WHERE run_id=%s AND campania=%s AND modelo=%s
          AND horizonte_semanas BETWEEN %s AND %s
          AND fecha_emision < fecha_objetivo
        ORDER BY fecha_emision, lote_id, horizonte_semanas
    """
    consulta_h01 = """
        SELECT campania, lote_id, fecha, turno, SUM(kg) AS kg
        FROM stg.h01_cosecha
        WHERE campania=%s
        GROUP BY campania, lote_id, fecha, turno
        ORDER BY lote_id, fecha
    """
    with psycopg.connect(postgres_dsn()) as conexion:
        conexion.execute("SET TRANSACTION READ ONLY")
        macro = pd.read_sql_query(
            consulta,
            conexion,
            params=[
                RUN_ID,
                CAMPANIA,
                "MacroLegacy_v1",
                HORIZONTE_MIN,
                HORIZONTE_MAX,
            ],
        )
        r09 = pd.read_sql_query(
            consulta,
            conexion,
            params=[
                RUN_ID,
                CAMPANIA,
                "R09_publicado",
                HORIZONTE_MIN,
                HORIZONTE_MAX,
            ],
        )
        h01 = pd.read_sql_query(consulta_h01, conexion, params=[CAMPANIA])
    return macro, r09, h01


def preparar_macro(macro: pd.DataFrame) -> pd.DataFrame:
    """Congela el contrato h1-h6 y rechaza curvas incompletas o mezcladas."""

    requeridas = set(CLAVE + ["fundo", "modulo", "p50_kg", "real_kg"])
    faltantes = sorted(requeridas.difference(macro.columns))
    if faltantes:
        raise ValueError(f"Macro run73 no cumple el contrato: {faltantes}")
    if macro.empty:
        raise ValueError("run73 no contiene MacroLegacy_v1 para C2026")

    base = macro.copy()
    base["fecha_emision"] = pd.to_datetime(base.fecha_emision, errors="raise").dt.normalize()
    base["fecha_objetivo"] = pd.to_datetime(base.fecha_objetivo, errors="raise").dt.normalize()
    base["horizonte_semanas"] = pd.to_numeric(base.horizonte_semanas, errors="raise").astype(int)
    base["p50_kg"] = pd.to_numeric(base.p50_kg, errors="raise")
    base["real_kg"] = pd.to_numeric(base.real_kg, errors="coerce")
    base = base[base.horizonte_semanas.between(HORIZONTE_MIN, HORIZONTE_MAX)].copy()
    if base.p50_kg.lt(0).any():
        raise ValueError("Macro run73 contiene predicciones negativas")
    if base.duplicated(CLAVE).any():
        raise ValueError("Macro run73 repite claves emision-objetivo-lote")

    esperados = list(range(HORIZONTE_MIN, HORIZONTE_MAX + 1))
    resumen = base.groupby(GRUPO_CURVA).horizonte_semanas.apply(
        lambda serie: sorted(int(v) for v in serie.unique())
    )
    incompletos = resumen[resumen.map(lambda valor: valor != esperados)]
    if len(incompletos):
        ejemplo = tuple(incompletos.index[0])
        raise ValueError(
            "run73 no conserva h1-h6 contiguos para todas las curvas; "
            f"primer grupo invalido={ejemplo}, horizontes={incompletos.iloc[0]}"
        )

    base["fundo"] = base.fundo.map(_normalizar_fundo)
    fundos = set(base.fundo.dropna().astype(str))
    if fundos != {"Arena", "Ayllu", "Kawsay", "Quri"}:
        raise ValueError(f"El contrato no contiene exactamente cuatro fundos: {fundos}")
    dimension = base.groupby("lote_id").agg(
        n_fundos=("fundo", "nunique"), n_modulos=("modulo", "nunique")
    )
    if dimension.n_fundos.gt(1).any() or dimension.n_modulos.gt(1).any():
        raise ValueError("Un lote cambia de fundo o modulo dentro de run73")

    lunes_emision = base.fecha_emision - pd.to_timedelta(base.fecha_emision.dt.weekday, unit="D")
    horizonte = ((base.fecha_objetivo - lunes_emision).dt.days // 7).astype(int)
    if horizonte.ne(base.horizonte_semanas).any():
        raise ValueError("El horizonte declarado no coincide con emision y objetivo")
    base["semana_objetivo"] = base.fecha_objetivo.dt.isocalendar().week.astype(int)
    base["semana_fin"] = base.fecha_objetivo + pd.Timedelta(days=6)
    evaluable = base.semana_objetivo.between(SEMANA_INICIAL, SEMANA_FINAL)
    evaluable &= base.semana_fin.le(CIERRE_CERTIFICADO)
    if base.loc[evaluable, "real_kg"].isna().any():
        raise ValueError("El contrato cerrado contiene cosecha real nula")

    reales = (
        base.loc[evaluable]
        .groupby(["campania", "fecha_objetivo", "lote_id"])
        .real_kg.agg(["min", "max"])
    )
    if (reales["max"] - reales["min"]).abs().gt(1e-6).any():
        raise ValueError("El real de una semana-lote cambia entre vintages")

    base["evaluation_contract_id"] = CONTRACT_ID
    base["modelo"] = "MacroLegacy_v1"
    base["version_modelo"] = "run73_congelada_h1_h6"
    base["tipo_prediccion"] = "forecast"
    base["incluye_en_metricas_forecast"] = evaluable
    base["split"] = np.select(
        [
            evaluable & base.semana_objetivo.le(SEMANA_DESARROLLO_FINAL),
            evaluable & base.semana_objetivo.gt(SEMANA_DESARROLLO_FINAL),
        ],
        ["desarrollo_s13_s30", "holdout_s31_s33"],
        default="fuera_evaluacion",
    )
    return base.sort_values(
        ["fecha_emision", "lote_id", "horizonte_semanas"], kind="stable"
    ).reset_index(drop=True)


def preparar_r09(r09: pd.DataFrame) -> pd.DataFrame:
    """Normaliza la referencia sin incorporarla a la seleccion del candidato."""

    if r09.empty:
        return pd.DataFrame(columns=CLAVE + ["r09_kg", "real_r09_kg"])
    requeridas = set(CLAVE + ["p50_kg", "real_kg"])
    faltantes = sorted(requeridas.difference(r09.columns))
    if faltantes:
        raise ValueError(f"R09 run73 no cumple el contrato: {faltantes}")
    ref = r09.copy()
    ref["fecha_emision"] = pd.to_datetime(ref.fecha_emision, errors="raise").dt.normalize()
    ref["fecha_objetivo"] = pd.to_datetime(ref.fecha_objetivo, errors="raise").dt.normalize()
    ref["horizonte_semanas"] = pd.to_numeric(ref.horizonte_semanas, errors="raise").astype(int)
    ref["p50_kg"] = pd.to_numeric(ref.p50_kg, errors="raise")
    ref["real_kg"] = pd.to_numeric(ref.real_kg, errors="coerce")
    ref = ref[
        ref.horizonte_semanas.between(HORIZONTE_MIN, HORIZONTE_MAX)
        & ref.fecha_emision.lt(ref.fecha_objetivo)
    ].copy()
    if ref.duplicated(CLAVE).any():
        raise ValueError("R09 run73 repite claves emision-objetivo-lote")
    return ref[CLAVE + ["p50_kg", "real_kg"]].rename(
        columns={"p50_kg": "r09_kg", "real_kg": "real_r09_kg"}
    )

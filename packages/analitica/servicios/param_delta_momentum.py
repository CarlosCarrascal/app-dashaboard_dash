"""Servicio de screening as-of para momentum y deltas de parámetros.

La regla no usa R09 para predecir. Parte de MacroLegacy congelada y solo acepta
los deltas X/O/N/A/B aprendidos de emisiones anteriores cuando ya existen tres
transiciones canónicas. El crecimiento reciente se informa como diagnóstico;
no se usa para elegir el umbral en este primer screening.

No persiste ni publica.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

from analitica.proyeccion.parametros import CandidateParamDelta
from analitica.servicios.parametros_replay import (
    ACCESS_DEFAULT,
    ROOT_DEFAULT,
    TRANSITIONS_DEFAULT,
    columna_campania,
    proyectar_emision_detallada,
)
from analitica.settings import postgres_dsn

MAPEO_FUNDO = {
    "aqu anqa 1": "Arena",
    "aqu anqa 2": "Quri",
    "aqu anqa 3": "Kawsay",
    "aqu anqa 4": "Ayllu",
    "aqu anqa 5": "Kawsay",
}


def _fundo(valor: object) -> str:
    texto = str(valor or "").strip()
    return MAPEO_FUNDO.get(texto.casefold(), texto)


def _leer_macro_h1(campania: str = "C2026", run_id: int = 76) -> pd.DataFrame:
    consulta = """
        SELECT campania, fecha_emision, fecha_objetivo, fundo,
               SUM(p50_kg) AS macro_kg, SUM(real_kg) AS real_pg_kg
        FROM analytics.prediction
        WHERE run_id=%s AND campania=%s AND modelo='MacroLegacy_v1'
          AND horizonte_semanas=1 AND fecha_emision < fecha_objetivo
        GROUP BY campania, fecha_emision, fecha_objetivo, fundo
    """
    with psycopg.connect(postgres_dsn()) as conexion:
        tabla = pd.read_sql_query(consulta, conexion, params=[run_id, campania])
    tabla["fecha_emision"] = pd.to_datetime(tabla.fecha_emision).dt.normalize()
    tabla["fecha_objetivo"] = pd.to_datetime(tabla.fecha_objetivo).dt.normalize()
    tabla["semana_emision"] = tabla.fecha_emision.dt.isocalendar().week.astype(int)
    tabla["semana_objetivo"] = tabla.fecha_objetivo.dt.isocalendar().week.astype(int)
    tabla["fundo_operativo"] = tabla.fundo.map(_fundo)
    return tabla.groupby(
        [
            "campania",
            "fecha_emision",
            "fecha_objetivo",
            "semana_emision",
            "semana_objetivo",
            "fundo_operativo",
        ],
        as_index=False,
    ).agg(macro_kg=("macro_kg", "sum"), real_pg_kg=("real_pg_kg", "sum"))


_columna_campania = columna_campania


def _leer_reales_r09_fundo(access: Path, campania: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError(
            "Este comando necesita pyodbc y el controlador ODBC de Microsoft Access."
        ) from exc
    cadena = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + str(access)
    with pyodbc.connect(cadena) as conexion:
        cursor = conexion.cursor()
        camp_h01 = _columna_campania(cursor, "H01_ProdHistorica")
        camp_r09 = _columna_campania(cursor, "R09_Forecast_Semanal")
        r09 = pd.read_sql(
            "SELECT [Fundo], [Version], [Sem], Sum([Kg]) AS total_kg "
            "FROM [R09_Forecast_Semanal] "
            f"WHERE [{camp_r09}] = ? GROUP BY [Fundo], [Version], [Sem]",
            conexion,
            params=[campania],
        )
    # M01-M04 de Aqu Anqa y M01-M05 de Aqu Anqa II colisionan si se ignora
    # el fundo físico; ambos campos son parte de la clave operativa.
    with pyodbc.connect(cadena) as conexion:
        reales = pd.read_sql(
            "SELECT [Fundo], [Modulo], [Semana], Sum([KG]) AS total_kg "
            "FROM [H01_ProdHistorica] "
            f"WHERE [{camp_h01}] = ? GROUP BY [Fundo], [Modulo], [Semana]",
            conexion,
            params=[campania],
        )
    reales.columns = ["fundo_fisico", "modulo", "semana_objetivo", "real_kg"]
    modulo = reales.modulo.astype(str).str.extract(r"(\d+)", expand=False).astype(float)
    fisico = reales.fundo_fisico.astype(str).str.casefold()
    reales["fundo_operativo"] = np.select(
        [
            fisico.eq("aqu anqa") & modulo.between(1, 4),
            fisico.eq("aqu anqa ii") & modulo.between(1, 5),
            fisico.eq("aqu anqa ii") & modulo.between(6, 11),
            fisico.eq("aqu anqa ii") & modulo.between(12, 15),
            fisico.eq("aqu anqa ii") & modulo.between(16, 17),
        ],
        ["Arena", "Quri", "Kawsay", "Ayllu", "Kawsay"],
        default="",
    )
    if reales.fundo_operativo.eq("").any():
        faltantes = reales.loc[
            reales.fundo_operativo.eq(""), ["fundo_fisico", "modulo"]
        ].drop_duplicates()
        raise ValueError(f"H01 contiene fundos/módulos sin mapear: {faltantes.to_dict('records')}")
    reales = reales.groupby(["semana_objetivo", "fundo_operativo"], as_index=False).real_kg.sum()

    r09.columns = ["fundo", "version", "semana_objetivo", "r09_kg"]
    r09["fundo_operativo"] = r09.fundo.map(_fundo)
    r09["semana_emision"] = r09.version.astype(str).str.upper().str.removeprefix("S")
    r09 = r09[r09.semana_emision.str.isdigit()].copy()
    r09["semana_emision"] = r09.semana_emision.astype(int)
    r09 = r09.groupby(
        ["semana_emision", "semana_objetivo", "fundo_operativo"], as_index=False
    ).r09_kg.sum()
    return reales, r09


def _metricas(
    tabla: pd.DataFrame, columna: str, *, grano: tuple[str, ...]
) -> dict[str, float | int]:
    agregado = tabla.groupby(list(grano), as_index=False).agg(
        pred_kg=(columna, "sum"), real_kg=("real_kg", "sum")
    )
    error = agregado.pred_kg - agregado.real_kg
    denominador = float(agregado.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / denominador),
        "sesgo": float(error.sum() / denominador),
        "mae_kg": float(error.abs().mean()),
        "n": int(len(agregado)),
    }


def _cobertura(
    tabla: pd.DataFrame,
    columna_disponible: str,
    *,
    grano: tuple[str, ...],
) -> dict[str, float | int]:
    agregado = tabla.groupby(list(grano), as_index=False).agg(
        real_kg=("real_kg", "sum"),
        disponible=(columna_disponible, "max"),
    )
    denominador = float(agregado.real_kg.abs().sum())
    volumen = float(agregado.loc[agregado.disponible, "real_kg"].abs().sum())
    return {
        "filas_disponibles": int(agregado.disponible.sum()),
        "filas_totales": int(len(agregado)),
        "cobertura_filas": float(agregado.disponible.mean()) if len(agregado) else 0.0,
        "cobertura_volumen": float(volumen / denominador) if denominador else 0.0,
    }


def _hash_keyset(tabla: pd.DataFrame) -> str:
    columnas = [
        "campania",
        "fecha_emision",
        "fecha_objetivo",
        "semana_emision",
        "semana_objetivo",
        "fundo_operativo",
    ]
    llaves = tabla[columnas].copy().sort_values(columnas, kind="stable")
    serializado = llaves.astype(str).agg("|".join, axis=1).str.cat(sep="\n")
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def ejecutar(
    *,
    root: Path = ROOT_DEFAULT,
    transitions: Path = TRANSITIONS_DEFAULT,
    access: Path = ACCESS_DEFAULT,
    campania: str = "C2026",
    emisiones_delta: tuple[int, ...] = (28, 29, 32),
    emisiones_holdout: tuple[int, ...] = (33,),
) -> dict[str, object]:
    macro = _leer_macro_h1(campania)
    reales, r09 = _leer_reales_r09_fundo(access, campania)
    # Macro congelada define el contrato. La ausencia de una fila real para un
    # fundo-semana significa cosecha cero; no autoriza a eliminar esa llave.
    macro = macro.merge(
        reales, on=["semana_objetivo", "fundo_operativo"], how="left", validate="many_to_one"
    )
    macro["real_disponible"] = macro.real_kg.notna()
    macro["real_kg"] = macro.real_kg.fillna(0.0)
    macro = macro.merge(
        r09,
        on=["semana_emision", "semana_objetivo", "fundo_operativo"],
        how="left",
        validate="one_to_one",
    )
    # La falta de R09 es falta de cobertura operativa, no permiso para reducir
    # el denominador. Se evalúa como cero y se reporta por separado.
    macro["r09_disponible"] = macro.r09_kg.notna()
    macro["r09_kg"] = macro.r09_kg.where(macro.r09_disponible, 0.0)
    macro["macro_disponible"] = True
    macro["candidate_disponible"] = True
    macro = macro[
        macro.fecha_objetivo.add(pd.Timedelta(days=6)).le(pd.Timestamp("2026-08-16"))
    ].copy()
    macro["candidate_kg"] = macro.macro_kg
    macro["ruta"] = "macro_fallback"

    transiciones = pd.read_parquet(transitions)
    transiciones = transiciones.loc[transiciones.fila_asof_utilizable.fillna(False)].copy()
    cache: dict[int, dict[str, tuple[pd.DataFrame, pd.DataFrame]]] = {}
    reemplazos: list[dict[str, object]] = []
    for emision in emisiones_delta:
        entrenamiento = transiciones.loc[transiciones.semana_emision_actual.lt(emision)].copy()
        if entrenamiento.semana_emision_actual.nunique() < 3:
            continue
        modelo = CandidateParamDelta(regularizacion=8.0, cuantiles=(0.15, 0.85)).fit(entrenamiento)
        por_fundo, _ = proyectar_emision_detallada(
            root,
            modelo,
            semana_emision=emision,
            campania=campania,
            bloque="parametros",
            cache_libros=cache,
        )
        objetivo = emision + 1
        for fundo, kg in por_fundo.items():
            mascara = (
                macro.semana_emision.eq(emision)
                & macro.semana_objetivo.eq(objetivo)
                & macro.fundo_operativo.eq(fundo)
            )
            if int(mascara.sum()) != 1:
                continue
            macro.loc[mascara, "candidate_kg"] = kg
            macro.loc[mascara, "ruta"] = "param_delta_asof"
            reemplazos.append(
                {"semana_emision": emision, "semana_objetivo": objetivo, "fundo": fundo, "kg": kg}
            )

    holdout: list[dict[str, object]] = []
    for emision in emisiones_holdout:
        entrenamiento = transiciones.loc[transiciones.semana_emision_actual.lt(emision)].copy()
        if entrenamiento.semana_emision_actual.nunique() < 3:
            continue
        modelo = CandidateParamDelta(regularizacion=8.0, cuantiles=(0.15, 0.85)).fit(entrenamiento)
        por_fundo, _ = proyectar_emision_detallada(
            root,
            modelo,
            semana_emision=emision,
            campania=campania,
            bloque="parametros",
            cache_libros=cache,
        )
        objetivo = emision + 1
        for fundo, kg in por_fundo.items():
            real = reales.loc[
                reales.semana_objetivo.eq(objetivo) & reales.fundo_operativo.eq(fundo),
                "real_kg",
            ]
            ref = r09.loc[
                r09.semana_emision.eq(emision)
                & r09.semana_objetivo.eq(objetivo)
                & r09.fundo_operativo.eq(fundo),
                "r09_kg",
            ]
            holdout.append(
                {
                    "semana_emision": emision,
                    "semana_objetivo": objetivo,
                    "fundo": fundo,
                    "candidate_kg": kg,
                    "real_kg": float(real.iloc[0]) if len(real) else np.nan,
                    "r09_kg": float(ref.iloc[0]) if len(ref) else np.nan,
                    "cierre": "candidato_no_certificado",
                }
            )

    comun = macro.copy()
    if comun.duplicated(["campania", "fecha_emision", "fecha_objetivo", "fundo_operativo"]).any():
        raise ValueError("El contrato contiene llaves campaña-emisión-objetivo-fundo duplicadas")
    esperados = comun.semana_objetivo.nunique() * 4
    if len(comun) != esperados or comun.fundo_operativo.nunique() != 4:
        raise ValueError(
            f"Contrato incompleto: {len(comun)} filas; se esperaban {esperados} para cuatro fundos"
        )
    por_fundo = {}
    for fundo, bloque in comun.groupby("fundo_operativo"):
        por_fundo[str(fundo)] = {
            "candidato": _metricas(
                bloque, "candidate_kg", grano=("semana_objetivo", "fundo_operativo")
            ),
            "macro": _metricas(bloque, "macro_kg", grano=("semana_objetivo", "fundo_operativo")),
            "r09": _metricas(bloque, "r09_kg", grano=("semana_objetivo", "fundo_operativo")),
        }
    return {
        "schema": "screening-param-delta-momentum-v1",
        "regla": "Macro; desde tres transiciones canónicas usa deltas X/O/N/A/B as-of",
        "campania": campania,
        "evaluation_contract": {
            "keyset_sha256": _hash_keyset(comun),
            "filas_fundo_semana": int(len(comun)),
            "semanas": int(comun.semana_objetivo.nunique()),
            "semana_min": int(comun.semana_objetivo.min()),
            "semana_max": int(comun.semana_objetivo.max()),
            "real_kg_denominador": float(comun.real_kg.sum()),
            "cierre_hasta": "2026-08-16",
        },
        "cobertura": {
            "candidato": _cobertura(
                comun, "candidate_disponible", grano=("semana_objetivo", "fundo_operativo")
            ),
            "macro": _cobertura(
                comun, "macro_disponible", grano=("semana_objetivo", "fundo_operativo")
            ),
            "r09": _cobertura(
                comun, "r09_disponible", grano=("semana_objetivo", "fundo_operativo")
            ),
        },
        "resumen_empresa_semana": {
            "candidato": _metricas(comun, "candidate_kg", grano=("semana_objetivo",)),
            "macro": _metricas(comun, "macro_kg", grano=("semana_objetivo",)),
            "r09": _metricas(comun, "r09_kg", grano=("semana_objetivo",)),
        },
        "resumen_fundo_semana": {
            "candidato": _metricas(
                comun, "candidate_kg", grano=("semana_objetivo", "fundo_operativo")
            ),
            "macro": _metricas(comun, "macro_kg", grano=("semana_objetivo", "fundo_operativo")),
            "r09": _metricas(comun, "r09_kg", grano=("semana_objetivo", "fundo_operativo")),
        },
        "por_fundo": por_fundo,
        "reemplazos": reemplazos,
        "holdout": holdout,
        "detalle": comun.to_dict("records"),
        "publicable": False,
    }


# Contrato público entre scripts; los aliases mantienen compatibilidad con los
# nombres privados usados por versiones anteriores.
normalizar_fundo = _fundo
leer_macro_h1 = _leer_macro_h1
columna_campania = _columna_campania
leer_reales_r09_fundo = _leer_reales_r09_fundo

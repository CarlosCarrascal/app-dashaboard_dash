"""Lectura, normalización y preparación de fuentes del screening."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd
import psycopg

from analitica.settings import postgres_dsn

from .fenologia_honest_contratos import (
    CAMPANIA,
    CIERRE_CERTIFICADO,
    FUNDOS,
    HORIZONTES,
    MAPEO_FUNDO,
    RUN_ID,
    SEMANA_DESARROLLO_FINAL,
    SEMANA_INICIAL,
    SEMANAS_HOLDOUT,
    SQL_CLIMA,
    SQL_ESTADOS,
    SQL_FLORES,
    SQL_MACRO,
    TBASES,
    VENTANAS,
)


def _normalizar_fundo(valor: object) -> str:
    texto = str(valor or "").strip()
    return MAPEO_FUNDO.get(texto.casefold(), texto)


def _leer_dataframe(cursor, consulta: str, parametros: Iterable[Any] = ()) -> pd.DataFrame:
    cursor.execute(consulta, tuple(parametros))
    columnas = [descripcion.name for descripcion in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=columnas)


def leer_fuentes(
    *, run_id: int = RUN_ID, campania: str = CAMPANIA
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Lee únicamente Macro, clima y censos dentro de una transacción read-only."""

    with psycopg.connect(postgres_dsn(), connect_timeout=8) as conexion:
        conexion.execute("SET TRANSACTION READ ONLY")
        with conexion.cursor() as cursor:
            macro = _leer_dataframe(cursor, SQL_MACRO, (run_id, campania))
            clima = _leer_dataframe(cursor, SQL_CLIMA)
            estados = _leer_dataframe(cursor, SQL_ESTADOS)
            flores = _leer_dataframe(cursor, SQL_FLORES)
    return macro, clima, estados, flores


def preparar_macro(
    macro: pd.DataFrame,
    *,
    campania: str = CAMPANIA,
    limitar_c2026: bool = True,
) -> pd.DataFrame:
    """Congela curvas h1-h6 completas y el mismo real para todos sus vintages."""

    requeridas = {
        "campania",
        "fecha_emision",
        "fecha_objetivo",
        "horizonte_semanas",
        "lote_id",
        "fundo",
        "modulo",
        "p50_kg",
        "real_kg",
    }
    faltantes = sorted(requeridas.difference(macro.columns))
    if faltantes:
        raise ValueError(f"Macro no cumple el contrato: {faltantes}")
    if macro.empty:
        raise ValueError(f"No existe MacroLegacy h1-h6 para {campania}")

    tabla = macro.copy()
    tabla["fecha_emision"] = pd.to_datetime(tabla.fecha_emision, errors="raise").dt.normalize()
    tabla["fecha_objetivo"] = pd.to_datetime(tabla.fecha_objetivo, errors="raise").dt.normalize()
    tabla["horizonte_semanas"] = pd.to_numeric(tabla.horizonte_semanas, errors="raise").astype(int)
    tabla["p50_kg"] = pd.to_numeric(tabla.p50_kg, errors="raise")
    tabla["real_kg"] = pd.to_numeric(tabla.real_kg, errors="coerce")
    tabla = tabla[tabla.horizonte_semanas.isin(HORIZONTES)].copy()
    if tabla.p50_kg.lt(0).any():
        raise ValueError("Macro contiene kilos negativos")
    clave = ["campania", "fecha_emision", "fecha_objetivo", "lote_id"]
    if tabla.duplicated(clave).any():
        raise ValueError("Macro repite una clave emisión-objetivo-lote")

    grupos = ["campania", "fecha_emision", "lote_id"]
    horizontes = tabla.groupby(grupos).horizonte_semanas.apply(
        lambda serie: tuple(sorted(int(v) for v in serie.unique()))
    )
    incompletas = horizontes[horizontes.map(lambda valores: valores != HORIZONTES)]
    if len(incompletas):
        raise ValueError(
            "Macro no conserva h1-h6 contiguos; "
            f"primer grupo={incompletas.index[0]}, horizontes={incompletas.iloc[0]}"
        )

    tabla["fundo_operativo"] = tabla.fundo.map(_normalizar_fundo)
    if set(tabla.fundo_operativo.unique()) != set(FUNDOS):
        raise ValueError("El contrato no contiene exactamente los cuatro fundos")
    tabla["semana_objetivo"] = tabla.fecha_objetivo.dt.isocalendar().week.astype(int)
    tabla["semana_fin"] = tabla.fecha_objetivo + pd.Timedelta(days=6)
    tabla["split"] = "fuera_evaluacion"
    if limitar_c2026:
        desarrollo = tabla.semana_objetivo.between(
            SEMANA_INICIAL, SEMANA_DESARROLLO_FINAL
        ) & tabla.semana_fin.le(CIERRE_CERTIFICADO)
        holdout = tabla.semana_objetivo.isin(SEMANAS_HOLDOUT) & tabla.semana_fin.le(
            CIERRE_CERTIFICADO
        )
        tabla.loc[desarrollo & tabla.semana_objetivo.le(24), "split"] = "desarrollo_temprano"
        tabla.loc[desarrollo & tabla.semana_objetivo.gt(24), "split"] = "desarrollo_tardio"
        tabla.loc[holdout, "split"] = "holdout_s31_s33"
        evaluable = desarrollo | holdout
        if tabla.loc[evaluable, "real_kg"].isna().any():
            raise ValueError("El contrato cerrado contiene reales nulos")
    else:
        tabla.loc[tabla.real_kg.notna(), "split"] = "externa"

    dimension = tabla[["lote_id", "fundo_operativo", "modulo"]].drop_duplicates()
    if dimension.groupby("lote_id").fundo_operativo.nunique().gt(1).any():
        raise ValueError("Un lote cambia de fundo dentro de la corrida")
    return tabla.sort_values(
        ["fecha_emision", "fundo_operativo", "lote_id", "horizonte_semanas"],
        kind="stable",
    ).reset_index(drop=True)


def preparar_clima(clima: pd.DataFrame) -> pd.DataFrame:
    """Reduce el clima a días cerrados y deriva DPV/GDD sin usar el futuro."""

    requeridas = {"fecha_hora", "temp", "temp_alta", "temp_baja", "humedad", "et_mm"}
    faltantes = sorted(requeridas.difference(clima.columns))
    if faltantes:
        raise ValueError(f"Clima no cumple el contrato: {faltantes}")
    tabla = clima.copy()
    tabla["fecha"] = pd.to_datetime(tabla.fecha_hora, errors="raise").dt.normalize()
    for columna in ("temp", "temp_alta", "temp_baja", "humedad", "et_mm"):
        tabla[columna] = pd.to_numeric(tabla[columna], errors="coerce")
    diario = tabla.groupby("fecha", as_index=False).agg(
        temp_observada=("temp", "mean"),
        temp_max=("temp_alta", "max"),
        temp_min=("temp_baja", "min"),
        humedad=("humedad", "mean"),
        eto=("et_mm", "sum"),
    )
    termica = (diario.temp_max + diario.temp_min) / 2.0
    diario["temp_media"] = termica.where(termica.notna(), diario.temp_observada)
    presion = 0.6108 * np.exp(17.27 * diario.temp_media / (diario.temp_media + 237.3))
    diario["dpv"] = presion * (1.0 - diario.humedad / 100.0).clip(lower=0.0)
    for base in TBASES:
        diario[f"gdd_{str(base).replace('.', '_')}"] = (diario.temp_media - base).clip(lower=0.0)
    return diario.sort_values("fecha", kind="stable").reset_index(drop=True)


def construir_clima_asof(emisiones: Iterable[pd.Timestamp], diario: pd.DataFrame) -> pd.DataFrame:
    """Resume ventanas [emisión-ventana, emisión), excluyendo el día de emisión."""

    filas: list[dict[str, Any]] = []
    for emision in sorted(pd.to_datetime(pd.Series(list(emisiones))).dt.normalize().unique()):
        fecha_emision = pd.Timestamp(emision)
        fila: dict[str, Any] = {"fecha_emision": fecha_emision}
        for ventana in VENTANAS:
            inicio = fecha_emision - pd.Timedelta(days=ventana)
            bloque = diario[diario.fecha.ge(inicio) & diario.fecha.lt(fecha_emision)]
            dias = int(bloque.fecha.nunique())
            fila[f"clima_cobertura_{ventana}d"] = dias / float(ventana)
            fila[f"temp_{ventana}d"] = float(bloque.temp_media.mean()) if dias else np.nan
            fila[f"dpv_{ventana}d"] = float(bloque.dpv.mean()) if dias else np.nan
            fila[f"eto_{ventana}d"] = float(bloque.eto.sum()) if dias else np.nan
            for base in TBASES:
                etiqueta = str(base).replace(".", "_")
                columna = f"gdd_{etiqueta}"
                fila[f"{columna}_{ventana}d"] = float(bloque[columna].sum()) if dias else np.nan
        filas.append(fila)
    return pd.DataFrame(filas)


def _preparar_estados(estados: pd.DataFrame) -> pd.DataFrame:
    tabla = estados.copy()
    tabla["fecha"] = pd.to_datetime(tabla.fecha, errors="raise").dt.normalize()
    for columna in ("e1", "e2", "e3", "e4", "e5"):
        tabla[columna] = pd.to_numeric(tabla[columna], errors="coerce").fillna(0.0)
    tabla = tabla.groupby(["lote_id", "fecha"], as_index=False)[
        ["e1", "e2", "e3", "e4", "e5"]
    ].sum()
    total = tabla[["e1", "e2", "e3", "e4", "e5"]].sum(axis=1).replace(0, np.nan)
    tabla["indice_estado"] = sum(numero * tabla[f"e{numero}"] for numero in range(1, 6)) / total
    tabla["prop_e45"] = (tabla.e4 + tabla.e5) / total
    return tabla[["lote_id", "fecha", "indice_estado", "prop_e45"]]


def _preparar_flores(flores: pd.DataFrame) -> pd.DataFrame:
    tabla = flores.copy()
    tabla["fecha"] = pd.to_datetime(tabla.fecha, errors="raise").dt.normalize()
    tabla["n_flores"] = pd.to_numeric(tabla.n_flores, errors="coerce").fillna(0.0)
    tabla["cuajo"] = pd.to_numeric(tabla.cuajo, errors="coerce").fillna(0.0)
    tabla = tabla.groupby(["lote_id", "fecha"], as_index=False).agg(
        flores=("n_flores", "sum"),
        cuajo=("cuajo", "sum"),
        plantas=("planta", "nunique"),
    )
    tabla["flores_por_planta"] = tabla.flores / tabla.plantas.replace(0, np.nan)
    tabla["tasa_cuajo"] = tabla.cuajo / tabla.flores.replace(0, np.nan)
    return tabla[["lote_id", "fecha", "flores_por_planta", "tasa_cuajo"]]


def construir_fenologia_asof(
    emisiones: Iterable[pd.Timestamp],
    dimension_lotes: pd.DataFrame,
    estados: pd.DataFrame,
    flores: pd.DataFrame,
    *,
    frescura_max_dias: int = 42,
) -> pd.DataFrame:
    """Último censo anterior a cada emisión, agregado por fundo y con cobertura."""

    estados_lote = _preparar_estados(estados)
    flores_lote = _preparar_flores(flores)
    dimension = dimension_lotes[["lote_id", "fundo_operativo"]].drop_duplicates()
    totales = dimension.groupby("fundo_operativo").lote_id.nunique().to_dict()
    filas: list[dict[str, Any]] = []
    for emision in sorted(pd.to_datetime(pd.Series(list(emisiones))).dt.normalize().unique()):
        fecha_emision = pd.Timestamp(emision)
        anteriores_estado = estados_lote[estados_lote.fecha.lt(fecha_emision)]
        anteriores_estado = anteriores_estado.sort_values("fecha").drop_duplicates(
            "lote_id", keep="last"
        )
        anteriores_flores = flores_lote[flores_lote.fecha.lt(fecha_emision)]
        anteriores_flores = anteriores_flores.sort_values("fecha").drop_duplicates(
            "lote_id", keep="last"
        )
        for fuente in (anteriores_estado, anteriores_flores):
            fuente["edad_dias"] = (fecha_emision - fuente.fecha).dt.days
        anteriores_estado = anteriores_estado[anteriores_estado.edad_dias.le(frescura_max_dias)]
        anteriores_flores = anteriores_flores[anteriores_flores.edad_dias.le(frescura_max_dias)]
        for fundo in FUNDOS:
            lotes = dimension.loc[dimension.fundo_operativo.eq(fundo), "lote_id"]
            e = anteriores_estado[anteriores_estado.lote_id.isin(lotes)]
            f = anteriores_flores[anteriores_flores.lote_id.isin(lotes)]
            total_lotes = max(int(totales.get(fundo, 0)), 1)
            filas.append(
                {
                    "fecha_emision": fecha_emision,
                    "fundo_operativo": fundo,
                    "indice_estado": float(e.indice_estado.median()) if len(e) else np.nan,
                    "prop_e45": float(e.prop_e45.median()) if len(e) else np.nan,
                    "flores_por_planta": (
                        float(f.flores_por_planta.median()) if len(f) else np.nan
                    ),
                    "tasa_cuajo": float(f.tasa_cuajo.median()) if len(f) else np.nan,
                    "cobertura_estados": e.lote_id.nunique() / total_lotes,
                    "cobertura_flores": f.lote_id.nunique() / total_lotes,
                    "edad_estados_mediana": (float(e.edad_dias.median()) if len(e) else np.nan),
                    "edad_flores_mediana": (float(f.edad_dias.median()) if len(f) else np.nan),
                }
            )
    return pd.DataFrame(filas)


def agregar_curvas_fundo(macro: pd.DataFrame) -> pd.DataFrame:
    dimensiones = [
        "campania",
        "fecha_emision",
        "fecha_objetivo",
        "horizonte_semanas",
        "semana_objetivo",
        "split",
        "fundo_operativo",
    ]
    return (
        macro.groupby(dimensiones, as_index=False, dropna=False)
        .agg(macro_kg=("p50_kg", "sum"), real_kg=("real_kg", "sum"))
        .sort_values(["fecha_emision", "fundo_operativo", "horizonte_semanas"])
        .reset_index(drop=True)
    )

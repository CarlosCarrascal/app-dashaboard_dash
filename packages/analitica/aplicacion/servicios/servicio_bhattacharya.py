"""Servicio de orquestación para el modelo de Bhattacharya (Base de datos y Excel).

Permite:
1. Calibrar todos los lotes de la campaña vigente leyendo directamente de PostgreSQL o Excel.
2. Generar la matriz semanal completa para packing y operaciones.
3. Exportar a Excel limpio o persistir en PostgreSQL (analytics.prediction).
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from .infraestructura.postgres import obtener_conexion_pg

if TYPE_CHECKING:
    from ...dominio.nucleo.bhattacharya import (
        ParametrosBhattacharya,
        ajustar_lote_automatico,
        proyectar_curva_oleadas,
    )

_SIMBOLOS_BHATTACHARYA = {
    "ParametrosBhattacharya",
    "ajustar_lote_automatico",
    "proyectar_curva_oleadas",
}


def __getattr__(nombre: str):
    """Resuelve el modelo pesado solo cuando el servicio lo utiliza."""

    if nombre in _SIMBOLOS_BHATTACHARYA:
        modulo = importlib.import_module("...dominio.nucleo.bhattacharya", __package__)
        return getattr(modulo, nombre)
    raise AttributeError(nombre)


def _obtener_conexion_pg():
    """Fachada histórica hacia el adaptador PostgreSQL."""
    return obtener_conexion_pg()


def cargar_datos_desde_db(
    campania: str = "C2026",
    fecha_corte: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Extrae cosecha por lote físico y la expresa en frutos por planta.

    ``fecha_corte`` implementa la semántica as-of: una calibración histórica no puede
    ver cosecha posterior a la emisión. No existe fallback silencioso a otra campaña.
    """
    query_cosecha = """
    WITH poda_campania AS (
        SELECT DISTINCT ON (p.lote_id, p.campania_id)
            p.lote_id,
            p.campania_id,
            p.fecha_inicio,
            p.area_ha
        FROM core.poda p
        ORDER BY p.lote_id, p.campania_id, p.fecha_inicio DESC
    )
    SELECT
        l.lote_id::text AS lote_id,
        l.codigo AS lote,
        f.codigo AS fundo,
        m.codigo AS modulo,
        t.codigo AS turno,
        c.codigo AS campania,
        co.fecha AS fecha_cosecha,
        p.fecha_inicio AS fecha_poda,
        (co.fecha - p.fecha_inicio) AS t_dias,
        co.pana,
        co.kg,
        co.peso_baya,
        COALESCE(NULLIF(co.n_plantas, 0), NULLIF(l.n_plantas, 0)) AS n_plantas,
        p.area_ha,
        (
            co.kg * 1000.0
            / NULLIF(co.peso_baya, 0)
            / NULLIF(COALESCE(NULLIF(co.n_plantas, 0), NULLIF(l.n_plantas, 0)), 0)
        ) AS frutos_obs
    FROM core.cosecha co
    JOIN core.campania c ON co.campania_id = c.campania_id
    JOIN core.lote l ON co.lote_id = l.lote_id
    LEFT JOIN core.modulo m ON l.modulo_id = m.modulo_id
    LEFT JOIN core.fundo f ON m.fundo_id = f.fundo_id
    LEFT JOIN core.turno t ON l.turno_id = t.turno_id
    LEFT JOIN poda_campania p
      ON p.lote_id = co.lote_id AND p.campania_id = co.campania_id
    WHERE c.codigo = %s
      AND p.fecha_inicio IS NOT NULL
      AND co.kg > 0
      AND (%s::date IS NULL OR co.fecha <= %s::date)
    ORDER BY l.lote_id, co.fecha, co.pana;
    """

    with _obtener_conexion_pg() as conn, conn.cursor() as cur:
        corte = None if fecha_corte is None else pd.Timestamp(fecha_corte).date()
        cur.execute(query_cosecha, (campania, corte, corte))
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        df_cosecha = pd.DataFrame(rows, columns=cols)
    return df_cosecha


def cargar_lotes_objetivo_desde_db(campania: str = "C2026") -> pd.DataFrame:
    """Devuelve identidad, poda, área y plantas del universo físico de la campaña."""
    query = """
    WITH poda_campania AS (
        SELECT DISTINCT ON (p.lote_id, p.campania_id)
            p.lote_id,
            p.campania_id,
            p.fecha_inicio,
            p.area_ha
        FROM core.poda p
        ORDER BY p.lote_id, p.campania_id, p.fecha_inicio DESC
    )
    SELECT
        l.lote_id::text AS lote_id,
        l.codigo AS lote,
        f.codigo AS fundo,
        m.codigo AS modulo,
        t.codigo AS turno,
        c.codigo AS campania,
        p.fecha_inicio AS fecha_poda,
        p.area_ha,
        l.n_plantas
    FROM core.campania c
    JOIN poda_campania p ON p.campania_id = c.campania_id
    JOIN core.lote l ON l.lote_id = p.lote_id
    JOIN core.modulo m ON m.modulo_id = l.modulo_id
    JOIN core.fundo f ON f.fundo_id = m.fundo_id
    LEFT JOIN core.turno t ON t.turno_id = l.turno_id
    WHERE c.codigo = %s
      AND NOT COALESCE(l.es_sentinel, false)
      AND NOT COALESCE(m.es_sentinel, false)
      AND NOT COALESCE(f.es_sentinel, false)
    ORDER BY f.codigo, m.codigo, l.codigo;
    """
    with _obtener_conexion_pg() as conn, conn.cursor() as cur:
        cur.execute(query, (campania,))
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
    return pd.DataFrame(rows, columns=cols)


def cargar_datos_desde_excel(ruta_excel: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lee las pañas, lotes y carga frutal directamente del archivo Excel."""
    xl = pd.ExcelFile(ruta_excel, engine="openpyxl")
    df_params = xl.parse("Parametros")
    df_totalpob = xl.parse("TotalPob")

    df_params.columns = [str(c).strip() for c in df_params.columns]
    df_totalpob.columns = [str(c).strip() for c in df_totalpob.columns]

    return df_params, df_totalpob


def _calibrar_grupo_db(
    clave_lote: object,
    df_g: pd.DataFrame,
    campania: str,
    prior: ParametrosBhattacharya | None,
) -> tuple[str, ParametrosBhattacharya]:
    """Worker puro y serializable para calibración paralela por proceso."""
    from ...dominio.nucleo.bhattacharya import ajustar_lote_automatico

    lote = str(df_g["lote"].iloc[0])
    parametro = ajustar_lote_automatico(
        t_dias=pd.to_numeric(df_g["t_dias"]).values,
        frutos_obs=pd.to_numeric(df_g["frutos_obs"]).values,
        peso_obs=pd.to_numeric(df_g["peso_baya"]).values,
        prior=prior,
        lote_id=str(clave_lote) if "lote_id" in df_g.columns else "",
        lote=lote,
        campania=campania,
        fundo=str(
            df_g["fundo"].iloc[0]
            if "fundo" in df_g.columns and pd.notna(df_g["fundo"].iloc[0])
            else "Aqu Anqa"
        ),
        modulo=str(
            df_g["modulo"].iloc[0]
            if "modulo" in df_g.columns and pd.notna(df_g["modulo"].iloc[0])
            else ""
        ),
        turno=str(
            df_g["turno"].iloc[0]
            if "turno" in df_g.columns and pd.notna(df_g["turno"].iloc[0])
            else ""
        ),
        fecha_poda=(
            pd.to_datetime(df_g["fecha_poda"].iloc[0])
            if pd.notna(df_g["fecha_poda"].iloc[0])
            else None
        ),
        n_plantas=(
            int(df_g["n_plantas"].iloc[0])
            if "n_plantas" in df_g.columns and pd.notna(df_g["n_plantas"].iloc[0])
            else 5000
        ),
    )
    return str(clave_lote), parametro


def calibrar_todos_los_lotes(
    df_cosecha: pd.DataFrame | None = None,
    ruta_excel: str | Path | None = None,
    campania: str = "C2026",
    fecha_corte: str | pd.Timestamp | None = None,
    priors_por_lote: dict[str, ParametrosBhattacharya] | None = None,
    paralelo: bool = True,
) -> tuple[dict[str, ParametrosBhattacharya], pd.DataFrame]:
    """Calibra Bhattacharya para todos los lotes y genera la matriz de parámetros.

    Devuelve:
    - Diccionario {lote_codigo: ParametrosBhattacharya}
    - DataFrame consolidado de parámetros
    """
    from ...dominio.nucleo.bhattacharya import ParametrosBhattacharya

    params_por_lote: dict[str, ParametrosBhattacharya] = {}

    if ruta_excel is not None and Path(ruta_excel).exists():
        df_params_ex, df_tp = cargar_datos_desde_excel(ruta_excel)
        for _, row in df_params_ex.iterrows():
            lote = str(row.get("Lote", "")).strip()
            if not lote or lote.lower() == "nan":
                continue

            n1 = float(row.get("N1", 500.0)) if pd.notna(row.get("N1")) else 500.0
            n2 = float(row.get("N2", 300.0)) if pd.notna(row.get("N2")) else 300.0
            n3 = float(row.get("N3", 100.0)) if pd.notna(row.get("N3")) else 100.0

            # Pañas simuladas/extraídas
            mu1_ex = float(row.get("X1", 220.0)) if pd.notna(row.get("X1")) else 220.0
            sig1_ex = float(row.get("O1", 25.0)) if pd.notna(row.get("O1")) else 25.0

            p = ParametrosBhattacharya(
                lote=lote,
                campania=campania,
                fundo=str(row.get("Fundo", "Aqu Anqa")),
                modulo=str(row.get("Modulo", "")),
                turno=str(row.get("Turno", "")),
                fecha_poda=pd.to_datetime(row.get("FechaPoda", "2025-12-29")),
                mu1=round(mu1_ex, 2),
                sigma1=round(sig1_ex, 2),
                N1=round(n1, 1),
                mu2=round(mu1_ex + 70.0, 2),
                sigma2=round(sig1_ex * 1.15, 2),
                N2=round(n2, 1),
                mu3=round(mu1_ex + 133.0, 2),
                sigma3=round(sig1_ex * 1.20, 2),
                N3=round(n3, 1),
                peso_a=4.28,
                peso_b=-0.0021,
                rmse_total=0.88,
            )
            clave = "|".join(
                [str(p.fundo).strip(), str(p.modulo).strip(), str(p.turno).strip(), lote]
            )
            params_por_lote[clave] = p
    else:
        if df_cosecha is None:
            df_cosecha = cargar_datos_desde_db(campania, fecha_corte=fecha_corte)

        if df_cosecha.empty:
            return {}, pd.DataFrame()

        columna_grupo = "lote_id" if "lote_id" in df_cosecha.columns else "lote"

        grupos = list(df_cosecha.groupby(columna_grupo, sort=False))

        if paralelo and len(grupos) > 20:
            from joblib import Parallel, delayed

            trabajadores = min(8, max(2, (os.cpu_count() or 2) - 1))
            calibrados = Parallel(
                n_jobs=trabajadores,
                backend="loky",
                batch_size="auto",
            )(
                delayed(_calibrar_grupo_db)(
                    clave_lote,
                    df_g,
                    campania,
                    (priors_por_lote or {}).get(str(clave_lote)),
                )
                for clave_lote, df_g in grupos
            )
            params_por_lote.update(calibrados)
        else:
            params_por_lote.update(
                _calibrar_grupo_db(
                    clave_lote,
                    df_g,
                    campania,
                    (priors_por_lote or {}).get(str(clave_lote)),
                )
                for clave_lote, df_g in grupos
            )

    # Construir DataFrame consolidado
    df_params_res = pd.DataFrame([p.to_dict() for p in params_por_lote.values()])
    return params_por_lote, df_params_res


def generar_proyeccion_empresa(
    params_por_lote: dict[str, ParametrosBhattacharya],
    t_start: int = 150,
    t_end: int = 420,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Genera la proyección semanal agregada por lote y consolidada para la empresa."""
    from ...dominio.nucleo.bhattacharya import proyectar_curva_oleadas

    if not params_por_lote:
        columnas_matriz = ["Fundo", "Lote", "Modulo", "Turno"]
        return pd.DataFrame(), pd.DataFrame(columns=columnas_matriz)

    lista_lotes = []

    for p in params_por_lote.values():
        df_lote = proyectar_curva_oleadas(p, t_start=t_start, t_end=t_end, step_days=7)
        lista_lotes.append(df_lote)

    df_detalle_lotes = pd.concat(lista_lotes, ignore_index=True)

    # Matriz pivoteada Semanal (Lotes en filas, Semanas en columnas)
    df_matriz_kg = df_detalle_lotes.pivot_table(
        index=["Fundo", "Lote", "Modulo", "Turno"],
        columns="Semana",
        values="Kg_Semanal_Total",
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()

    return df_detalle_lotes, df_matriz_kg


def exportar_proyeccion_excel(
    df_params: pd.DataFrame,
    df_matriz_kg: pd.DataFrame,
    df_detalle: pd.DataFrame,
    ruta_salida: str | Path,
) -> Path:
    """Exporta el reporte consolidado a un archivo Excel limpio sin errores."""
    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(ruta_salida, engine="openpyxl") as writer:
        df_matriz_kg.to_excel(writer, sheet_name="Proyeccion_Semanal_Kg", index=False)
        df_params.to_excel(writer, sheet_name="Parametros_Bhattacharya", index=False)
        df_detalle.head(5000).to_excel(writer, sheet_name="Detalle_Curvas_Oleadas", index=False)

    return ruta_salida


__all__ = [
    "ParametrosBhattacharya",
    "ajustar_lote_automatico",
    "proyectar_curva_oleadas",
    "cargar_datos_desde_db",
    "cargar_lotes_objetivo_desde_db",
    "cargar_datos_desde_excel",
    "calibrar_todos_los_lotes",
    "generar_proyeccion_empresa",
    "exportar_proyeccion_excel",
]

"""Implementación única del screening asistido por Excel.

Para cada emisión semanal canónica ejecuta el motor Python con los parámetros y
el calendario que estaban en el Excel de esa emisión. La salida se compara con
la cosecha real posterior y con R09 de la misma versión. Este benchmark no es un
modelo automático: cuantifica cuánto de la ventaja operativa proviene de los
ajustes humanos ya contenidos en los libros.

La lectura de Access y de los libros Excel permanece diferida a las funciones
que la necesitan, de modo que importar el servicio no requiere ``pyodbc`` ni
``python-calamine``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from analitica.aplicacion.operativo import construir_modelo_operativo_excel
from analitica.aplicacion.procesos.candidatos import escribir_json_reproducible

ROOT_DEFAULT = Path(r"C:\Users\CCARRASCAL\Downloads\Proyecciones")
ACCESS_DEFAULT = Path(
    r"C:\Users\CCARRASCAL\Proyectos\aquanqa-data-platform\.cache"
    r"\analitica\source-snapshots\BD_AQUANQA_26_snapshot_2026-08-25.accdb"
)
SEMANAS_LIMPIAS = (24, 25, 26, 27, 28, 29, 31, 32, 33)


def _conexion_access(ruta: Path):
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError(
            "Este comando necesita pyodbc y el controlador ODBC de Microsoft Access."
        ) from exc
    if not ruta.is_file():
        raise FileNotFoundError(ruta)
    cadena = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + str(ruta)
    return pyodbc.connect(cadena)


def _columna_campania(cursor, tabla: str) -> str:
    columnas = [fila.column_name for fila in cursor.columns(table=tabla)]
    candidatas = [columna for columna in columnas if columna.casefold().startswith("campa")]
    if len(candidatas) != 1:
        raise ValueError(f"No se pudo identificar campaña en {tabla}: {columnas}")
    return candidatas[0]


def cargar_reales_y_r09(ruta: Path, campania: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    with _conexion_access(ruta) as conexion:
        cursor = conexion.cursor()
        columna_campania_h01 = _columna_campania(cursor, "H01_ProdHistorica")
        columna_campania_r09 = _columna_campania(cursor, "R09_Forecast_Semanal")
        consulta_real = (
            "SELECT [Semana], Sum([KG]) AS total_kg "
            "FROM [H01_ProdHistorica] "
            f"WHERE [{columna_campania_h01}] = ? "
            "GROUP BY [Semana] ORDER BY [Semana]"
        )
        consulta_r09 = (
            "SELECT [Version], [Sem], Sum([Kg]) AS total_kg "
            "FROM [R09_Forecast_Semanal] "
            f"WHERE [{columna_campania_r09}] = ? "
            "GROUP BY [Version], [Sem] ORDER BY [Version], [Sem]"
        )
        reales = pd.read_sql(consulta_real, conexion, params=[campania])
        r09 = pd.read_sql(consulta_r09, conexion, params=[campania])
    reales.columns = ["semana", "real_kg"]
    r09.columns = ["version", "semana", "r09_kg"]
    reales["semana"] = pd.to_numeric(reales.semana, errors="raise").astype(int)
    r09["semana"] = pd.to_numeric(r09.semana, errors="raise").astype(int)
    return reales, r09


def fecha_lunes_iso(anio: int, semana: int) -> pd.Timestamp:
    return pd.Timestamp.fromisocalendar(anio, semana, 1)


def ejecutar(
    root: Path = ROOT_DEFAULT,
    access: Path = ACCESS_DEFAULT,
    *,
    campania: str = "C2026",
    semanas: tuple[int, ...] = SEMANAS_LIMPIAS,
) -> dict[str, object]:
    reales, r09 = cargar_reales_y_r09(access, campania)
    filas: list[dict[str, object]] = []
    omitidas: list[dict[str, object]] = []
    anio = int(campania.removeprefix("C"))

    for semana_emision in semanas:
        carpeta = root / f"ProyeccionSemanal_{semana_emision}"
        if not carpeta.is_dir():
            omitidas.append({"semana_emision": semana_emision, "motivo": "carpeta_ausente"})
            continue
        emision = fecha_lunes_iso(anio, semana_emision)
        try:
            predicciones, _, detalles = construir_modelo_operativo_excel(
                carpeta,
                campania=campania,
                fecha_emision=emision,
                version_fuente=f"ProySemanal_{semana_emision}",
                fuente_parametros="excel",
            )
        except (FileNotFoundError, ValueError) as exc:
            omitidas.append({"semana_emision": semana_emision, "motivo": str(exc)})
            continue
        tabla = predicciones.copy()
        tabla["fecha_objetivo"] = pd.to_datetime(tabla.fecha_objetivo)
        tabla["semana"] = tabla.fecha_objetivo.dt.isocalendar().week.astype(int)
        objetivo = semana_emision + 1
        excel_kg = float(tabla.loc[tabla.semana.eq(objetivo), "p50_kg"].sum())
        real = reales.loc[reales.semana.eq(objetivo), "real_kg"]
        referencia = r09.loc[
            r09.version.astype(str).str.upper().eq(f"S{semana_emision:02d}")
            & r09.semana.eq(objetivo),
            "r09_kg",
        ]
        if real.empty:
            omitidas.append(
                {"semana_emision": semana_emision, "motivo": "semana_objetivo_sin_real_cerrado"}
            )
            continue
        filas.append(
            {
                "campania": campania,
                "semana_emision": semana_emision,
                "fecha_emision": emision.date().isoformat(),
                "semana_objetivo": objetivo,
                "real_kg": float(real.iloc[0]),
                "excel_asistido_kg": excel_kg,
                "r09_kg": float(referencia.iloc[0]) if not referencia.empty else np.nan,
                "n_libros": int(len(detalles["manifest"])),
                "hashes": [item["sha256"] for item in detalles["manifest"]],
            }
        )

    comparacion = pd.DataFrame(filas)
    metricas: dict[str, object] = {}
    if not comparacion.empty:
        denominador = float(comparacion.real_kg.abs().sum())
        for nombre, columna in (("ExcelAsistido", "excel_asistido_kg"), ("R09", "r09_kg")):
            valido = comparacion[columna].notna()
            parte = comparacion[valido]
            error = parte[columna] - parte.real_kg
            denom = float(parte.real_kg.abs().sum())
            metricas[nombre] = {
                "wape": float(error.abs().sum() / denom) if denom else np.nan,
                "sesgo": float(error.sum() / denom) if denom else np.nan,
                "mae_kg": float(error.abs().mean()) if len(error) else np.nan,
                "n_semanas": int(len(parte)),
                "volumen_real_kg": float(parte.real_kg.sum()),
            }
        comparacion["error_abs_excel"] = (comparacion.excel_asistido_kg - comparacion.real_kg).abs()
        comparacion["error_abs_r09"] = (comparacion.r09_kg - comparacion.real_kg).abs()
        metricas["ExcelAsistido"]["semanas_ganadas_r09"] = float(
            comparacion.error_abs_excel.lt(comparacion.error_abs_r09).mean()
        )
        metricas["universo"] = {
            "n_semanas": int(len(comparacion)),
            "volumen_real_kg": float(comparacion.real_kg.sum()),
            "denominador_wape": denominador,
        }
    return {
        "schema": "screening-excel-assisted-v1",
        "descripcion": "Techo asistido; no es un modelo automatico ni publicable.",
        "campania": campania,
        "access": str(access),
        "root": str(root),
        "semanas_solicitadas": list(semanas),
        "comparacion": comparacion.to_dict("records"),
        "metricas": metricas,
        "omitidas": omitidas,
        "publicable": False,
    }


__all__ = [
    "ACCESS_DEFAULT",
    "ROOT_DEFAULT",
    "SEMANAS_LIMPIAS",
    "cargar_reales_y_r09",
    "construir_modelo_operativo_excel",
    "ejecutar",
    "escribir_json_reproducible",
    "fecha_lunes_iso",
    "np",
    "pd",
]

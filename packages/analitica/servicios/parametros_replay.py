"""Servicios compartidos para replay y screening de parámetros.

Las funciones de este módulo son la única implementación de las utilidades
comunes a los scripts de parámetros. Se mantienen deliberadamente sin
dependencias hacia ``analitica.scripts`` para que los lanzadores puedan
evolucionar de forma independiente.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from analitica.proyeccion.motor_proyeccion_semanal import ejecutar_proyeccion_semanal_dataframe
from analitica.proyeccion.operativo import leer_libro_operativo
from analitica.proyeccion.parametros import CandidateParamDelta
from analitica.proyeccion.parametros_excel import seleccionar_libros_parametros

ROOT_DEFAULT = Path(r"C:\Users\CCARRASCAL\Downloads\Proyecciones")
TRANSITIONS_DEFAULT = (
    Path(__file__).resolve().parents[1] / ".tmp" / "excel_parameter_transitions_s24_s35.parquet"
)
ACCESS_DEFAULT = (
    Path(r"C:\Users\CCARRASCAL\Proyectos\aquanqa-data-platform\.cache")
    / "analitica"
    / "source-snapshots"
    / "BD_AQUANQA_26_snapshot_2026-08-25.accdb"
)

PARAMETROS_CURVA = (
    "X1",
    "O1",
    "N1",
    "X2",
    "O2",
    "N2",
    "X3",
    "O3",
    "N3",
    "A1",
    "B1",
    "A2",
    "B2",
    "A3",
    "B3",
)
PARAMETROS_CALENDARIO = ("%Caida", "Finicio")


def conexion_access(ruta: Path):
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError(
            "Este comando necesita pyodbc y el controlador ODBC de Microsoft Access."
        ) from exc
    cadena = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + str(ruta)
    return pyodbc.connect(cadena)


def columna_campania(cursor, tabla: str) -> str:
    columnas = [fila.column_name for fila in cursor.columns(table=tabla)]
    candidatas = [columna for columna in columnas if columna.casefold().startswith("campa")]
    if len(candidatas) != 1:
        raise ValueError(f"No se pudo identificar campaña en {tabla}: {columnas}")
    return candidatas[0]


def cargar_reales_y_r09(
    ruta: Path, campania: str
) -> tuple[dict[int, float], dict[tuple[int, int], float]]:
    with conexion_access(ruta) as conexion:
        cursor = conexion.cursor()
        camp_h01 = columna_campania(cursor, "H01_ProdHistorica")
        camp_r09 = columna_campania(cursor, "R09_Forecast_Semanal")
        reales = pd.read_sql(
            "SELECT [Semana], Sum([KG]) AS total_kg FROM [H01_ProdHistorica] "
            f"WHERE [{camp_h01}] = ? GROUP BY [Semana]",
            conexion,
            params=[campania],
        )
        r09 = pd.read_sql(
            "SELECT [Version], [Sem], Sum([Kg]) AS total_kg FROM [R09_Forecast_Semanal] "
            f"WHERE [{camp_r09}] = ? GROUP BY [Version], [Sem]",
            conexion,
            params=[campania],
        )
    reales.columns = ["semana", "kg"]
    r09.columns = ["version", "semana", "kg"]
    real_map = {int(r.semana): float(r.kg) for r in reales.itertuples()}
    r09_map = {
        (int(str(r.version).upper().removeprefix("S")), int(r.semana)): float(r.kg)
        for r in r09.itertuples()
        if str(r.version).upper().removeprefix("S").isdigit()
    }
    return real_map, r09_map


def libros_semana(root: Path, semana: int) -> dict[str, Path]:
    seleccionados, _ = seleccionar_libros_parametros(root, semanas=(semana,))
    if seleccionados.empty:
        raise ValueError(f"No hay libros canónicos para S{semana:02d}")
    return {
        str(fila.fundo_operativo): Path(str(fila.ruta_fuente))
        for fila in seleccionados.itertuples()
    }


def normalizar_clave(valor: object) -> str:
    return str(valor).strip()


def columna(frame: pd.DataFrame, *nombres: str) -> str | None:
    buscados = {str(nombre).strip().casefold().replace("%", "") for nombre in nombres}
    for nombre in frame.columns:
        canonico = str(nombre).strip().casefold().replace("%", "")
        if canonico in buscados:
            return str(nombre)
    return None


def preparar_lote(parametros: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    p = parametros.copy()
    q = panel.copy()
    p["Modulo"] = p["Modulo"].map(normalizar_clave)
    p["Lote"] = p["Lote"].map(normalizar_clave)
    q["Modulo"] = q["Modulo"].map(normalizar_clave)
    q["Lote"] = q["Lote"].map(normalizar_clave)
    columnas_parametros = ["Modulo", "Lote"] + [
        nombre for nombre in PARAMETROS_CURVA if nombre in p.columns
    ]
    columnas_panel = ["Modulo", "Lote"] + [
        nombre for nombre in q.columns if str(nombre).casefold().startswith("fepas")
    ]
    caida = columna(q, "Caida", "%Caida")
    finicio = columna(q, "Finicio")
    if caida is not None:
        columnas_panel.append(caida)
    if finicio is not None:
        columnas_panel.append(finicio)
    parametros_minimos = p.loc[:, columnas_parametros].drop_duplicates(
        ["Modulo", "Lote"], keep="last"
    )
    panel_minimo = (
        q.loc[:, list(dict.fromkeys(columnas_panel))]
        .drop_duplicates(["Modulo", "Lote"], keep="last")
        .copy()
    )
    renombres = {}
    if caida is not None:
        renombres[caida] = "Caida"
    if finicio is not None:
        renombres[finicio] = "Finicio"
    panel_minimo.rename(columns=renombres, inplace=True)
    return parametros_minimos.merge(
        panel_minimo,
        on=["Modulo", "Lote"],
        how="left",
        validate="one_to_one",
    )


def aplicar_modelo(
    modelo: CandidateParamDelta,
    parametros: pd.DataFrame,
    panel: pd.DataFrame,
    *,
    fundo: str,
    bloque: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    p = parametros.copy()
    q = panel.copy()
    combinado = preparar_lote(p, q)
    indice_parametros = {
        (normalizar_clave(fila.Modulo), normalizar_clave(fila.Lote)): indice
        for indice, fila in p.iterrows()
    }
    indice_panel = {
        (normalizar_clave(fila.Modulo), normalizar_clave(fila.Lote)): indice
        for indice, fila in q.iterrows()
    }
    niveles: dict[str, int] = {}
    for fila in combinado.to_dict("records"):
        clave = (normalizar_clave(fila["Modulo"]), normalizar_clave(fila["Lote"]))
        previos = {nombre: fila.get(nombre) for nombre in PARAMETROS_CURVA}
        previos["%Caida"] = fila.get("Caida")
        previos["Finicio"] = fila.get("Finicio")
        for nombre in combinado.columns:
            if str(nombre).casefold().startswith("fepas"):
                numero = str(nombre)[5:]
                if numero.isdigit():
                    previos[f"FePas{int(numero)}"] = fila.get(nombre)
        resultado = modelo.predict(
            previos,
            {"fundo": fundo, "modulo": clave[0], "lote": clave[1]},
        )
        niveles[resultado["nivel_calibracion"]] = (
            niveles.get(resultado["nivel_calibracion"], 0) + 1
        )
        finales = resultado["parametros"]
        if bloque in {"parametros", "todo"}:
            for nombre in PARAMETROS_CURVA:
                if nombre in finales and clave in indice_parametros:
                    p.at[indice_parametros[clave], nombre] = finales[nombre]
        if bloque in {"calendario", "todo"} and clave in indice_panel:
            caida_col = columna(q, "Caida", "%Caida")
            finicio_col = columna(q, "Finicio")
            if "%Caida" in finales and caida_col is not None:
                q.at[indice_panel[clave], caida_col] = finales["%Caida"]
            # FePas forma un calendario ordenado. Predecir cada fecha de manera
            # independiente puede invertir o repetir pasadas; por eso aprendemos
            # un único desplazamiento robusto y conservamos los intervalos que ya
            # estaban disponibles en la emisión anterior.
            desplazamientos = []
            for nombre, valor_previo in previos.items():
                if not str(nombre).casefold().startswith("fepas") or nombre not in finales:
                    continue
                previo_ts = pd.to_datetime(valor_previo, errors="coerce")
                final_ts = pd.to_datetime(finales[nombre], errors="coerce")
                if pd.notna(previo_ts) and pd.notna(final_ts):
                    desplazamientos.append((final_ts - previo_ts).days)
            delta_calendario = (
                int(round(float(np.median(desplazamientos)))) if desplazamientos else 0
            )
            if finicio_col is not None and pd.notna(
                pd.to_datetime(previos.get("Finicio"), errors="coerce")
            ):
                q.at[indice_panel[clave], finicio_col] = (
                    pd.Timestamp(previos["Finicio"]) + pd.Timedelta(days=delta_calendario)
                ).date()
            for nombre, valor_previo in previos.items():
                if not str(nombre).casefold().startswith("fepas"):
                    continue
                destino = columna(q, nombre)
                fecha_previa = pd.to_datetime(valor_previo, errors="coerce")
                if destino is not None and pd.notna(fecha_previa):
                    q.at[indice_panel[clave], destino] = (
                        pd.Timestamp(fecha_previa) + pd.Timedelta(days=delta_calendario)
                    ).date()
    return p, q, niveles


def proyectar_emision_detallada(
    root: Path,
    modelo: CandidateParamDelta,
    *,
    semana_emision: int,
    campania: str,
    bloque: str,
    cache_libros: dict[int, dict[str, tuple[pd.DataFrame, pd.DataFrame]]] | None = None,
) -> tuple[dict[str, float], dict[str, int]]:
    fuente = semana_emision - 1
    cache_libros = cache_libros if cache_libros is not None else {}
    if fuente not in cache_libros:
        cache_libros[fuente] = {}
        for fundo, ruta in libros_semana(root, fuente).items():
            parametros, panel, _ = leer_libro_operativo(ruta)
            cache_libros[fuente][fundo] = (parametros, panel)
    objetivo = semana_emision + 1
    por_fundo: dict[str, float] = {}
    niveles_total: dict[str, int] = {}
    for fundo, (parametros_base, panel_base) in cache_libros[fuente].items():
        parametros = parametros_base.copy(deep=True)
        panel = panel_base.copy(deep=True)
        parametros, panel, niveles = aplicar_modelo(
            modelo,
            parametros,
            panel,
            fundo=fundo,
            bloque=bloque,
        )
        motor = ejecutar_proyeccion_semanal_dataframe(
            df_parametros=parametros,
            df_panel=panel,
            campana=campania,
            fundo_nombre=fundo,
        )
        fechas = pd.to_datetime(motor["FeCos"])
        semanas = fechas.dt.isocalendar().week.astype(int)
        por_fundo[fundo] = float(motor.loc[semanas.eq(objetivo), "Kg"].sum())
        for nivel, n in niveles.items():
            niveles_total[nivel] = niveles_total.get(nivel, 0) + n
    return por_fundo, niveles_total


def proyectar_emision(
    root: Path,
    modelo: CandidateParamDelta,
    *,
    semana_emision: int,
    campania: str,
    bloque: str,
    cache_libros: dict[int, dict[str, tuple[pd.DataFrame, pd.DataFrame]]] | None = None,
) -> tuple[float, dict[str, int]]:
    """Compatibilidad: agrega la salida detallada sin perder trazabilidad."""

    por_fundo, niveles = proyectar_emision_detallada(
        root,
        modelo,
        semana_emision=semana_emision,
        campania=campania,
        bloque=bloque,
        cache_libros=cache_libros,
    )
    return float(sum(por_fundo.values())), niveles


__all__ = [
    "ACCESS_DEFAULT",
    "PARAMETROS_CALENDARIO",
    "PARAMETROS_CURVA",
    "ROOT_DEFAULT",
    "TRANSITIONS_DEFAULT",
    "aplicar_modelo",
    "cargar_reales_y_r09",
    "columna",
    "columna_campania",
    "conexion_access",
    "libros_semana",
    "normalizar_clave",
    "preparar_lote",
    "proyectar_emision",
    "proyectar_emision_detallada",
]

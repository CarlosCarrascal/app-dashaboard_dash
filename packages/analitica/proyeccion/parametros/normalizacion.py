"""Normalización y selección as-of de parámetros tipo Excel."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ...nucleo.bhattacharya import ParametrosBhattacharya
from .contratos import PARAMETROS_NOMBRADOS


def normalizar_parametros_excel(
    tabla: pd.DataFrame,
    *,
    fuente: str | None = None,
    archivo_fuente: str | None = None,
    sha256_fuente: str | None = None,
) -> pd.DataFrame:
    """Normaliza parámetros Excel por nombre, nunca por posición de columna.

    No calcula kilos ni completa parámetros ausentes. La tabla resultante puede ser
    cargada en ``DatosProyeccion.parametros_legacy`` por un adaptador de ingestión.
    """

    if tabla is None or tabla.empty:
        return pd.DataFrame()
    salida = tabla.copy()
    # Algunos libros conservan columnas vacías repetidas al final de la hoja. No
    # contienen parámetros, pero impedirían reindexar el contrato por nombre.
    salida = salida.loc[:, ~salida.columns.duplicated()]
    mapa = {str(columna).strip().casefold().replace(" ", ""): columna for columna in salida.columns}
    for canonico in PARAMETROS_NOMBRADOS:
        original = mapa.get(canonico.casefold())
        if original is not None and canonico not in salida:
            salida[canonico] = salida[original]
    for columna in PARAMETROS_NOMBRADOS:
        if columna in salida:
            salida[columna] = pd.to_numeric(salida[columna], errors="coerce")
    if fuente is not None:
        salida["fuente_parametros"] = fuente
    if archivo_fuente is not None:
        salida["archivo_fuente"] = archivo_fuente
    if sha256_fuente is not None:
        salida["sha256_fuente"] = sha256_fuente
    faltantes = [c for c in PARAMETROS_NOMBRADOS if c not in salida]
    salida["parametros_completos"] = ~salida.reindex(columns=PARAMETROS_NOMBRADOS).isna().any(
        axis=1
    )
    salida["parametros_faltantes"] = ",".join(faltantes)
    return salida


def _serie_numerica(tabla: pd.DataFrame, columna: str, indice) -> pd.Series:
    if columna not in tabla:
        return pd.Series(np.nan, index=indice, dtype=float)
    return pd.to_numeric(tabla[columna], errors="coerce").reindex(indice)


def _parametros_excel_asof(
    datos, panel: pd.DataFrame, fecha: pd.Timestamp
) -> dict[tuple[str, str], ParametrosBhattacharya]:
    """Convierte filas Excel vigentes en priors para el calibrador automático."""

    tabla = getattr(datos, "parametros_legacy", pd.DataFrame())
    if tabla is None or tabla.empty:
        return {}
    tabla = normalizar_parametros_excel(tabla)
    if not tabla.get("parametros_completos", pd.Series(False, index=tabla.index)).any():
        return {}
    fecha = pd.Timestamp(fecha).normalize()
    columnas_lote = [c for c in ("lote_id", "lote", "Lote") if c in tabla]
    if not columnas_lote:
        return {}
    columna_lote = columnas_lote[0]
    if "fecha_emision" in tabla:
        tabla = tabla[pd.to_datetime(tabla.fecha_emision, errors="coerce").lt(fecha)]
    salida: dict[tuple[str, str], ParametrosBhattacharya] = {}

    def _fundo_operativo(valor: object) -> str:
        texto = str(valor or "").casefold()
        if "arena" in texto or texto.endswith("1"):
            return "Arena"
        if "ayllu" in texto or texto.endswith("4"):
            return "Ayllu"
        if "quri" in texto or texto.endswith("2"):
            return "Quri"
        if "kawsay" in texto or texto.endswith("3") or texto.endswith("5"):
            return "Kawsay"
        return ""

    for fila in tabla[tabla.parametros_completos].to_dict("records"):
        lote = str(fila.get(columna_lote)).strip()
        # Excel identifica el lote como L039; PostgreSQL usa lote_id numérico y
        # conserva además el código comercial. La coincidencia debe usar el código
        # y, cuando está disponible, módulo/fundo; comparar contra lote_id solo
        # dejaba todos los priors Excel fuera del challenger.
        if "lote" in panel:
            coincidencias = panel[panel.lote.astype(str).str.strip().eq(lote)]
        else:
            coincidencias = panel[panel.lote_id.astype(str).eq(lote)]
        modulo = str(fila.get("Modulo", fila.get("modulo", ""))).strip()
        if modulo and "modulo" in coincidencias:
            coincidencias = coincidencias[coincidencias.modulo.astype(str).str.strip().eq(modulo)]
        fundo_excel = fila.get("fundo_operativo", fila.get("Fundo", fila.get("fundo", "")))
        fundo_operativo = _fundo_operativo(fundo_excel)
        if fundo_operativo and "fundo" in coincidencias:
            fundos = coincidencias.fundo.map(_fundo_operativo)
            coincidencias = coincidencias[fundos.eq(fundo_operativo)]
        if coincidencias.empty:
            continue
        base = coincidencias.iloc[0]
        lote_id_base = str(base.get("lote_id", lote)).strip()
        poda = pd.to_datetime(
            base.get("fecha_poda", base.get("fecha_inicio_poda")), errors="coerce"
        )
        if pd.isna(poda):
            poda = pd.Timestamp("2025-12-29")
        vigencia = pd.to_datetime(fila.get("fecha_vigencia"), errors="coerce")
        if pd.isna(vigencia):
            vigencia = None
        try:
            parametro = ParametrosBhattacharya(
                lote=str(base.get("lote", lote)),
                campania=str(base.campania),
                lote_id=lote_id_base,
                fundo=str(base.get("fundo", "")),
                modulo=str(base.get("modulo", "")),
                fecha_poda=poda,
                n_plantas=int(float(base.get("plantas", base.get("n_plantas", 5000)))),
                mu1=float(fila["X1"]),
                sigma1=float(fila["O1"]),
                N1=float(fila["N1"]),
                mu2=float(fila["X2"]),
                sigma2=float(fila["O2"]),
                N2=float(fila["N2"]),
                mu3=float(fila["X3"]),
                sigma3=float(fila["O3"]),
                N3=float(fila["N3"]),
                peso_a=float(fila["A1"]),
                peso_b=float(fila["B1"]),
                peso_a2=float(fila["A2"]),
                peso_b2=float(fila["B2"]),
                peso_a3=float(fila["A3"]),
                peso_b3=float(fila["B3"]),
                fuente_parametros="excel_prior_asof",
                nivel_calibracion="excel_vigente",
                archivo_fuente=str(fila.get("archivo_fuente") or "") or None,
                sha256_fuente=str(fila.get("sha256_fuente") or "") or None,
                fecha_vigencia=vigencia,
            )
        except (TypeError, ValueError, OverflowError):
            continue
        salida[(str(base.campania), lote_id_base)] = parametro
    return salida


__all__ = ["normalizar_parametros_excel"]

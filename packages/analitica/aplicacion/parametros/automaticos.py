"""Calibración automática de parámetros del modelo operativo desde PostgreSQL.

La salida conserva el contrato de la hoja ``Parametros`` para que el motor semanal no
dependa de cómo se obtuvieron X/O/N/A/B. El calendario de pasadas sigue llegando desde
``Panel`` hasta que exista una tabla operativa equivalente en PostgreSQL.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd

from analitica.aplicacion.servicios.servicio_bhattacharya import (
    calibrar_todos_los_lotes,
    cargar_datos_desde_db,
    cargar_lotes_objetivo_desde_db,
)
from analitica.dominio.nucleo.bhattacharya import ParametrosBhattacharya


def _campania_anterior(campania: str) -> str | None:
    coincidencia = re.fullmatch(r"C(\d{4})", str(campania).strip(), re.I)
    return None if coincidencia is None else f"C{int(coincidencia.group(1)) - 1}"


def _texto(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return ""
    return " ".join(str(valor).strip().casefold().split())


def _numero(valor: object, defecto: float = 0.0) -> float:
    numero = pd.to_numeric(pd.Series([valor]), errors="coerce").iloc[0]
    return defecto if pd.isna(numero) else float(numero)


def _lote_normalizado(valor: object) -> str:
    texto = str(valor or "").strip().upper().replace(" ", "")
    coincidencia = re.fullmatch(r"L0*(\d+)([A-Z]*)", texto)
    if coincidencia is None:
        return texto.casefold()
    return f"L{int(coincidencia.group(1)):03d}{coincidencia.group(2)}".casefold()


def _fundo_db(fundo_operativo: str, modulo: str) -> str:
    fundo = _texto(fundo_operativo)
    modulo = str(modulo).strip().upper()
    if "arena" in fundo:
        return "Aqu Anqa 1"
    if "quri" in fundo or "qury" in fundo:
        return "Aqu Anqa 2"
    if "ayllu" in fundo:
        return "Aqu Anqa 4"
    if "kawsay" in fundo:
        return (
            "Aqu Anqa 3" if modulo in {"M06", "M07", "M08", "M09", "M10A", "M10B"} else "Aqu Anqa 5"
        )
    return str(fundo_operativo).strip()


def _clave(fundo: object, modulo: object, turno: object, lote: object) -> tuple[str, str, str, str]:
    return (_texto(fundo), _texto(modulo), _texto(turno), _lote_normalizado(lote))


def _prior_grupal(
    disponibles: list[ParametrosBhattacharya],
    *,
    objetivo: pd.Series,
    campania: str,
) -> ParametrosBhattacharya:
    mismo_modulo = [
        p
        for p in disponibles
        if _texto(p.fundo) == _texto(objetivo["fundo"])
        and _texto(p.modulo) == _texto(objetivo["modulo"])
    ]
    mismo_fundo = [p for p in disponibles if _texto(p.fundo) == _texto(objetivo["fundo"])]
    # El maestro objetivo todavía no expone variedad. No se inventa ese nivel:
    # cuando esté disponible se incorporará entre fundo y global con una prueba de
    # cobertura propia.
    candidatos = mismo_modulo or mismo_fundo or disponibles
    if not candidatos:
        raise ValueError(
            f"No existen parámetros históricos para calibrar el lote {objetivo['lote_id']}"
        )

    def mediana(campo: str, defecto: float) -> float:
        valores = np.asarray(
            [float(getattr(p, campo)) for p in candidatos if np.isfinite(float(getattr(p, campo)))],
            dtype=float,
        )
        return float(np.median(valores)) if valores.size else defecto

    return ParametrosBhattacharya(
        lote_id=str(objetivo["lote_id"]),
        lote=str(objetivo["lote"]),
        campania=campania,
        fundo=str(objetivo["fundo"]),
        modulo=str(objetivo["modulo"]),
        turno=str(objetivo.get("turno", "") or ""),
        fecha_poda=pd.to_datetime(objetivo.get("fecha_poda"), errors="coerce"),
        n_plantas=int(_numero(objetivo.get("n_plantas"))),
        mu1=mediana("mu1", 220.0),
        sigma1=mediana("sigma1", 25.0),
        N1=mediana("N1", 500.0),
        mu2=mediana("mu2", 290.0),
        sigma2=mediana("sigma2", 29.0),
        N2=mediana("N2", 225.0),
        mu3=mediana("mu3", 353.0),
        sigma3=mediana("sigma3", 30.0),
        N3=mediana("N3", 100.0),
        peso_a=mediana("peso_a", 4.9),
        peso_b=mediana("peso_b", -0.001387),
        es_estimado_por_defecto=True,
        fuente_parametros="postgres",
        nivel_calibracion=(
            "modulo_historico"
            if mismo_modulo
            else "fundo_historico"
            if mismo_fundo
            else "global_historico"
        ),
    )


def calibrar_universo_operativo(
    campania: str,
    fecha_corte: str | pd.Timestamp,
) -> tuple[dict[str, ParametrosBhattacharya], pd.DataFrame, dict[str, Any]]:
    """Calibra el universo físico usando actual as-of, histórico y priors grupales."""
    actual = cargar_datos_desde_db(campania, fecha_corte=fecha_corte)
    anterior = _campania_anterior(campania)
    historico = cargar_datos_desde_db(anterior) if anterior is not None else pd.DataFrame()
    priors, _ = calibrar_todos_los_lotes(df_cosecha=historico, campania=anterior or campania)
    actuales, _ = calibrar_todos_los_lotes(
        df_cosecha=actual,
        campania=campania,
        fecha_corte=fecha_corte,
        priors_por_lote=priors,
    )
    objetivos = cargar_lotes_objetivo_desde_db(campania)
    universo: dict[str, ParametrosBhattacharya] = {}
    disponibles = list(actuales.values()) + [p for k, p in priors.items() if k not in actuales]

    niveles: dict[str, int] = {}
    for _, objetivo in objetivos.iterrows():
        lote_id = str(objetivo["lote_id"])
        parametro = actuales.get(lote_id)
        if parametro is None and lote_id in priors:
            parametro = replace(
                priors[lote_id],
                campania=campania,
                fecha_poda=pd.to_datetime(objetivo.get("fecha_poda"), errors="coerce"),
                n_plantas=int(_numero(objetivo.get("n_plantas"))),
                fuente_parametros="postgres",
                nivel_calibracion="lote_historico",
            )
        if parametro is None:
            parametro = _prior_grupal(disponibles, objetivo=objetivo, campania=campania)
        parametro = replace(
            parametro,
            lote_id=lote_id,
            lote=str(objetivo["lote"]),
            fundo=str(objetivo["fundo"]),
            modulo=str(objetivo["modulo"]),
            turno=str(objetivo.get("turno", "") or ""),
            fecha_poda=pd.to_datetime(objetivo.get("fecha_poda"), errors="coerce"),
            n_plantas=int(_numero(objetivo.get("n_plantas"))),
        )
        universo[lote_id] = parametro
        niveles[parametro.nivel_calibracion] = niveles.get(parametro.nivel_calibracion, 0) + 1

    metadata = {
        "campania": campania,
        "fecha_corte": pd.Timestamp(fecha_corte).date().isoformat(),
        "campania_prior": anterior,
        "filas_cosecha_actual": int(len(actual)),
        "lotes_con_cosecha_actual": int(actual.get("lote_id", pd.Series(dtype=str)).nunique()),
        "lotes_con_historico": int(historico.get("lote_id", pd.Series(dtype=str)).nunique()),
        "lotes_objetivo": int(len(objetivos)),
        "niveles_calibracion": niveles,
        "jerarquia_calibracion": [
            "lote_actual",
            "lote_historico",
            "modulo_historico",
            "fundo_historico",
            "variedad_historica (no disponible en el maestro actual)",
            "global_historico",
        ],
    }
    return universo, objetivos, metadata


def reemplazar_parametros_excel_por_db(
    parametros_excel: pd.DataFrame,
    *,
    fundo_operativo: str,
    universo: dict[str, ParametrosBhattacharya],
    objetivos: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Entrega el contrato Parametros con identidad DB y X/O/N/A/B automáticos."""
    salida = parametros_excel.copy()
    salida.columns = [str(c).strip() for c in salida.columns]
    indice_exacto: dict[tuple[str, str, str, str], pd.Series] = {}
    indice_sin_turno: dict[tuple[str, str, str], list[pd.Series]] = {}
    for _, fila in objetivos.iterrows():
        exacta = _clave(fila["fundo"], fila["modulo"], fila.get("turno", ""), fila["lote"])
        indice_exacto[exacta] = fila
        corta = (exacta[0], exacta[1], exacta[3])
        indice_sin_turno.setdefault(corta, []).append(fila)

    registros = []
    faltantes = []
    podas_fallback = 0
    for _, fila in salida.iterrows():
        registro = fila.to_dict()
        modulo = str(registro.get("Modulo", "")).strip()
        turno = str(registro.get("Turno", "")).strip()
        lote = str(registro.get("Lote", "")).strip()
        if not modulo or not lote or lote.casefold() == "nan":
            continue
        fundo_db = _fundo_db(fundo_operativo, modulo)
        objetivo = indice_exacto.get(_clave(fundo_db, modulo, turno, lote))
        if objetivo is None:
            candidatos = indice_sin_turno.get((_texto(fundo_db), _texto(modulo), _texto(lote)), [])
            objetivo = candidatos[0] if len(candidatos) == 1 else None
        if objetivo is None:
            faltantes.append(f"{fundo_operativo}/{modulo}/{turno}/{lote}")
            continue

        parametro = universo[str(objetivo["lote_id"])]
        fecha_poda_db = pd.to_datetime(objetivo.get("fecha_poda"), errors="coerce")
        if pd.isna(fecha_poda_db):
            fecha_poda_db = pd.to_datetime(registro.get("FPoda"), errors="coerce")
            podas_fallback += 1
            fuente_poda = "excel_fallback"
        else:
            fuente_poda = "postgres"
        if pd.isna(fecha_poda_db):
            faltantes.append(f"{fundo_operativo}/{modulo}/{turno}/{lote}:sin_poda")
            continue
        registro.update(
            {
                "Area": _numero(objetivo.get("area_ha")),
                "NPlantas": int(_numero(objetivo.get("n_plantas"))),
                "FPoda": fecha_poda_db,
                "X1": parametro.mu1,
                "O1": parametro.sigma1,
                "N1": parametro.N1,
                "X2": parametro.mu2,
                "O2": parametro.sigma2,
                "N2": parametro.N2,
                "X3": parametro.mu3,
                "O3": parametro.sigma3,
                "N3": parametro.N3,
                "A1": parametro.peso_a,
                "B1": parametro.peso_b,
                "A2": parametro.peso_a,
                "B2": parametro.peso_b,
                "A3": parametro.peso_a,
                "B3": parametro.peso_b,
                "LoteIdDB": parametro.lote_id,
                "FuenteParametros": "postgres_auto",
                "NivelCalibracion": parametro.nivel_calibracion,
                "PanasObservadas": parametro.panas_observadas,
                "RmseParametros": parametro.rmse_total,
                "FuentePoda": fuente_poda,
            }
        )
        registros.append(registro)

    if faltantes:
        ejemplo = ", ".join(faltantes[:5])
        raise ValueError(
            f"No se resolvieron {len(faltantes)} lotes de {fundo_operativo} contra "
            f"PostgreSQL: {ejemplo}"
        )
    resultado = pd.DataFrame(registros)
    metadata = {
        "fundo_operativo": fundo_operativo,
        "filas": int(len(resultado)),
        "niveles_calibracion": resultado["NivelCalibracion"].value_counts().to_dict(),
        "panas_observadas": int(pd.to_numeric(resultado["PanasObservadas"], errors="coerce").sum()),
        "podas_excel_fallback": int(podas_fallback),
        "rmse_mediano_frutos_planta": float(
            pd.to_numeric(resultado["RmseParametros"], errors="coerce").median()
        ),
    }
    return resultado, metadata


__all__ = ["calibrar_universo_operativo", "reemplazar_parametros_excel_por_db"]

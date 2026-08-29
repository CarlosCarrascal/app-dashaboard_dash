"""Ingeniería de ventanas temporales para el panel analítico.

Este módulo conoce únicamente la tabla ya normalizada y el contrato de hallazgos.
No lee fuentes ni importa el orquestador del panel, por lo que puede probarse de
forma aislada y reutilizarse sin crear ciclos en el núcleo.
"""

from __future__ import annotations

import pandas as pd

from .contratos import Hallazgo


def _rolling_semanal(serie_por_semana: pd.Series, ventana: int) -> pd.Series:
    """Promedio móvil de una serie indexada por semana, contando huecos como NaN."""
    completa = serie_por_semana.reindex(
        range(int(serie_por_semana.index.min()), int(serie_por_semana.index.max()) + 1)
    )
    return completa.rolling(ventana, min_periods=ventana).mean()


def _rolling_climatico(tabla: pd.DataFrame, col: str, ventana: int) -> pd.Series:
    """Rueda una variable climática una vez por semana y la devuelve al panel."""
    semanal = tabla.drop_duplicates("nsem").set_index("nsem")[col].sort_index()
    rolado = _rolling_semanal(semanal, ventana)
    return tabla.nsem.map(rolado)


def _rolling_por_modulo(tabla: pd.DataFrame, col: str, ventana: int) -> pd.Series:
    """Rueda una variable que cambia por módulo, reindexando cada calendario."""
    resultado = pd.Series(index=tabla.index, dtype=float)
    for _, grupo in tabla.groupby(["Fundo", "Modulo"]):
        semanal = grupo.set_index("nsem")[col].sort_index()
        rolado = _rolling_semanal(semanal, ventana)
        resultado.loc[grupo.index] = rolado.reindex(grupo.nsem).to_numpy()
    return resultado


def _agregar_lags(
    tabla: pd.DataFrame, lags_config: dict, hallazgos: list[Hallazgo]
) -> pd.DataFrame:
    """Aplica promedios móviles completos con ventanas independientes por variable."""
    columnas_lag = []
    for col in ("DPV", "Rad", "ETo", "gdd_semana"):
        key_name = "gdd" if col == "gdd_semana" else col
        target_name = "gdd_lag" if col == "gdd_semana" else f"{col}_lag"
        v = max(1, lags_config.get(key_name, 1))
        tabla[target_name] = tabla[col] if v == 1 else _rolling_climatico(tabla, col, v)
        columnas_lag.append(target_name)

    v_riego = max(1, lags_config.get("riego", 1))
    tabla["riego_lag"] = (
        tabla["riego_lt_planta"]
        if v_riego == 1
        else _rolling_por_modulo(tabla, "riego_lt_planta", v_riego)
    )
    columnas_lag.append("riego_lag")

    incompletas = int(tabla[columnas_lag].isna().any(axis=1).sum())
    if incompletas:
        ventanas = ", ".join(
            f"{etq}={lags_config.get(k, 1)} sem."
            for k, etq in [
                ("riego", "riego"),
                ("Rad", "Rad"),
                ("ETo", "ETo"),
                ("DPV", "DPV"),
                ("gdd", "GDD"),
            ]
            if lags_config.get(k, 1) > 1
        )
        hallazgos.append(
            Hallazgo(
                "lags_ventana_incompleta",
                "Celdas sin ventana de rezago completa",
                "media",
                f"{incompletas} de {len(tabla)} celdas no tienen las semanas de calendario "
                f"previas que pide la ventana configurada ({ventanas or 'todas en 1 semana'})"
                " — el módulo empezó su cosecha hace menos semanas que el largo de la ventana, "
                "o tuvo un hueco de cosecha justo antes.",
                "Esas celdas se excluyen del entrenamiento del modelo (no se rellenan con una "
                "ventana parcial): un promedio de 3 semanas cuando se pidieron 7 mediría otra "
                "cosa. Datos y calidad y la exportación indican cuántas filas quedan fuera.",
            )
        )
    return tabla


def diagnostico_ventanas(tabla: pd.DataFrame, lags_config: dict | None = None) -> pd.DataFrame:
    """Expone cómo se construyó cada variable temporal que ve el modelo."""
    cfg = {"riego": 7, "Rad": 3, "ETo": 2, "DPV": 6, "gdd": 7}
    cfg.update(lags_config or {})
    especificaciones = [
        ("DPV_lag", "DPV", "DPV", "clima · una serie por semana", "media móvil calendario"),
        (
            "riego_lag",
            "riego_lt_planta",
            "riego",
            "riego · Fundo + Módulo",
            "media móvil por módulo",
        ),
        ("Rad_lag", "Rad", "Rad", "clima · una serie por semana", "media móvil calendario"),
        ("ETo_lag", "ETo", "ETo", "clima · una serie por semana", "media móvil calendario"),
        ("gdd_lag", "gdd_semana", "gdd", "clima · una serie por semana", "media móvil calendario"),
        ("TempMax", "TempMax", None, "clima · semana actual", "valor de la semana"),
        ("TempMin", "TempMin", None, "clima · semana actual", "valor de la semana"),
    ]
    filas = []
    for destino, fuente, clave, ambito, regla in especificaciones:
        serie = tabla[destino]
        por_semana = tabla.groupby("nsem")[destino].nunique(dropna=True)
        filas.append(
            {
                "Columna modelo": destino,
                "Columna fuente": fuente,
                "Ventana (sem)": int(cfg[clave]) if clave else 1,
                "Cobertura temporal": (
                    f"t-{int(cfg[clave]) - 1} a t" if clave and int(cfg[clave]) > 1 else "t"
                ),
                "Incluye semana objetivo": "Si",
                "Ámbito": ambito,
                "Regla aplicada": regla,
                "Filas con valor": int(serie.notna().sum()),
                "Semanas con valor": int(tabla.loc[serie.notna(), "nsem"].nunique()),
                "Max. valores distintos por semana": (
                    int(por_semana.max()) if not por_semana.empty else 0
                ),
            }
        )
    return pd.DataFrame(filas)


__all__ = ["diagnostico_ventanas"]

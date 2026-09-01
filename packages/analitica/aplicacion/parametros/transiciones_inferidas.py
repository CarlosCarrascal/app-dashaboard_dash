"""Transiciones de parámetros inferidas desde H01, sin depender de Excel.

El libro manual sigue siendo la mejor fuente para saber qué parámetros cambiaron y
por qué el equipo los modificó. Cuando esa revisión no está disponible, este módulo
construye una señal sustituta: ajusta la misma curva Gaussian/exponencial a H01 en
varias fechas de corte y convierte la diferencia entre dos cortes en una transición
X/O/N/A/B.

La salida es deliberadamente ``inferida``. No representa una edición humana del
libro ni una causa agronómica. Sirve para probar si el contexto histórico aporta
señal predictiva antes de conectar la fuente manual real.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from analitica.dominio.modelos.hibrido import (
    MacroParams,
    construir_prior_automatico,
)

from .oleadas_candidato import PARAMETROS_CURVA

_CLAVES_SALIDA = ("campania", "fundo", "modulo", "turno", "lote")
_CLAVES_FISICAS = ("campania", "modulo", "turno", "lote")
_PARAMETROS_TRANSICION = tuple(PARAMETROS_CURVA)


def _nombre_columna(valor: object) -> str:
    return "".join(caracter for caracter in str(valor).strip().casefold() if caracter.isalnum())


def _alias(tabla: pd.DataFrame, nombres: Sequence[str]) -> str | None:
    disponibles = {_nombre_columna(columna): str(columna) for columna in tabla.columns}
    for nombre in nombres:
        columna = disponibles.get(_nombre_columna(nombre))
        if columna is not None:
            return columna
    return None


def _texto(serie: pd.Series) -> pd.Series:
    salida = serie.astype("string").str.strip()
    return salida.mask(
        salida.isna()
        | salida.eq("")
        | salida.str.casefold().isin({"nan", "none", "nat"})
    )


def _normalizar_identidad(tabla: pd.DataFrame) -> pd.DataFrame:
    salida = tabla.copy()
    aliases = {
        "campania": ("campania", "campaña", "campana"),
        "fundo": ("fundo", "fundo_ppto", "fundo_operativo"),
        "modulo": ("modulo", "módulo", "modulo_id"),
        "turno": ("turno", "turno_id"),
        "lote": ("lote", "lote_id", "lote_codigo"),
    }
    for canonico, nombres in aliases.items():
        columna = canonico if canonico in salida else _alias(salida, nombres)
        salida[canonico] = salida[columna] if columna is not None else pd.NA
        salida[canonico] = _texto(salida[canonico])
    return salida


def _numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce")


def _clave(fila: Mapping[str, Any], columnas: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        "" if fila.get(nombre) is None or pd.isna(fila.get(nombre)) else str(fila[nombre]).strip()
        for nombre in columnas
    )


def _normalizar_lotes(lotes: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(lotes, pd.DataFrame) or lotes.empty:
        raise ValueError("lotes debe ser un DataFrame no vacío")
    salida = _normalizar_identidad(lotes)
    columna_area = _alias(salida, ("area_ha", "area", "Area"))
    columna_plantas = _alias(salida, ("plantas", "n_plantas", "NPlantas"))
    columna_pivote = _alias(
        salida, ("fecha_pivote", "fecha_poda", "fecha_inicio", "FPoda")
    )
    salida["area_ha"] = (
        _numero(salida[columna_area])
        if columna_area is not None
        else np.nan
    )
    salida["plantas"] = (
        _numero(salida[columna_plantas])
        if columna_plantas is not None
        else np.nan
    )
    salida["fecha_pivote"] = (
        pd.to_datetime(salida[columna_pivote], errors="coerce").dt.normalize()
        if columna_pivote is not None
        else pd.NaT
    )
    salida.loc[salida.fecha_pivote.dt.year.lt(2000), "fecha_pivote"] = pd.NaT
    validas = (
        salida[list(_CLAVES_FISICAS)].notna().all(axis=1)
        & salida.area_ha.gt(0)
        & salida.plantas.gt(0)
        & salida.fecha_pivote.notna()
    )
    salida = salida.loc[validas].copy()
    if salida.empty:
        raise ValueError("lotes no tiene filas con identidad, area, plantas y pivote válidos")
    # M_Poda puede traer varias revisiones del mismo lote. Para una emisión se usa
    # la poda vigente más reciente y no se generan dos estados físicos en paralelo.
    salida = salida.sort_values("fecha_pivote", kind="stable")
    salida = (
        salida.groupby(list(_CLAVES_FISICAS), as_index=False, dropna=False)
        .agg(
            fundo=("fundo", "last"),
            area_ha=("area_ha", "max"),
            plantas=("plantas", "max"),
            fecha_pivote=("fecha_pivote", "last"),
        )
    )
    return salida


def _normalizar_cosecha(cosecha: pd.DataFrame | None) -> pd.DataFrame:
    if cosecha is None:
        return pd.DataFrame()
    if not isinstance(cosecha, pd.DataFrame):
        raise TypeError("cosecha debe ser un DataFrame o None")
    if cosecha.empty:
        return cosecha.copy()
    salida = _normalizar_identidad(cosecha)
    columna_fecha = _alias(
        salida, ("fecha", "fecha_cosecha", "fecha_real", "fecha_dato")
    )
    if columna_fecha is None:
        raise ValueError("cosecha requiere fecha, fecha_cosecha o fecha_dato")
    salida["__fecha_cosecha"] = pd.to_datetime(
        salida[columna_fecha], errors="coerce"
    ).dt.normalize()
    validas = salida[list(_CLAVES_FISICAS)].notna().all(axis=1) & salida[
        "__fecha_cosecha"
    ].notna()
    return salida.loc[validas].copy()


def _normalizar_emisiones(fechas_emision: Sequence[object]) -> tuple[pd.Timestamp, ...]:
    fechas = tuple(pd.Timestamp(fecha).normalize() for fecha in fechas_emision)
    if len(fechas) < 2 or any(pd.isna(fecha) for fecha in fechas):
        raise ValueError("fechas_emision debe contener al menos dos fechas válidas")
    if len(set(fechas)) != len(fechas):
        raise ValueError("fechas_emision no puede repetir fechas")
    return tuple(sorted(fechas))


def _parametros_a_mapping(parametros: MacroParams) -> dict[str, float]:
    return {
        "X1": parametros.ola_1_media_dias,
        "O1": parametros.ola_1_desvio_dias,
        "N1": parametros.ola_1_multiplicador,
        "X2": parametros.ola_2_media_dias,
        "O2": parametros.ola_2_desvio_dias,
        "N2": parametros.ola_2_multiplicador,
        "X3": parametros.ola_3_media_dias,
        "O3": parametros.ola_3_desvio_dias,
        "N3": parametros.ola_3_multiplicador,
        "A1": parametros.peso_1_base_g,
        "B1": parametros.peso_1_tasa,
        "A2": parametros.peso_2_base_g,
        "B2": parametros.peso_2_tasa,
        "A3": parametros.peso_3_base_g,
        "B3": parametros.peso_3_tasa,
    }


def _fila_ajuste(
    lote: Mapping[str, Any],
    historia: pd.DataFrame,
    fecha_emision: pd.Timestamp,
    *,
    intervalo_dias: int,
    fuerza_prior: float | None,
) -> dict[str, Any]:
    resultado = construir_prior_automatico(
        fecha_pivote=lote["fecha_pivote"],
        plantas=float(lote["plantas"]),
        area_ha=float(lote["area_ha"]),
        observaciones=historia,
        fecha_corte=fecha_emision,
        intervalo_dias=intervalo_dias,
        fuerza_prior=fuerza_prior,
    )
    fila = {
        "parametros": _parametros_a_mapping(resultado.parametros),
        "n_observaciones": int(resultado.n_observaciones),
        "n_observaciones_peso": int(resultado.n_observaciones_peso),
        "rmse_frutos_por_planta": resultado.rmse_frutos_por_planta,
        "rmse_peso_g": resultado.rmse_peso_g,
        "fuente": resultado.fuente,
        "advertencias": list(resultado.advertencias),
    }
    return fila


def construir_transiciones_gaussianas_asof(
    lotes: pd.DataFrame,
    cosecha: pd.DataFrame | None,
    fechas_emision: Sequence[object],
    *,
    minimo_observaciones: int = 6,
    intervalo_dias: int = 7,
    fuerza_prior: float | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Infiere transiciones de parámetros entre cortes históricos.

    Para cada lote y fecha se ajusta la misma curva que usa el candidato automático
    con filas H01 estrictamente anteriores al corte. Solo se conserva una transición
    cuando el lote tiene al menos ``minimo_observaciones`` pasadas en ambos cortes.
    La fecha de la transición es la segunda emisión, que es la fecha a la que luego
    se une el contexto as-of.

    El resultado puede alimentar :class:`ModeloContextoOleadas`, pero debe llevarse
    separado de transiciones humanas: el ajuste puede confundir una falta de cosecha,
    un cambio de escala o una identificación débil de oleadas con un cambio agronómico.
    """

    if int(minimo_observaciones) < 1:
        raise ValueError("minimo_observaciones debe ser positivo")
    if int(intervalo_dias) < 1:
        raise ValueError("intervalo_dias debe ser positivo")
    emisiones = _normalizar_emisiones(fechas_emision)
    lotes_n = _normalizar_lotes(lotes)
    cosecha_n = _normalizar_cosecha(cosecha)

    historias: dict[tuple[str, ...], pd.DataFrame] = {}
    if not cosecha_n.empty:
        for clave, grupo in cosecha_n.groupby(list(_CLAVES_FISICAS), sort=False, dropna=False):
            clave_t = clave if isinstance(clave, tuple) else (clave,)
            historias[tuple(str(valor).strip() for valor in clave_t)] = grupo.copy()

    ajustes: dict[tuple[tuple[str, ...], pd.Timestamp], dict[str, Any] | None] = {}
    conteo_ajustes: dict[str, int] = {fecha.strftime("%Y-%m-%d"): 0 for fecha in emisiones}
    lotes_con_historia: set[tuple[str, ...]] = set()
    advertencias: list[str] = []
    for registro in lotes_n.to_dict("records"):
        clave = _clave(registro, _CLAVES_FISICAS)
        historia = historias.get(clave, pd.DataFrame())
        for fecha in emisiones:
            if pd.Timestamp(registro["fecha_pivote"]).normalize() >= fecha:
                ajustes[(clave, fecha)] = None
                continue
            ajuste = _fila_ajuste(
                registro,
                historia,
                fecha,
                intervalo_dias=intervalo_dias,
                fuerza_prior=fuerza_prior,
            )
            ajustes[(clave, fecha)] = ajuste
            if ajuste["n_observaciones"] >= int(minimo_observaciones):
                conteo_ajustes[fecha.strftime("%Y-%m-%d")] += 1
                lotes_con_historia.add(clave)

    filas: list[dict[str, Any]] = []
    for fecha_anterior, fecha_actual in zip(emisiones[:-1], emisiones[1:], strict=True):
        for registro in lotes_n.to_dict("records"):
            clave = _clave(registro, _CLAVES_FISICAS)
            previo = ajustes.get((clave, fecha_anterior))
            actual = ajustes.get((clave, fecha_actual))
            if previo is None or actual is None:
                continue
            if (
                previo["n_observaciones"] < int(minimo_observaciones)
                or actual["n_observaciones"] < int(minimo_observaciones)
            ):
                continue
            fila: dict[str, Any] = {
                "campania": registro["campania"],
                "fundo": registro["fundo"],
                "modulo": registro["modulo"],
                "turno": registro["turno"],
                "lote": registro["lote"],
                "fecha_emision_anterior": fecha_anterior,
                "fecha_emision_actual": fecha_actual,
                "fecha_pivote": registro["fecha_pivote"],
                "n_observaciones_anterior": previo["n_observaciones"],
                "n_observaciones_actual": actual["n_observaciones"],
                "n_observaciones_peso_anterior": previo["n_observaciones_peso"],
                "n_observaciones_peso_actual": actual["n_observaciones_peso"],
                "rmse_frutos_anterior": previo["rmse_frutos_por_planta"],
                "rmse_frutos_actual": actual["rmse_frutos_por_planta"],
                "rmse_peso_anterior": previo["rmse_peso_g"],
                "rmse_peso_actual": actual["rmse_peso_g"],
                "fuente_parametros_anterior": previo["fuente"],
                "fuente_parametros_actual": actual["fuente"],
                "fuente_parametros": "h01_gaussian_asof_inferido",
                "transicion_inferida": True,
                "etiqueta_causal": False,
                "sin_fuga": True,
            }
            fila.update(
                {
                    f"{parametro}_anterior": previo["parametros"][parametro]
                    for parametro in _PARAMETROS_TRANSICION
                }
            )
            fila.update(
                {
                    f"{parametro}_actual": actual["parametros"][parametro]
                    for parametro in _PARAMETROS_TRANSICION
                }
            )
            filas.append(fila)

    columnas = [
        *_CLAVES_SALIDA,
        "fecha_emision_anterior",
        "fecha_emision_actual",
        "fecha_pivote",
        *(
            f"{parametro}_{lado}"
            for lado in ("anterior", "actual")
            for parametro in _PARAMETROS_TRANSICION
        ),
        "n_observaciones_anterior",
        "n_observaciones_actual",
        "n_observaciones_peso_anterior",
        "n_observaciones_peso_actual",
        "rmse_frutos_anterior",
        "rmse_frutos_actual",
        "rmse_peso_anterior",
        "rmse_peso_actual",
        "fuente_parametros_anterior",
        "fuente_parametros_actual",
        "fuente_parametros",
        "transicion_inferida",
        "etiqueta_causal",
        "sin_fuga",
    ]
    salida = pd.DataFrame(filas)
    salida = (
        pd.DataFrame(columns=columnas)
        if salida.empty
        else salida.reindex(columns=columnas)
    )
    for columna in ("fecha_emision_anterior", "fecha_emision_actual", "fecha_pivote"):
        if columna in salida:
            salida[columna] = pd.to_datetime(salida[columna], errors="coerce").dt.normalize()

    for fecha, cantidad in conteo_ajustes.items():
        if cantidad == 0:
            advertencias.append(f"sin_ajustes_con_{minimo_observaciones}_observaciones:{fecha}")
    metadata: dict[str, Any] = {
        "fuente": "h01_gaussian_asof_inferido",
        "inferencia": True,
        "etiqueta_causal": False,
        "sin_fuga": True,
        "minimo_observaciones": int(minimo_observaciones),
        "intervalo_dias": int(intervalo_dias),
        "fechas_emision": [fecha.strftime("%Y-%m-%d") for fecha in emisiones],
        "lotes_entrada": int(len(lotes_n)),
        "lotes_con_historia_suficiente": int(len(lotes_con_historia)),
        "ajustes_suficientes_por_emision": conteo_ajustes,
        "transiciones": int(len(salida)),
        "advertencias": advertencias,
    }
    return salida, metadata


__all__ = ["construir_transiciones_gaussianas_asof"]

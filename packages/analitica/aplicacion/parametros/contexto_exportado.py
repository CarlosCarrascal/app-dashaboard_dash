"""Construcción reproducible del contexto de oleadas desde exportaciones.

Las hojas de operación ya contienen piezas que pueden ayudar a actualizar X/O/N y
A/B, pero no están en el mismo grano ni comparten siempre la misma identidad:

* poda y H01 identifican campaña, módulo, turno y lote;
* flores, estados y brotes llegan normalmente como módulo-lote-fecha; y
* clima es una serie global fechada.

Este módulo resuelve esas diferencias y devuelve una fila por transición o lote en
la fecha de emisión. Todas las fuentes se cortan con fecha_dato < fecha_emision.
Las asociaciones que entrega son variables de contexto para el modelo; no se
presentan como causas.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from .contexto_oleadas import FEATURES_CONTEXTO_POR_DEFECTO, unir_contexto_asof

_CLAVES_COMPLETAS = ("campania", "fundo", "modulo", "turno", "lote")
_CLAVES_LOTE = ("campania", "modulo", "turno", "lote")


def _nombre_columna(valor: object) -> str:
    texto = str(valor).strip().casefold()
    return "".join(caracter for caracter in texto if caracter.isalnum())


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
        salida.isna() | salida.eq("") | salida.str.casefold().isin({"nan", "none", "nat"})
    )


def _normalizar_identidad(tabla: pd.DataFrame) -> pd.DataFrame:
    salida = tabla.copy()
    aliases = {
        "campania": ("campania", "campaña", "campana"),
        "fundo": (
            "fundo",
            "fundo_ppto",
            "fundo_operativo",
            "fundo_poda",
            "fundoac",
        ),
        "modulo": ("modulo", "módulo", "modulo_id"),
        "turno": ("turno", "turno_id"),
        "lote": ("lote", "lote_codigo"),
    }
    for canonico, nombres in aliases.items():
        if canonico not in salida:
            columna = _alias(salida, nombres)
            salida[canonico] = salida[columna] if columna is not None else pd.NA
        salida[canonico] = _texto(salida[canonico])
    return salida


def _fecha(tabla: pd.DataFrame, nombres: Sequence[str]) -> tuple[pd.Series, str | None]:
    columna = _alias(tabla, nombres)
    if columna is None:
        return pd.Series(pd.NaT, index=tabla.index, dtype="datetime64[ns]"), None
    return pd.to_datetime(tabla[columna], errors="coerce").dt.normalize(), columna


def _numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce")


def _claves_disponibles(
    transiciones: pd.DataFrame,
    fuente: pd.DataFrame,
    preferidas: Sequence[str],
) -> list[str]:
    claves = [
        clave
        for clave in preferidas
        if clave in transiciones
        and clave in fuente
        and transiciones[clave].notna().any()
        and fuente[clave].notna().any()
    ]
    if not claves:
        raise ValueError("no hay claves comunes para unir una fuente de contexto")
    return claves


def _validar_fuente_sin_campania(
    transiciones: pd.DataFrame,
    fuente: pd.DataFrame,
    *,
    nombre: str,
) -> None:
    """Evita mezclar ciclos cuando una hoja solo identifica módulo/turno."""

    if "campania" not in fuente or fuente["campania"].notna().any():
        return
    campanias = transiciones["campania"].dropna().astype(str).nunique()
    if campanias > 1:
        raise ValueError(
            f"{nombre} no contiene campaña y no se puede unir a {campanias} campañas "
            "en una misma corrida; filtre la fuente o emita una campaña por vez"
        )


def _unir_fuente(
    transiciones: pd.DataFrame,
    fuente: pd.DataFrame,
    *,
    nombre: str,
    claves: Sequence[str],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    salida, metadata = unir_contexto_asof(
        transiciones,
        fuente,
        fecha_contexto="fecha_dato",
        claves_union=tuple(claves),
    )
    salida = salida.rename(
        columns={
            "fecha_contexto_asof": f"fecha_contexto_{nombre}",
            "nivel_contexto_asof": f"nivel_contexto_{nombre}",
        }
    )
    metadata = dict(metadata)
    metadata["nombre"] = nombre
    fechas = pd.to_datetime(fuente.fecha_dato, errors="coerce")
    metadata["fecha_maxima_fuente"] = (
        fechas.max().isoformat() if not fuente.empty and fechas.notna().any() else None
    )
    return salida, metadata


def _preparar_poda(poda: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    tabla = _normalizar_identidad(poda)
    tabla["fecha_dato"], columna_fecha = _fecha(
        tabla, ("fecha_inicio", "fecha_poda", "fecha_dato", "fecha")
    )
    # 1899-12-30 aparece como sustituto de vacío en algunas exportaciones Access.
    tabla.loc[tabla.fecha_dato.dt.year.lt(2000), "fecha_dato"] = pd.NaT
    columna_area = _alias(tabla, ("area_ha", "area", "AreaPoda"))
    tabla["area_ha"] = (
        _numero(tabla[columna_area])
        if columna_area is not None
        else pd.Series(np.nan, index=tabla.index)
    )
    validas = tabla.fecha_dato.notna() & tabla[list(_CLAVES_LOTE)].notna().all(axis=1)
    tabla = tabla.loc[validas].copy()
    if tabla.empty:
        return pd.DataFrame(columns=[*(_CLAVES_LOTE), "fecha_dato", "area_ha"]), {
            "filas_entrada": int(len(poda)),
            "filas_validas": 0,
            "columna_fecha": columna_fecha,
            "advertencias": ["poda_sin_fechas_o_identidad"],
        }
    dispersion = tabla.groupby(["campania", "modulo"], dropna=False)["fecha_dato"].transform(
        lambda serie: (serie.max() - serie.min()).days
    )
    tabla["poda_dispersion_dias"] = pd.to_numeric(dispersion, errors="coerce")
    # Una fuente de poda puede tener más de una carga para el mismo lote. La fecha
    # más reciente representa el ciclo vigente; se conserva el área máxima.
    tabla = (
        tabla.sort_values("fecha_dato", kind="stable")
        .groupby(list(_CLAVES_LOTE), as_index=False, dropna=False)
        .agg(
            fecha_dato=("fecha_dato", "last"),
            area_ha=("area_ha", "max"),
            poda_dispersion_dias=("poda_dispersion_dias", "max"),
        )
    )
    return tabla, {
        "filas_entrada": int(len(poda)),
        "filas_validas": int(len(tabla)),
        "columna_fecha": columna_fecha,
        "advertencias": [],
    }


def _preparar_clima(clima: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    tabla = clima.copy()
    tabla["fecha_dato"], columna_fecha = _fecha(
        tabla, ("fecha_dato", "fecha", "fecha_hora")
    )
    aliases = {
        "temp": ("temp", "temp_media", "temperatura"),
        "temp_max": ("temp_max", "temperatura_maxima", "temp max"),
        "temp_min": ("temp_min", "temperatura_minima", "temp min"),
        "humedad": ("humedad", "humedad_relativa", "rh"),
        "rad_sol": (
            "rad_sol",
            "radiacion",
            "radiacion_solar",
            "radiacionsolar",
            "rad",
        ),
        "et_mm": ("et_mm", "eto", "evapotranspiracion"),
        "lluvia": ("lluvia", "precipitacion"),
        "gdd_direct": ("gdd", "gdd_diario", "suma_de_gdd", "suma gdd"),
    }
    for canonico, nombres in aliases.items():
        columna = _alias(tabla, nombres)
        tabla[canonico] = _numero(tabla[columna]) if columna is not None else np.nan
    temp_estimado = (tabla["temp_max"] + tabla["temp_min"]) / 2.0
    tabla["temp"] = tabla["temp"].where(tabla["temp"].notna(), temp_estimado)
    tabla = tabla.loc[tabla.fecha_dato.notna()].copy()
    if tabla.empty:
        return pd.DataFrame(columns=["fecha_dato"]), {
            "filas_entrada": int(len(clima)),
            "filas_validas": 0,
            "columna_fecha": columna_fecha,
            "advertencias": ["clima_sin_fechas"],
        }
    diario = (
        tabla.groupby("fecha_dato", as_index=False)
        .agg(
            temp_media=("temp", "mean"),
            humedad=("humedad", "mean"),
            Rad=("rad_sol", "sum"),
            ETo=("et_mm", "sum"),
            lluvia=("lluvia", "sum"),
            gdd_direct=("gdd_direct", lambda serie: serie.sum(min_count=1)),
        )
        .sort_values("fecha_dato", kind="stable")
    )
    presion_saturacion = 0.6108 * np.exp(
        17.27 * diario.temp_media / (diario.temp_media + 237.3)
    )
    diario["DPV"] = (presion_saturacion * (1 - diario.humedad / 100)).clip(lower=0)
    gdd_calculado = (diario.temp_media - 4.4).clip(lower=0)
    diario["gdd_direct"] = diario["gdd_direct"].clip(lower=0)
    diario["gdd_diario"] = diario["gdd_direct"].where(
        diario["gdd_direct"].notna(), gdd_calculado
    )
    diario["gdd_acum_global"] = diario.gdd_diario.fillna(0).cumsum()
    diario["gdd_dias_global"] = diario.gdd_diario.notna().cumsum()
    diario["gdd_28d"] = (
        diario.set_index("fecha_dato")["gdd_diario"]
        .rolling("28D", closed="both")
        .sum()
        .to_numpy()
    )
    return diario, {
        "filas_entrada": int(len(clima)),
        "filas_validas": int(len(diario)),
        "columna_fecha": columna_fecha,
        "gdd_directo": bool(diario["gdd_direct"].notna().any()),
        "advertencias": [],
    }


def _preparar_flores(flores: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    tabla = _normalizar_identidad(flores)
    tabla["fecha_dato"], columna_fecha = _fecha(
        tabla, ("fecha_dato", "fecha", "promedio_de_fecha")
    )
    n_flores = _alias(
        tabla, ("n_flores", "flores", "nflores", "cantidad_flores")
    )
    cuajo = _alias(tabla, ("cuajo", "frutos_cuajados", "cuajado"))
    planta = _alias(tabla, ("planta", "planta_id", "id_planta"))
    dias_poda = _alias(tabla, ("dias_desde_poda", "dias_poda"))
    tabla["__flores"] = (
        _numero(tabla[n_flores]) if n_flores is not None else np.nan
    )
    tabla["__cuajo"] = _numero(tabla[cuajo]) if cuajo is not None else np.nan
    tabla["dias_desde_poda_excel"] = (
        _numero(tabla[dias_poda]) if dias_poda is not None else np.nan
    )
    tabla.loc[tabla["__cuajo"] < 0, "__cuajo"] = np.nan
    tabla["__planta"] = tabla[planta].astype("string") if planta is not None else pd.NA
    tiene_turno = tabla.turno.notna().any()
    tiene_lote = tabla.lote.notna().any()
    claves = ["modulo"]
    if tiene_turno:
        claves.append("turno")
    if tiene_lote:
        claves.append("lote")
    validas = tabla.fecha_dato.notna() & tabla.modulo.notna()
    if tiene_turno:
        validas &= tabla.turno.notna()
    if tiene_lote:
        validas &= tabla.lote.notna()
    tabla = tabla.loc[validas].copy()
    if tabla.empty:
        return pd.DataFrame(columns=["modulo", "lote", "fecha_dato"]), {
            "filas_entrada": int(len(flores)),
            "filas_validas": 0,
            "columna_fecha": columna_fecha,
            "advertencias": ["flores_sin_fechas_o_identidad"],
        }
    diario = (
        tabla.groupby([*claves, "fecha_dato"], as_index=False, dropna=False)
        .agg(
            __flores_total=("__flores", "sum"),
            __flores_media=("__flores", "mean"),
            __flores_sd=("__flores", "std"),
            __cuajo_total=("__cuajo", "sum"),
            plantas_muestreadas=("__planta", "nunique"),
            dias_desde_poda_excel=("dias_desde_poda_excel", "mean"),
        )
    )
    diario["flores_promedio"] = diario["__flores_total"] / diario.plantas_muestreadas.replace(
        0, np.nan
    )
    diario["flores_promedio"] = diario["flores_promedio"].fillna(diario["__flores_media"])
    diario["flores_dispersion_relativa"] = (
        diario["__flores_sd"] / diario["__flores_media"].abs().replace(0, np.nan)
    )
    diario.loc[
        diario["__flores_media"].notna() & diario["__flores_sd"].isna(),
        "flores_dispersion_relativa",
    ] = 0.0
    diario["tasa_cuajo"] = diario["__cuajo_total"] / diario["__flores_total"].replace(
        0, np.nan
    )
    return diario.drop(
        columns=["__flores_total", "__flores_media", "__flores_sd", "__cuajo_total"],
        errors="ignore",
    ), {
        "filas_entrada": int(len(flores)),
        "filas_validas": int(len(diario)),
        "columna_fecha": columna_fecha,
        "advertencias": [],
    }


def _preparar_estados(estados: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    tabla = _normalizar_identidad(estados)
    tabla["fecha_dato"], columna_fecha = _fecha(tabla, ("fecha_dato", "fecha"))
    for estado in ("e1", "e2", "e3", "e4", "e5"):
        columna = _alias(tabla, (estado, estado.upper()))
        tabla[estado] = _numero(tabla[columna]) if columna is not None else 0.0
    validas = tabla.fecha_dato.notna() & tabla.modulo.notna() & tabla.lote.notna()
    tabla = tabla.loc[validas].copy()
    if tabla.empty:
        return pd.DataFrame(columns=["modulo", "lote", "fecha_dato"]), {
            "filas_entrada": int(len(estados)),
            "filas_validas": 0,
            "columna_fecha": columna_fecha,
            "advertencias": ["estados_sin_fechas_o_identidad"],
        }
    diario = tabla.groupby(["modulo", "lote", "fecha_dato"], as_index=False, dropna=False)[
        ["e1", "e2", "e3", "e4", "e5"]
    ].sum(min_count=1)
    total = diario[["e1", "e2", "e3", "e4", "e5"]].sum(
        axis=1, min_count=1
    ).replace(0, np.nan)
    diario["indice_estado"] = sum(
        indice * diario[f"e{indice}"] for indice in range(1, 6)
    ) / total
    diario["prop_e45"] = (diario.e4 + diario.e5) / total
    return diario, {
        "filas_entrada": int(len(estados)),
        "filas_validas": int(len(diario)),
        "columna_fecha": columna_fecha,
        "advertencias": [],
    }


def _preparar_brotes(brotes: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    tabla = _normalizar_identidad(brotes)
    tabla["fecha_dato"], columna_fecha = _fecha(tabla, ("fecha_dato", "fecha"))
    brotes_columna = _alias(tabla, ("brotes", "brotes_total", "n_brotes"))
    planta = _alias(tabla, ("planta", "planta_id", "id_planta"))
    tabla["__brotes"] = (
        _numero(tabla[brotes_columna]) if brotes_columna is not None else np.nan
    )
    tabla["__planta"] = tabla[planta].astype("string") if planta is not None else pd.NA
    validas = tabla.fecha_dato.notna() & tabla.modulo.notna() & tabla.lote.notna()
    tabla = tabla.loc[validas].copy()
    if tabla.empty:
        return pd.DataFrame(columns=["modulo", "lote", "fecha_dato"]), {
            "filas_entrada": int(len(brotes)),
            "filas_validas": 0,
            "columna_fecha": columna_fecha,
            "advertencias": ["brotes_sin_fechas_o_identidad"],
        }
    diario = tabla.groupby(["modulo", "lote", "fecha_dato"], as_index=False, dropna=False).agg(
        brotes_total=("__brotes", "sum"),
        plantas_brotes=("__planta", "nunique"),
    )
    diario["brotes_por_planta"] = diario.brotes_total / diario.plantas_brotes.replace(
        0, np.nan
    )
    return diario, {
        "filas_entrada": int(len(brotes)),
        "filas_validas": int(len(diario)),
        "columna_fecha": columna_fecha,
        "advertencias": [],
    }


def _preparar_riego(riego: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    tabla = _normalizar_identidad(riego)
    tabla["fecha_dato"], columna_fecha = _fecha(tabla, ("fecha_dato", "fecha"))
    aliases = {
        "agua_m3": ("agua_m3", "riego_agua_m3", "m3"),
        "agua_ha": ("agua_ha", "agua/ha", "agua ha", "riego_agua_ha", "m3/ha", "m3ha"),
        "lt_planta_direct": (
            "lt_planta",
            "lt/planta",
            "litros_planta",
            "litros/planta",
        ),
        "lamina_mm": ("lamina_mm", "riego_lamina_mm", "lamina"),
        "reposicion_pct": ("reposicion_pct", "reposicion"),
        "area_ha": ("area_ha", "area"),
    }
    nombres_agua_ha = aliases["agua_ha"]
    columna_agua_ha = _alias(tabla, nombres_agua_ha)
    for canonico, nombres in aliases.items():
        columna = _alias(tabla, nombres)
        tabla[canonico] = _numero(tabla[columna]) if columna is not None else np.nan
    unidad_m3_ha_explicita = columna_agua_ha is not None and _nombre_columna(
        columna_agua_ha
    ) in {"m3ha", "riego_m3ha"}
    validas = tabla.fecha_dato.notna() & tabla.modulo.notna()
    tabla = tabla.loc[validas].copy()
    if tabla.empty:
        return pd.DataFrame(columns=["modulo", "fecha_dato"]), {
            "filas_entrada": int(len(riego)),
            "filas_validas": 0,
            "columna_fecha": columna_fecha,
            "advertencias": ["riego_sin_fechas_o_modulo"],
        }
    diario = tabla.groupby(["modulo", "fecha_dato"], as_index=False, dropna=False).agg(
        riego_agua_m3=("agua_m3", "sum"),
        riego_lamina_mm=("lamina_mm", "sum"),
            riego_reposicion_pct=("reposicion_pct", "mean"),
            riego_area_ha=("area_ha", "max"),
            riego_agua_ha=("agua_ha", lambda serie: serie.sum(min_count=1)),
            riego_lt_planta_direct=(
                "lt_planta_direct",
                lambda serie: serie.sum(min_count=1),
            ),
        )
    diario = diario.sort_values(["modulo", "fecha_dato"], kind="stable")
    partes = []
    for modulo, grupo in diario.groupby("modulo", sort=False, dropna=False):
        serie = grupo.set_index("fecha_dato").sort_index()
        rodante = serie.rolling("28D", closed="both").agg(
            {
                "riego_agua_m3": "sum",
                "riego_lamina_mm": "sum",
                "riego_reposicion_pct": "mean",
                "riego_agua_ha": "sum",
                "riego_lt_planta_direct": "sum",
            }
        ).reset_index()
        rodante["modulo"] = modulo
        for columna in ("riego_agua_ha", "riego_lt_planta_direct"):
            observaciones = serie[columna].rolling("28D", closed="both").count().to_numpy()
            rodante[columna] = rodante[columna].where(observaciones > 0)
        area = float(pd.to_numeric(grupo.riego_area_ha, errors="coerce").max())
        if unidad_m3_ha_explicita:
            rodante["riego_m3_ha"] = rodante["riego_agua_ha"]
        else:
            rodante["riego_m3_ha"] = (
                rodante.riego_agua_m3 / area
                if np.isfinite(area) and area > 0
                else np.nan
            )
        rodante["riego_lt_planta"] = rodante["riego_lt_planta_direct"]
        partes.append(rodante)
    salida = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    return salida, {
        "filas_entrada": int(len(riego)),
        "filas_validas": int(len(salida)),
        "columna_fecha": columna_fecha,
        "agua_ha_columna": columna_agua_ha,
        "agua_ha_unidad_m3_ha_explicita": unidad_m3_ha_explicita,
        "advertencias": [],
    }


def _preparar_cosecha(cosecha: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    tabla = _normalizar_identidad(cosecha)
    tabla["fecha_dato"], columna_fecha = _fecha(
        tabla, ("fecha_dato", "fecha", "fecha_cosecha")
    )
    kg = _alias(tabla, ("kg", "kilogramos", "real_kg", "volumen_kg"))
    tabla["kg"] = _numero(tabla[kg]) if kg is not None else np.nan
    validas = (
        tabla.fecha_dato.notna()
        & tabla["kg"].notna()
        & tabla[list(_CLAVES_LOTE)].notna().all(axis=1)
    )
    tabla = tabla.loc[validas].copy()
    if tabla.empty:
        return pd.DataFrame(columns=[*(_CLAVES_LOTE), "fecha_dato", "kg"]), {
            "filas_entrada": int(len(cosecha)),
            "filas_validas": 0,
            "columna_fecha": columna_fecha,
            "advertencias": ["cosecha_sin_fechas_identidad_o_kg"],
        }
    salida = tabla.groupby([*(_CLAVES_LOTE), "fecha_dato"], as_index=False, dropna=False).kg.sum()
    return salida, {
        "filas_entrada": int(len(cosecha)),
        "filas_validas": int(len(salida)),
        "columna_fecha": columna_fecha,
        "advertencias": [],
    }


def _cosecha_asof(
    transiciones: pd.DataFrame,
    cosecha: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Calcula cosecha acumulada y de las últimas cuatro semanas sin fuga."""

    salida = transiciones.copy()
    salida["kg_real_acumulado"] = np.nan
    salida["kg_ultimas_4_semanas_asof"] = np.nan
    salida["fecha_contexto_cosecha"] = pd.NaT
    salida["nivel_contexto_cosecha"] = "sin_contexto"
    if cosecha.empty:
        return salida, {
            "nombre": "cosecha",
            "filas": int(len(salida)),
            "filas_con_contexto": 0,
            "cobertura": 0.0,
            "claves_union": list(_CLAVES_LOTE),
            "features": ["kg_real_acumulado", "kg_ultimas_4_semanas_asof"],
            "fuga": False,
            "advertencias": ["cosecha_sin_datos"],
        }
    grupos = {}
    for clave, grupo in cosecha.groupby(list(_CLAVES_LOTE), sort=False, dropna=False):
        clave = clave if isinstance(clave, tuple) else (clave,)
        grupo = grupo.sort_values("fecha_dato", kind="stable")
        fechas = grupo.fecha_dato.to_numpy(dtype="datetime64[ns]")
        kilos = grupo.kg.to_numpy(dtype=float)
        grupos[tuple(str(valor) for valor in clave)] = (fechas, np.cumsum(kilos))
    fechas_emision = pd.to_datetime(
        salida.fecha_emision_actual, errors="coerce"
    ).dt.normalize()
    for indice, fila in salida.iterrows():
        clave = tuple(str(fila[valor]) for valor in _CLAVES_LOTE)
        datos = grupos.get(clave)
        corte = fechas_emision.loc[indice]
        if datos is None or pd.isna(corte):
            continue
        fechas, acumulado = datos
        posicion = int(
            np.searchsorted(fechas, np.datetime64(corte.value, "ns"), side="left")
        )
        if posicion <= 0:
            continue
        ultimo = float(acumulado[posicion - 1])
        salida.at[indice, "kg_real_acumulado"] = ultimo
        inicio = np.datetime64(
            (corte - pd.Timedelta(28, unit="D")).value,
            "ns",
        )
        inicio_posicion = int(np.searchsorted(fechas, inicio, side="left"))
        anterior = float(acumulado[inicio_posicion - 1]) if inicio_posicion > 0 else 0.0
        salida.at[indice, "kg_ultimas_4_semanas_asof"] = max(0.0, ultimo - anterior)
        salida.at[indice, "fecha_contexto_cosecha"] = pd.Timestamp(fechas[posicion - 1])
        salida.at[indice, "nivel_contexto_cosecha"] = "exacto"
    con_contexto = int(salida.fecha_contexto_cosecha.notna().sum())
    return salida, {
        "nombre": "cosecha",
        "filas": int(len(salida)),
        "filas_con_contexto": con_contexto,
        "cobertura": float(con_contexto / len(salida)) if len(salida) else 0.0,
        "claves_union": list(_CLAVES_LOTE),
        "features": ["kg_real_acumulado", "kg_ultimas_4_semanas_asof"],
        "fuga": False,
        "advertencias": [],
    }


def _asignar_gdd_desde_poda(
    transiciones: pd.DataFrame,
    clima: pd.DataFrame,
) -> pd.DataFrame:
    salida = transiciones.copy()
    if clima.empty or "gdd_acum_global" not in salida or "fecha_contexto_poda" not in salida:
        return salida
    fechas = clima.fecha_dato.to_numpy(dtype="datetime64[ns]")
    acumulado = clima.gdd_acum_global.to_numpy(dtype=float)
    dias = clima.gdd_dias_global.to_numpy(dtype=float)
    poda = pd.to_datetime(salida.fecha_contexto_poda, errors="coerce").to_numpy(
        dtype="datetime64[ns]"
    )
    posiciones = np.searchsorted(fechas, poda, side="right") - 1
    base_acumulado = np.full(len(salida), np.nan, dtype=float)
    base_dias = np.full(len(salida), np.nan, dtype=float)
    validas = (posiciones >= 0) & ~pd.isna(poda)
    base_acumulado[validas] = acumulado[posiciones[validas]]
    base_dias[validas] = dias[posiciones[validas]]
    corriente = pd.to_numeric(salida["gdd_acum_global"], errors="coerce").to_numpy(
        dtype=float
    )
    corriente_dias = pd.to_numeric(salida["gdd_dias_global"], errors="coerce").to_numpy(
        dtype=float
    )
    salida["gdd_acum_poda_obs"] = np.maximum(corriente - base_acumulado, 0.0)
    salida["gdd_semanas_poda_obs"] = np.maximum(
        (corriente_dias - base_dias) / 7.0, 0.0
    )
    return salida


def construir_contexto_oleadas_asof(
    transiciones: pd.DataFrame,
    *,
    poda: pd.DataFrame | None = None,
    clima: pd.DataFrame | None = None,
    flores: pd.DataFrame | None = None,
    estados: pd.DataFrame | None = None,
    brotes: pd.DataFrame | None = None,
    cosecha: pd.DataFrame | None = None,
    riego: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Construye contexto as-of para transiciones de parámetros o emisiones.

    transiciones requiere identidad campania + modulo + turno + lote y
    fecha_emision_actual. El fundo puede faltar en las fuentes agronómicas; se
    conserva para la salida, pero no se usa como llave de poda/H01 para evitar que
    nombres presupuestales distintos rompan una unión física segura.
    """

    if not isinstance(transiciones, pd.DataFrame):
        raise TypeError("transiciones debe ser un pandas.DataFrame")
    if transiciones.empty:
        raise ValueError("transiciones no puede estar vacío")
    salida = _normalizar_identidad(transiciones).reset_index(drop=True)
    if "fecha_emision_actual" not in salida:
        columna_emision = _alias(
            salida, ("fecha_emision_actual", "fecha_emision", "fecha_corte")
        )
        if columna_emision is None:
            raise ValueError("transiciones requiere fecha_emision_actual o fecha_emision")
        salida["fecha_emision_actual"] = salida[columna_emision]
    salida["fecha_emision_actual"] = pd.to_datetime(
        salida.fecha_emision_actual, errors="coerce"
    ).dt.normalize()
    if salida.fecha_emision_actual.isna().any():
        raise ValueError("transiciones contiene fechas de emisión inválidas")
    faltantes = [clave for clave in _CLAVES_LOTE if salida[clave].isna().any()]
    if faltantes:
        raise ValueError(
            "transiciones contiene identidad incompleta: " + ", ".join(faltantes)
        )

    manifiesto: dict[str, Any] = {
        "filas": int(len(salida)),
        "fecha_emision_min": salida.fecha_emision_actual.min().isoformat(),
        "fecha_emision_max": salida.fecha_emision_actual.max().isoformat(),
        "fuentes": {},
        "fuga": False,
        "advertencias": [],
    }

    poda_preparada = pd.DataFrame()
    if poda is not None:
        if not isinstance(poda, pd.DataFrame):
            raise TypeError("poda debe ser un DataFrame o None")
        poda_preparada, detalle = _preparar_poda(poda)
        manifiesto["fuentes"]["poda"] = detalle
        if not poda_preparada.empty:
            salida, unido = _unir_fuente(
                salida,
                poda_preparada,
                nombre="poda",
                claves=_claves_disponibles(
                    salida, poda_preparada, ("campania", "modulo", "turno", "lote")
                ),
            )
            salida["dias_desde_poda"] = (
                salida.fecha_emision_actual
                - pd.to_datetime(salida.fecha_contexto_poda)
            ).dt.days
            salida.loc[salida.dias_desde_poda.lt(0), "dias_desde_poda"] = np.nan
            manifiesto["fuentes"]["poda_union"] = unido
    if clima is not None:
        if not isinstance(clima, pd.DataFrame):
            raise TypeError("clima debe ser un DataFrame o None")
        clima_preparado, detalle = _preparar_clima(clima)
        manifiesto["fuentes"]["clima"] = detalle
        if not clima_preparado.empty:
            salida, unido = _unir_fuente(
                salida, clima_preparado, nombre="clima", claves=()
            )
            salida = _asignar_gdd_desde_poda(salida, clima_preparado)
            manifiesto["fuentes"]["clima_union"] = unido
    for nombre, tabla, preparador in (
        ("flores", flores, _preparar_flores),
        ("estados", estados, _preparar_estados),
        ("brotes", brotes, _preparar_brotes),
    ):
        if tabla is None:
            continue
        if not isinstance(tabla, pd.DataFrame):
            raise TypeError(f"{nombre} debe ser un DataFrame o None")
        preparada, detalle = preparador(tabla)
        manifiesto["fuentes"][nombre] = detalle
        if not preparada.empty:
            _validar_fuente_sin_campania(salida, preparada, nombre=nombre)
            salida, unido = _unir_fuente(
                salida,
                preparada,
                nombre=nombre,
                claves=_claves_disponibles(
                    salida, preparada, ("campania", "modulo", "turno", "lote")
                ),
            )
            if nombre == "flores" and "dias_desde_poda_excel" in salida:
                dias_excel = _numero(salida["dias_desde_poda_excel"])
                if "dias_desde_poda" not in salida:
                    salida["dias_desde_poda"] = dias_excel
                else:
                    salida["dias_desde_poda"] = _numero(
                        salida["dias_desde_poda"]
                    ).fillna(dias_excel)
            manifiesto["fuentes"][f"{nombre}_union"] = unido
    if riego is not None:
        if not isinstance(riego, pd.DataFrame):
            raise TypeError("riego debe ser un DataFrame o None")
        riego_preparado, detalle = _preparar_riego(riego)
        manifiesto["fuentes"]["riego"] = detalle
        if not riego_preparado.empty:
            _validar_fuente_sin_campania(salida, riego_preparado, nombre="riego")
            salida, unido = _unir_fuente(
                salida,
                riego_preparado,
                nombre="riego",
                claves=_claves_disponibles(
                    salida, riego_preparado, ("campania", "modulo", "turno", "lote")
                ),
            )
            area = next(
                (
                    _numero(salida[columna])
                    for columna in ("area_ha", "area", "Area")
                    if columna in salida
                ),
                pd.Series(np.nan, index=salida.index),
            )
            if "riego_agua_m3" in salida and salida["riego_agua_m3"].notna().any():
                derivado_m3_ha = salida["riego_agua_m3"] / area.replace(0, np.nan)
                if "riego_m3_ha" not in salida:
                    salida["riego_m3_ha"] = derivado_m3_ha
                else:
                    salida["riego_m3_ha"] = _numero(
                        salida["riego_m3_ha"]
                    ).fillna(derivado_m3_ha)
            if (
                "plantas" in salida
                and "riego_agua_m3" in salida
                and salida["riego_agua_m3"].notna().any()
            ):
                derivado_lt_planta = (
                    salida["riego_agua_m3"]
                    * 1000
                    / _numero(salida.plantas).replace(0, np.nan)
                )
                if "riego_lt_planta" not in salida:
                    salida["riego_lt_planta"] = derivado_lt_planta
                else:
                    salida["riego_lt_planta"] = _numero(
                        salida["riego_lt_planta"]
                    ).fillna(derivado_lt_planta)
            manifiesto["fuentes"]["riego_union"] = unido
    if cosecha is not None:
        if not isinstance(cosecha, pd.DataFrame):
            raise TypeError("cosecha debe ser un DataFrame o None")
        cosecha_preparada, detalle = _preparar_cosecha(cosecha)
        manifiesto["fuentes"]["cosecha"] = detalle
        salida, unido = _cosecha_asof(salida, cosecha_preparada)
        manifiesto["fuentes"]["cosecha_union"] = unido

    # Las features sin fuente se dejan explícitas como NaN para que la compuerta de
    # cobertura pueda demostrar por qué no aplicó una corrección.
    for feature in FEATURES_CONTEXTO_POR_DEFECTO:
        if feature not in salida:
            salida[feature] = np.nan
    cobertura = {
        feature: float(
            pd.to_numeric(salida[feature], errors="coerce").notna().mean()
        )
        for feature in FEATURES_CONTEXTO_POR_DEFECTO
    }
    manifiesto["cobertura_features"] = cobertura
    manifiesto["features_construidas"] = [
        feature for feature in FEATURES_CONTEXTO_POR_DEFECTO if cobertura[feature] > 0
    ]
    manifiesto["fuga"] = False
    return salida, manifiesto


def _clave_valor(valor: object) -> str:
    return "" if valor is None or pd.isna(valor) else str(valor).strip()


def construir_contexto_por_lote_oleadas_asof(
    lotes: pd.DataFrame,
    fecha_emision: object,
    *,
    poda: pd.DataFrame | None = None,
    clima: pd.DataFrame | None = None,
    flores: pd.DataFrame | None = None,
    estados: pd.DataFrame | None = None,
    brotes: pd.DataFrame | None = None,
    cosecha: pd.DataFrame | None = None,
    riego: pd.DataFrame | None = None,
) -> tuple[dict[tuple[str, ...], dict[str, float]], dict[str, Any]]:
    """Devuelve contexto_por_lote listo para la ruta automática sin Excel."""

    if not isinstance(lotes, pd.DataFrame) or lotes.empty:
        raise ValueError("lotes debe ser un DataFrame no vacío")
    base = _normalizar_identidad(lotes)
    base["fecha_emision_actual"] = pd.Timestamp(fecha_emision).normalize()
    tabla, manifiesto = construir_contexto_oleadas_asof(
        base,
        poda=poda,
        clima=clima,
        flores=flores,
        estados=estados,
        brotes=brotes,
        cosecha=cosecha,
        riego=riego,
    )
    mapa: dict[tuple[str, ...], dict[str, float]] = {}
    for _, fila in tabla.iterrows():
        clave = tuple(_clave_valor(fila[nombre]) for nombre in _CLAVES_COMPLETAS)
        if clave in mapa:
            raise ValueError(f"lotes repite la identidad canónica: {clave}")
        contexto: dict[str, float] = {}
        for feature in FEATURES_CONTEXTO_POR_DEFECTO:
            valor = pd.to_numeric(
                pd.Series([fila.get(feature)]), errors="coerce"
            ).iloc[0]
            if pd.notna(valor):
                contexto[feature] = float(valor)
        mapa[clave] = contexto
    manifiesto = dict(manifiesto)
    manifiesto["lotes"] = int(len(mapa))
    manifiesto["lotes_con_contexto"] = int(sum(bool(valor) for valor in mapa.values()))
    manifiesto["contexto_por_lote"] = mapa
    return mapa, manifiesto


__all__ = [
    "construir_contexto_oleadas_asof",
    "construir_contexto_por_lote_oleadas_asof",
]

"""Priors y calibración temporal del modelo híbrido legacy.

Este módulo contiene únicamente la construcción de parámetros as-of: normaliza
emisiones, indexa las fuentes de calibración, busca historia del mismo lote o de
grupos agronómicos y ejecuta el calibrador Bhattacharya. No conoce el panel
fenológico ni el ajuste residual, por lo que puede probarse y evolucionar de forma
independiente.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from ...nucleo.bhattacharya import ParametrosBhattacharya, ajustar_lote_automatico


@dataclass(frozen=True)
class ParametroLegacyAsOf:
    """Parámetros legacy y su procedencia para una combinación lote-emisión."""

    parametros: ParametrosBhattacharya
    fuente: str
    n_observaciones: int
    fecha_pivote: pd.Timestamp


def _normalizar_emisiones(
    emisiones: pd.DataFrame,
    campania: str | None = None,
) -> pd.DataFrame:
    if emisiones.empty:
        return pd.DataFrame(columns=["campania", "fecha_emision"])
    salida = emisiones.copy()
    if "campania" not in salida:
        salida["campania"] = campania
    if campania is not None:
        salida["campania"] = salida.campania.fillna(campania).astype(str)
        salida = salida[salida.campania.eq(str(campania))].copy()
    else:
        salida["campania"] = salida.campania.astype(str)
    salida["fecha_emision"] = pd.to_datetime(salida.fecha_emision, errors="coerce").dt.normalize()
    return salida.dropna(subset=["fecha_emision", "campania"]).drop_duplicates(
        ["campania", "fecha_emision"]
    )


def _campania_defecto(datos) -> str:
    for tabla in (datos.cosecha, datos.poda, datos.forecast):
        if not tabla.empty and "campania" in tabla:
            valores = tabla.campania.dropna().astype(str)
            if not valores.empty:
                return sorted(valores.unique())[-1]
    return "C2026"


def _campania_anterior(campania: str) -> str | None:
    texto = str(campania).strip().upper()
    if not texto.startswith("C") or not texto[1:].isdigit():
        return None
    return f"C{int(texto[1:]) - 1}"


def _arrays_calibracion(
    historia: pd.DataFrame,
    *,
    fecha_poda: pd.Timestamp,
    plantas: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Expresa una historia de cosecha en días, frutos/planta y peso.

    El contrato de ``DatosProyeccion`` conserva kg y peso por lote-campaña. Esta
    conversión es la misma que utiliza el calibrador operativo de PostgreSQL y evita
    confundir kilos observados con la carga total de frutos de la campaña.
    """

    if historia.empty:
        vacio = np.array([], dtype=float)
        return vacio, vacio, vacio
    fechas = pd.to_datetime(historia.fecha, errors="coerce")
    kg = pd.to_numeric(historia.kg, errors="coerce")
    peso = pd.to_numeric(historia.peso_baya, errors="coerce")
    validos = fechas.notna() & kg.ge(0) & peso.gt(0)
    if not validos.any():
        vacio = np.array([], dtype=float)
        return vacio, vacio, vacio
    t_dias = (fechas[validos] - fecha_poda).dt.days.to_numpy(float)
    pesos = peso[validos].to_numpy(float)
    frutos = (kg[validos] * 1000.0 / (peso[validos] * plantas)).to_numpy(float)
    return t_dias, frutos, pesos


def _prior_historico_lote(
    datos,
    campania: str,
    lote_id: Any,
    plantas: float,
) -> ParametrosBhattacharya | None:
    """Calibra una vez el histórico cerrado del mismo lote como prior biológico."""

    anterior = _campania_anterior(campania)
    if anterior is None:
        return None
    cache = getattr(datos, "_legacy_prior_lote_cache", None)
    if cache is None:
        cache = {}
        datos._legacy_prior_lote_cache = cache
    clave = (anterior, str(lote_id))
    if clave in cache:
        return cache[clave]

    indices = _legacy_input_cache(datos)
    historia = indices["cosecha"].get(clave)
    if historia is None or historia.empty:
        cache[clave] = None
        return None
    fecha_poda = indices["poda"].get(clave)
    if fecha_poda is None:
        fecha_poda = _fecha_poda(datos, anterior, lote_id, historia)
    t_dias, frutos, pesos = _arrays_calibracion(
        historia,
        fecha_poda=fecha_poda,
        plantas=plantas,
    )
    fila = historia.iloc[0]
    parametro = ajustar_lote_automatico(
        t_dias=t_dias,
        frutos_obs=frutos,
        peso_obs=pesos,
        lote_id=str(lote_id),
        lote=str(fila.get("lote", lote_id)),
        campania=anterior,
        fundo=str(fila.get("fundo", "")),
        modulo=str(fila.get("modulo", "")),
        turno=str(fila.get("turno", "")),
        fecha_poda=fecha_poda,
        n_plantas=int(round(plantas)),
    )
    cache[clave] = parametro
    return parametro


def _metadatos_lotes(datos) -> pd.DataFrame:
    """Devuelve la identidad agronómica disponible para construir priors grupales.

    Los libros pueden repetir el código comercial del lote entre módulos. Por eso la
    jerarquía nunca usa ``lote`` como clave aislada; primero intenta resolver el lote
    físico y después conserva módulo, fundo y variedad como niveles de respaldo.
    """

    cache = getattr(datos, "_legacy_metadata_cache", None)
    if cache is not None:
        return cache
    lotes = getattr(datos, "lotes", pd.DataFrame())
    if lotes is None or lotes.empty or "lote_id" not in lotes:
        cache = pd.DataFrame(columns=["lote_id", "fundo", "modulo", "variedad"])
    else:
        columnas = [c for c in ("lote_id", "fundo", "modulo", "variedad", "turno") if c in lotes]
        cache = lotes[columnas].copy().drop_duplicates("lote_id")
        for columna in ("fundo", "modulo", "variedad", "turno"):
            if columna not in cache:
                cache[columna] = ""
        cache["_lote_key"] = cache.lote_id.astype(str)
    datos._legacy_metadata_cache = cache
    return cache


def _identidad_lote(datos, lote_id: Any) -> dict[str, str]:
    metadata = _metadatos_lotes(datos)
    if metadata.empty:
        return {c: "" for c in ("fundo", "modulo", "variedad")}
    filas = metadata[metadata["_lote_key"].eq(str(lote_id))]
    if filas.empty:
        return {c: "" for c in ("fundo", "modulo", "variedad")}
    fila = filas.iloc[0]
    return {c: str(fila.get(c, "") or "").strip() for c in ("fundo", "modulo", "variedad")}


def _prior_grupal_historico(
    datos,
    campania: str,
    lote_id: Any,
    plantas: float,
    fecha_emision: pd.Timestamp,
) -> tuple[ParametrosBhattacharya | None, str]:
    """Construye el primer prior disponible por la jerarquía agronómica.

    El prior solo usa cosecha anterior al corte. Se prefieren observaciones del mismo
    módulo, luego fundo+variedad, variedad y finalmente el conjunto histórico global.
    Es un prior de regularización, no una sustitución silenciosa de la historia del
    lote: su nivel queda guardado en ``nivel_calibracion``.
    """

    cache = getattr(datos, "_legacy_prior_grupo_cache", None)
    if cache is None:
        cache = {}
        datos._legacy_prior_grupo_cache = cache
    identidad = _identidad_lote(datos, lote_id)
    niveles = [
        ("modulo_historico", (identidad.get("fundo", ""), identidad.get("modulo", ""), "")),
        (
            "fundo_variedad_historica",
            (identidad.get("fundo", ""), "", identidad.get("variedad", "")),
        ),
        ("variedad_historica", ("", "", identidad.get("variedad", ""))),
        ("global_historico", ("", "", "")),
    ]
    cosecha = getattr(datos, "cosecha", pd.DataFrame())
    if cosecha is None or cosecha.empty:
        return None, "sin_prior_grupal"
    requeridas = {"lote_id", "fecha", "kg", "peso_baya"}
    if not requeridas <= set(cosecha):
        return None, "sin_prior_grupal"
    tabla = cosecha.copy()
    tabla["_fecha"] = pd.to_datetime(tabla.fecha, errors="coerce").dt.normalize()
    tabla["_lote_key"] = tabla.lote_id.astype(str)
    tabla = tabla[tabla["_fecha"].lt(pd.Timestamp(fecha_emision).normalize())].copy()
    if tabla.empty:
        return None, "sin_prior_grupal"
    metadata = _metadatos_lotes(datos)
    if not metadata.empty:
        tabla = tabla.merge(
            metadata[["_lote_key", "fundo", "modulo", "variedad"]],
            on="_lote_key",
            how="left",
            suffixes=("", "_maestro"),
        )
    for columna in ("fundo", "modulo", "variedad"):
        if columna not in tabla:
            tabla[columna] = ""
        tabla[columna] = tabla[columna].fillna("").astype(str).str.strip()

    def _clave(valor: object) -> str:
        return str(valor or "").casefold().strip()

    for nivel, (fundo, modulo, variedad) in niveles:
        llave = (
            str(campania),
            str(lote_id),
            pd.Timestamp(fecha_emision).date(),
            nivel,
            fundo,
            modulo,
            variedad,
        )
        if llave in cache:
            return cache[llave], nivel
        parte = tabla.copy()
        if fundo:
            parte = parte[parte.fundo.map(_clave).eq(_clave(fundo))]
        if modulo:
            parte = parte[parte.modulo.map(_clave).eq(_clave(modulo))]
        if variedad:
            parte = parte[parte.variedad.map(_clave).eq(_clave(variedad))]
        # Un prior grupal debe tener más señal que un único registro. La campaña
        # actual puede aportar historia cerrada, pero no puede aportar el futuro.
        parte = parte.dropna(subset=["_fecha", "kg", "peso_baya"])
        if len(parte) < 4 or parte["_lote_key"].nunique() < 2:
            continue
        plantas_grupo = float(plantas) if np.isfinite(plantas) and plantas > 0 else 5000.0
        if "plantas_maestro" in parte:
            valores = pd.to_numeric(parte.plantas_maestro, errors="coerce").dropna()
            if not valores.empty:
                plantas_grupo = float(valores.median())
        poda_grupo = pd.Timestamp(fecha_emision).normalize() - pd.Timedelta(days=220)
        fechas = parte["_fecha"]
        kg = pd.to_numeric(parte.kg, errors="coerce")
        peso = pd.to_numeric(parte.peso_baya, errors="coerce")
        validos = fechas.notna() & kg.ge(0) & peso.gt(0)
        if int(validos.sum()) < 4:
            continue
        t_dias = (fechas[validos] - poda_grupo).dt.days.to_numpy(float)
        frutos = (kg[validos] * 1000.0 / (peso[validos] * plantas_grupo)).to_numpy(float)
        pesos = peso[validos].to_numpy(float)
        parametro = ajustar_lote_automatico(
            t_dias=t_dias,
            frutos_obs=frutos,
            peso_obs=pesos,
            lote=f"PRIOR_{nivel}",
            lote_id=f"PRIOR_{nivel}",
            campania=str(campania),
            fundo=fundo,
            modulo=modulo,
            fecha_poda=poda_grupo,
            n_plantas=int(round(plantas_grupo)),
        )
        parametro.fuente_parametros = "postgres_prior_grupal_asof"
        parametro.nivel_calibracion = nivel
        cache[llave] = parametro
        return parametro, nivel
    return None, "sin_prior_grupal"


def _fecha_poda(datos, campania: str, lote_id: Any, historia: pd.DataFrame) -> pd.Timestamp:
    poda = datos.poda
    if not poda.empty and {"campania", "lote_id", "fecha_inicio"} <= set(poda):
        filas = poda[poda.campania.astype(str).eq(str(campania)) & poda.lote_id.eq(lote_id)]
        if not filas.empty:
            fecha = pd.to_datetime(filas.fecha_inicio, errors="coerce").dropna()
            if not fecha.empty:
                return pd.Timestamp(fecha.min()).normalize()
    if not historia.empty:
        primera = pd.to_datetime(historia.fecha, errors="coerce").dropna().min()
        if pd.notna(primera):
            # Fallback explícito: solo fija el origen temporal cuando la tabla de poda no
            # tiene cobertura. La procedencia queda registrada como estimada.
            return pd.Timestamp(primera).normalize() - pd.Timedelta(days=220)
    return pd.Timestamp("2025-12-29")


def _legacy_input_cache(datos) -> dict[str, Any]:
    """Indexa las fuentes de calibración una sola vez por snapshot en memoria."""

    cache = getattr(datos, "_legacy_input_cache", None)
    if cache is not None:
        return cache

    cosecha_por_lote: dict[tuple[str, str], pd.DataFrame] = {}
    cosecha = datos.cosecha
    requeridas = {"lote_id", "campania", "fecha", "kg", "peso_baya"}
    if not cosecha.empty and requeridas <= set(cosecha):
        tabla = cosecha.copy()
        tabla["_campania_key"] = tabla.campania.astype(str)
        tabla["_lote_key"] = tabla.lote_id.astype(str)
        for claves, grupo in tabla.groupby(["_campania_key", "_lote_key"], dropna=False):
            cosecha_por_lote[(str(claves[0]), str(claves[1]))] = grupo.drop(
                columns=["_campania_key", "_lote_key"]
            )

    poda_por_lote: dict[tuple[str, str], pd.Timestamp] = {}
    poda = datos.poda
    if not poda.empty and {"campania", "lote_id", "fecha_inicio"} <= set(poda):
        tabla = poda.copy()
        tabla["_campania_key"] = tabla.campania.astype(str)
        tabla["_lote_key"] = tabla.lote_id.astype(str)
        tabla["_fecha"] = pd.to_datetime(tabla.fecha_inicio, errors="coerce")
        for claves, grupo in tabla.groupby(["_campania_key", "_lote_key"], dropna=False):
            fechas = grupo["_fecha"].dropna()
            if not fechas.empty:
                poda_por_lote[(str(claves[0]), str(claves[1]))] = fechas.min().normalize()

    plantas_por_lote: dict[str, float] = {}
    lotes = datos.lotes
    if not lotes.empty and {"lote_id", "n_plantas"} <= set(lotes):
        tabla = lotes.copy()
        tabla["_lote_key"] = tabla.lote_id.astype(str)
        tabla["_plantas"] = pd.to_numeric(tabla.n_plantas, errors="coerce")
        plantas_por_lote = (
            tabla.dropna(subset=["_plantas"]).groupby("_lote_key")["_plantas"].median().to_dict()
        )

    cache = {
        "cosecha": cosecha_por_lote,
        "poda": poda_por_lote,
        "plantas": plantas_por_lote,
    }
    datos._legacy_input_cache = cache
    return cache


def calibrar_parametros_legacy_asof(
    datos,
    campania: str,
    lote_id: Any,
    fecha_emision,
    *,
    inicial: ParametrosBhattacharya | None = None,
) -> ParametroLegacyAsOf:
    """Calibra la curva legacy solo con cosecha anterior a la emisión.

    Las cantidades observadas se expresan en frutos/planta para que el producto final no
    multiplique dos veces por las plantas del lote. Si no hay historia suficiente, el
    calibrador devuelve sus priors explícitos y marca la fuente como estimada.
    """

    fecha_emision = pd.Timestamp(fecha_emision).normalize()
    cache = getattr(datos, "_legacy_parametros_cache", None)
    if cache is None:
        cache = {}
        datos._legacy_parametros_cache = cache
    # Un mismo corte puede calcularse primero para MacroLegacy sin prior Excel y
    # después para el challenger con un libro histórico. La procedencia del prior
    # forma parte de la función; si no entra en la clave, el primer resultado
    # contaminaba silenciosamente la segunda corrida desde el cache.
    firma_inicial = None
    if inicial is not None:
        firma_inicial = tuple(
            round(float(getattr(inicial, campo)), 8)
            for campo in (
                "mu1",
                "sigma1",
                "N1",
                "mu2",
                "sigma2",
                "N2",
                "mu3",
                "sigma3",
                "N3",
                "peso_a",
                "peso_b",
            )
        )
    clave_cache = (str(campania), str(lote_id), str(fecha_emision.date()), firma_inicial)
    if clave_cache in cache:
        return cache[clave_cache]

    indices = _legacy_input_cache(datos)
    historia_base = indices["cosecha"].get((str(campania), str(lote_id)))
    if historia_base is None:
        historia = pd.DataFrame()
    else:
        fechas_historia = pd.to_datetime(historia_base.fecha, errors="coerce")
        historia = historia_base.loc[fechas_historia.lt(fecha_emision)].copy()

    fecha_poda = indices["poda"].get((str(campania), str(lote_id)))
    if fecha_poda is None:
        fecha_poda = _fecha_poda(datos, campania, lote_id, historia)
    plantas = np.nan
    if not historia.empty and "plantas_maestro" in historia:
        plantas = pd.to_numeric(historia.plantas_maestro, errors="coerce").dropna().median()
    if not np.isfinite(plantas) or plantas <= 0:
        plantas = indices["plantas"].get(str(lote_id), np.nan)
    plantas = float(plantas) if np.isfinite(plantas) and plantas > 0 else 5000.0

    t_dias, frutos, pesos = _arrays_calibracion(
        historia,
        fecha_poda=fecha_poda,
        plantas=plantas,
    )
    prior = _prior_historico_lote(datos, str(campania), lote_id, plantas)
    nivel_prior = "historico_lote"
    if prior is None:
        prior, nivel_prior = _prior_grupal_historico(
            datos,
            str(campania),
            lote_id,
            plantas,
            fecha_emision,
        )
    fila = historia.iloc[0] if not historia.empty else pd.Series(dtype=object)
    parametros = ajustar_lote_automatico(
        t_dias=t_dias,
        frutos_obs=frutos,
        peso_obs=pesos if len(pesos) else None,
        prior=prior,
        inicial=inicial,
        lote_id=str(lote_id),
        lote=str(fila.get("lote", lote_id)),
        campania=str(campania),
        fundo=str(fila.get("fundo", "")),
        modulo=str(fila.get("modulo", "")),
        turno=str(fila.get("turno", "")),
        fecha_poda=fecha_poda,
        n_plantas=int(round(plantas)),
    )
    if len(frutos):
        fuente = "postgres_auto_asof_con_historico" if prior is not None else "postgres_auto_asof"
    elif prior is not None:
        fuente = (
            "historico_lote_sin_actual"
            if nivel_prior == "historico_lote"
            else "postgres_prior_grupal_asof"
        )
    else:
        fuente = "prior_legacy_sin_historia"
    if len(historia):
        if nivel_prior == "historico_lote":
            nivel_resultado = "lote_actual_con_historico"
        elif prior is not None:
            nivel_resultado = f"lote_actual_con_{nivel_prior}"
        else:
            nivel_resultado = "lote_actual"
    elif prior is not None:
        nivel_resultado = nivel_prior
    else:
        nivel_resultado = "prior_legacy_sin_historia"
    parametros.nivel_calibracion = nivel_resultado
    parametros.fuente_parametros = fuente
    n_asof = max(len(historia), int(getattr(prior, "panas_observadas", 0) or 0))
    resultado = ParametroLegacyAsOf(parametros, fuente, n_asof, fecha_poda)
    cache[clave_cache] = resultado
    return resultado


__all__ = [
    "ParametroLegacyAsOf",
    "calibrar_parametros_legacy_asof",
    "_arrays_calibracion",
    "_campania_anterior",
    "_campania_defecto",
    "_fecha_poda",
    "_identidad_lote",
    "_legacy_input_cache",
    "_metadatos_lotes",
    "_normalizar_emisiones",
    "_prior_grupal_historico",
    "_prior_historico_lote",
]

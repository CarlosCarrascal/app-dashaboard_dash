"""Orquestación candidate-only de parámetros manuales y oleadas as-of.

Este módulo conecta dos piezas que antes se evaluaban por separado:

1. ``CandidateParamDelta`` aprende deltas de la fila Excel anterior; y
2. ``oleadas_asof`` conserva la fórmula Gaussian/exponencial y la ajusta con la
   cosecha estrictamente anterior al corte.

No publica, no persiste y no conoce R09. Es una frontera experimental para poder
comparar el proceso manual, el ajuste estructural y sus explicaciones con el mismo
horizonte de seis semanas.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pandas as pd

from analitica.dominio.modelos.hibrido import (
    MacroParams,
    ajustar_oleadas_asof,
    construir_prior_automatico,
    parametros_desde_fila,
    proyectar_oleadas_horizonte,
)

from .candidate_param_delta import CandidateParamDelta
from .contexto_oleadas import ModeloContextoOleadas

NOMBRE_MODELO = "HibridoOleadasAsOf_v1"
VERSION_MODELO = "excel_delta_gaussian_waves_asof_h6_v1"
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
PARAMETROS_MANUAL = (*PARAMETROS_CURVA, "%Caida")


def _factor_carga(fila: Mapping[str, Any]) -> float | None:
    for nombre in ("multiplicador_carga", "factor_caida", "Caida", "%Caida", "caida"):
        if nombre not in fila:
            continue
        try:
            valor = float(fila[nombre])
        except (TypeError, ValueError):
            continue
        if not math.isfinite(valor):
            continue
        if 1.0 < valor <= 100.0:
            valor /= 100.0
        return max(0.0, min(1.0, valor))
    return None


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


def _reemplazar_parametros_desde_mapping(
    parametros: MacroParams,
    valores: Mapping[str, Any],
) -> MacroParams:
    campos = {
        "X1": "ola_1_media_dias",
        "O1": "ola_1_desvio_dias",
        "N1": "ola_1_multiplicador",
        "X2": "ola_2_media_dias",
        "O2": "ola_2_desvio_dias",
        "N2": "ola_2_multiplicador",
        "X3": "ola_3_media_dias",
        "O3": "ola_3_desvio_dias",
        "N3": "ola_3_multiplicador",
        "A1": "peso_1_base_g",
        "B1": "peso_1_tasa",
        "A2": "peso_2_base_g",
        "B2": "peso_2_tasa",
        "A3": "peso_3_base_g",
        "B3": "peso_3_tasa",
    }
    cambios = {
        destino: float(valores[nombre])
        for nombre, destino in campos.items()
        if nombre in valores and valores[nombre] is not None
    }
    return replace(parametros, **cambios)


def proyectar_candidato_oleadas(
    fila_manual: Mapping[str, Any] | pd.Series,
    fecha_emision: object,
    *,
    modelo_deltas: CandidateParamDelta | None = None,
    modelo_contexto: ModeloContextoOleadas | None = None,
    contexto: Mapping[str, Any] | None = None,
    observaciones: pd.DataFrame | None = None,
    fecha_corte: object | None = None,
    semanas: int = 6,
    ventanas: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Ejecuta el candidato completo sobre una fila ``Parametros``.

    ``modelo_deltas`` es opcional para permitir una comparación contra el Excel
    congelado. Cuando se entrega, solo modifica los parámetros de curva que el
    candidato aprendió as-of. ``observaciones`` permite refinar esas curvas con
    cosecha y peso; por defecto el corte es la fecha de emisión, por lo que una
    observación de la semana actual no entra accidentalmente.
    """

    fila = dict(fila_manual)
    previos = {nombre: fila.get(nombre) for nombre in PARAMETROS_MANUAL}
    detalle_delta: dict[str, Any] = {}
    nivel_delta = "sin_delta_parametros"
    n_delta = 0
    if modelo_deltas is not None:
        resultado_delta = modelo_deltas.predict(previos, contexto or {})
        finales = resultado_delta["parametros"]
        fila.update({nombre: finales[nombre] for nombre in PARAMETROS_CURVA if nombre in finales})
        if "%Caida" in finales:
            fila["multiplicador_carga"] = finales["%Caida"]
        detalle_delta = dict(resultado_delta.get("detalle_calibracion", {}))
        nivel_delta = str(resultado_delta.get("nivel_calibracion", nivel_delta))
        n_delta = int(resultado_delta.get("n_observaciones", 0))

    detalle_contexto: dict[str, Any] = {}
    nivel_contexto = "sin_contexto_continuo"
    n_contexto = 0
    if modelo_contexto is not None:
        resultado_contexto = modelo_contexto.predict(fila, contexto or {})
        finales_contexto = resultado_contexto["parametros"]
        fila.update(
            {
                nombre: finales_contexto[nombre]
                for nombre in PARAMETROS_CURVA
                if nombre in finales_contexto
            }
        )
        detalle_contexto = dict(resultado_contexto.get("detalle_calibracion", {}))
        nivel_contexto = str(
            resultado_contexto.get("nivel_calibracion", nivel_contexto)
        )
        n_contexto = int(resultado_contexto.get("n_observaciones", 0))

    factor_carga = _factor_carga(fila)
    if factor_carga is not None:
        fila["multiplicador_carga"] = factor_carga
    parametros = parametros_desde_fila(fila)
    ajuste = None
    if observaciones is not None:
        corte = fecha_emision if fecha_corte is None else fecha_corte
        ajuste = ajustar_oleadas_asof(
            parametros,
            observaciones,
            fecha_corte=corte,
        )
        parametros = ajuste.parametros

    salida = proyectar_oleadas_horizonte(
        parametros,
        fecha_emision,
        semanas=semanas,
        ventanas=ventanas,
    )
    fuente = "excel_congelado"
    if modelo_deltas is not None:
        fuente = "excel_delta_asof"
    if ajuste is not None:
        fuente = f"{fuente}+ajuste_oleadas_asof"
    salida["modelo"] = NOMBRE_MODELO
    salida["version_fuente"] = VERSION_MODELO
    salida["fuente_parametros"] = fuente
    salida["nivel_delta_parametros"] = nivel_delta
    salida["n_transiciones_delta"] = n_delta
    salida["n_observaciones_oleadas_asof"] = ajuste.n_observaciones if ajuste else 0
    salida["componentes"] = [
        {
            "modelo": NOMBRE_MODELO,
            "formula": "X/O/N gaussianos por oleada + A/B exponencial + plantas / 1000",
            "fuente_parametros": fuente,
            "horizonte": "H1-H6",
            "ajuste_delta": detalle_delta,
            "ajuste_contexto": detalle_contexto,
            "ajuste_oleadas": ajuste.to_dict() if ajuste else None,
            "etiqueta_causal": False,
            "limitacion": (
                "Las contribuciones de parámetros son mecánicas; las variables "
                "agronómicas no se pueden llamar causas sin intervención experimental."
            ),
        }
        for _ in range(len(salida))
    ]
    metadata: dict[str, Any] = {
        "modelo": NOMBRE_MODELO,
        "version": VERSION_MODELO,
        "fuente_parametros": fuente,
        "nivel_delta_parametros": nivel_delta,
        "n_transiciones_delta": n_delta,
        "detalle_delta": detalle_delta,
        "detalle_contexto": detalle_contexto,
        "nivel_contexto": nivel_contexto,
        "n_observaciones_contexto": n_contexto,
        "ajuste_oleadas": ajuste.to_dict() if ajuste else None,
        "publicable": False,
    }
    return salida, metadata


def proyectar_automatico_oleadas(
    fecha_emision: object,
    *,
    fecha_pivote: object,
    plantas: float,
    area_ha: float = 1.0,
    prior_historico: MacroParams | None = None,
    modelo_contexto: ModeloContextoOleadas | None = None,
    contexto: Mapping[str, Any] | None = None,
    observaciones: pd.DataFrame | None = None,
    fecha_corte: object | None = None,
    multiplicador_carga: float | None = None,
    semanas: int = 6,
    ventanas: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Proyecta H1–H6 sin una fila de Excel.

    La fecha de poda y el universo físico son los únicos datos estructurales
    obligatorios. La historia es opcional: cuando existe, se filtra estrictamente
    antes de ``fecha_corte`` (la emisión por defecto) y ajusta las tres oleadas.
    """

    corte = fecha_emision if fecha_corte is None else fecha_corte
    ajuste = construir_prior_automatico(
        fecha_pivote=fecha_pivote,
        plantas=plantas,
        area_ha=area_ha,
        prior=prior_historico,
        observaciones=observaciones,
        fecha_corte=corte if observaciones is not None else None,
        multiplicador_carga=multiplicador_carga,
    )
    detalle_contexto: dict[str, Any] = {}
    nivel_contexto = "sin_contexto_continuo"
    if modelo_contexto is not None:
        resultado_contexto = modelo_contexto.predict(
            _parametros_a_mapping(ajuste.parametros), contexto or {}
        )
        ajuste = replace(
            ajuste,
            parametros=_reemplazar_parametros_desde_mapping(
                ajuste.parametros, resultado_contexto["parametros"]
            ),
        )
        detalle_contexto = dict(resultado_contexto.get("detalle_calibracion", {}))
        nivel_contexto = str(
            resultado_contexto.get("nivel_calibracion", nivel_contexto)
        )
    salida = proyectar_oleadas_horizonte(
        ajuste.parametros,
        fecha_emision,
        semanas=semanas,
        ventanas=ventanas,
    )
    fuente = "prior_automatico_oleadas_asof"
    salida["modelo"] = NOMBRE_MODELO
    salida["version_fuente"] = VERSION_MODELO
    salida["fuente_parametros"] = fuente
    salida["n_observaciones_oleadas_asof"] = ajuste.n_observaciones
    salida["componentes"] = [
        {
            "modelo": NOMBRE_MODELO,
            "formula": "prior automático + tres oleadas Gaussian + peso exponencial",
            "fuente_parametros": fuente,
            "horizonte": f"H1-H{semanas}",
            "ajuste_oleadas": ajuste.to_dict(),
            "ajuste_contexto": detalle_contexto,
            "etiqueta_causal": False,
        }
        for _ in range(len(salida))
    ]
    metadata: dict[str, Any] = {
        "modelo": NOMBRE_MODELO,
        "version": VERSION_MODELO,
        "fuente_parametros": fuente,
        "ajuste_oleadas": ajuste.to_dict(),
        "detalle_contexto": detalle_contexto,
        "nivel_contexto": nivel_contexto,
        "publicable": False,
    }
    return salida, metadata


_CLAVES_UNIVERSO = ("campania", "fundo", "modulo", "turno", "lote")
_CLAVES_HISTORIA_UNIVERSO = ("campania", "modulo", "turno", "lote")
_ALIAS_IDENTIDAD_UNIVERSO = {
    "campania": ("campania", "campaña", "campana"),
    "fundo": ("fundo", "fundo_ppto", "fundo_operativo"),
    "modulo": ("modulo", "módulo", "modulo_id"),
    "turno": ("turno", "turno_id"),
    "lote": ("lote", "lote_id", "lote_codigo"),
}


def _columna_alias(tabla: pd.DataFrame, nombres: tuple[str, ...]) -> str | None:
    indice = {str(columna).strip().casefold(): columna for columna in tabla.columns}
    for nombre in nombres:
        columna = indice.get(nombre.casefold())
        if columna is not None:
            return str(columna)
    return None


def _canonizar_identidad_universo(tabla: pd.DataFrame) -> pd.DataFrame:
    salida = tabla.copy()
    for clave, aliases in _ALIAS_IDENTIDAD_UNIVERSO.items():
        columna = _columna_alias(salida, aliases)
        if columna is None:
            salida[clave] = ""
        elif columna != clave:
            salida[clave] = salida[columna]
        salida[clave] = salida[clave].map(
            lambda valor: "" if valor is None or pd.isna(valor) else str(valor).strip()
        )
    return salida


def _clave_universo(fila: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(fila.get(clave, "")).strip() for clave in _CLAVES_UNIVERSO)


def _valor_numerico_alias(fila: Mapping[str, Any], nombres: tuple[str, ...]) -> float:
    for nombre in nombres:
        if nombre not in fila:
            continue
        valor = pd.to_numeric(pd.Series([fila[nombre]]), errors="coerce").iloc[0]
        if pd.notna(valor):
            return float(valor)
    return float("nan")


def _valor_fecha_alias(fila: Mapping[str, Any], nombres: tuple[str, ...]) -> pd.Timestamp:
    for nombre in nombres:
        if nombre not in fila:
            continue
        valor = pd.to_datetime(fila[nombre], errors="coerce")
        if pd.notna(valor):
            return pd.Timestamp(valor).normalize()
    return pd.NaT


def proyectar_universo_automatico_oleadas(
    lotes: pd.DataFrame,
    cosecha: pd.DataFrame | None,
    fecha_emision: object,
    *,
    semanas: int = 6,
    prior_historicos: Mapping[tuple[str, ...], MacroParams] | None = None,
    fecha_corte: object | None = None,
    modelo_contexto: ModeloContextoOleadas | None = None,
    contexto_por_lote: Mapping[tuple[str, ...], Mapping[str, Any]] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Proyecta al menos seis semanas para un universo sin leer Excel.

    ``lotes`` debe aportar identidad, área, plantas y fecha de poda/inicio. ``cosecha``
    puede ser diaria o semanal y acepta ``kg`` + ``peso`` o directamente los componentes
    ``frutos_por_planta`` + ``peso_baya_g``. La fecha de corte se aplica dentro de cada
    lote antes de ajustar las oleadas. ``prior_historicos`` es opcional y permite inyectar
    un prior de campaña anterior ya calibrado sin convertirlo en una dependencia oculta.

    La función devuelve una rejilla lote × emisión × H1…Hn y un resumen de soporte. Los
    lotes sin historia siguen emitiendo una curva explícita, pero quedan contabilizados en
    ``lotes_sin_historia`` y no se confunden con una predicción de alta confianza. Si se
    entrega ``modelo_contexto``, ``contexto_por_lote`` debe mapear la identidad canónica
    ``(campania, fundo, modulo, turno, lote)`` a sus features as-of; la calibración se
    aplica después del prior automático y antes de generar H1…Hn.
    """

    if lotes is None or lotes.empty:
        raise ValueError("lotes no puede estar vacío")
    if not 6 <= int(semanas) <= 52:
        raise ValueError("semanas debe estar entre 6 y 52")
    if prior_historicos is not None and not isinstance(prior_historicos, Mapping):
        raise TypeError("prior_historicos debe ser un mapping de identidad a MacroParams")
    if contexto_por_lote is not None and not isinstance(contexto_por_lote, Mapping):
        raise TypeError("contexto_por_lote debe ser un mapping de identidad a contexto")

    lotes_n = _canonizar_identidad_universo(lotes)
    cosecha_n = _canonizar_identidad_universo(
        cosecha if cosecha is not None else pd.DataFrame()
    )
    columnas_area = ("area_ha", "area", "Area")
    columnas_plantas = ("plantas", "n_plantas", "NPlantas")
    columnas_pivote = ("fecha_pivote", "fecha_poda", "fecha_inicio", "FPoda")
    fecha_corte_real = fecha_emision if fecha_corte is None else fecha_corte
    previos = dict(prior_historicos or {})
    salidas: list[pd.DataFrame] = []
    lotes_sin_historia: list[tuple[str, ...]] = []
    advertencias: list[str] = []

    for indice, fila in lotes_n.iterrows():
        registro = fila.to_dict()
        clave = _clave_universo(registro)
        area = _valor_numerico_alias(registro, columnas_area)
        plantas = _valor_numerico_alias(registro, columnas_plantas)
        pivote = _valor_fecha_alias(registro, columnas_pivote)
        if not pd.notna(area) or area <= 0:
            raise ValueError(f"Lote {clave} no tiene area/area_ha positiva")
        if not pd.notna(plantas) or plantas <= 0:
            raise ValueError(f"Lote {clave} no tiene plantas/n_plantas positivas")
        if not pd.notna(pivote):
            raise ValueError(f"Lote {clave} no tiene fecha de poda/inicio válida")

        if cosecha_n.empty:
            historia = cosecha_n.copy()
        else:
            mascara = pd.Series(True, index=cosecha_n.index)
            # El fundo es un rótulo que cambia entre R09, H01 y el maestro. La
            # identidad física segura para no mezclar cosechas es campaña + módulo +
            # turno + lote; conservar el fundo en la salida sigue siendo útil para
            # reportar, pero no debe bloquear la historia del lote.
            for columna in _CLAVES_HISTORIA_UNIVERSO:
                mascara &= cosecha_n[columna].eq(registro[columna])
            historia = cosecha_n.loc[mascara].copy()
        if historia.empty:
            lotes_sin_historia.append(clave)

        prior = previos.get(clave)
        if prior is not None and not isinstance(prior, MacroParams):
            raise TypeError(f"El prior del lote {clave} no es MacroParams")
        contexto_lote = (
            contexto_por_lote.get(clave, {}) if contexto_por_lote is not None else {}
        )
        if not isinstance(contexto_lote, Mapping):
            raise TypeError(f"El contexto del lote {clave} no es un mapping")
        salida, metadata = proyectar_automatico_oleadas(
            fecha_emision,
            fecha_pivote=pivote,
            plantas=plantas,
            area_ha=area,
            prior_historico=prior,
            modelo_contexto=modelo_contexto,
            contexto=contexto_lote,
            observaciones=historia if not historia.empty else None,
            fecha_corte=fecha_corte_real,
            semanas=semanas,
        )
        for columna in _CLAVES_UNIVERSO:
            salida[columna] = registro[columna]
        salida["indice_lote_universo"] = indice
        salida["tiene_historia_asof"] = bool(
            metadata["ajuste_oleadas"]["n_observaciones"] > 0
        )
        salida["tiene_prior_historico"] = prior is not None
        salida["nivel_contexto"] = metadata["nivel_contexto"]
        salidas.append(salida)
        advertencias.extend(
            f"{clave}: {advertencia}"
            for advertencia in metadata["ajuste_oleadas"].get("advertencias", [])
        )

    resultado = pd.concat(salidas, ignore_index=True, sort=False)
    metadata_universo: dict[str, Any] = {
        "modelo": NOMBRE_MODELO,
        "version": VERSION_MODELO,
        "fecha_emision": pd.Timestamp(fecha_emision).normalize().strftime("%Y-%m-%d"),
        "fecha_corte": pd.Timestamp(fecha_corte_real).normalize().strftime("%Y-%m-%d"),
        "semanas": int(semanas),
        "n_lotes": int(len(lotes_n)),
        "n_filas": int(len(resultado)),
        "lotes_con_historia_asof": int(len(lotes_n) - len(lotes_sin_historia)),
        "lotes_sin_historia": [list(clave) for clave in lotes_sin_historia],
        "lotes_con_prior_historico": int(
            sum(_clave_universo(fila) in previos for fila in lotes_n.to_dict("records"))
        ),
        "lotes_con_modelo_contexto": int(
            sum(
                modelo_contexto is not None
                and bool(contexto_por_lote)
                and _clave_universo(fila) in contexto_por_lote
                for fila in lotes_n.to_dict("records")
            )
        ),
        "advertencias": advertencias,
        "publicable": False,
    }
    return resultado, metadata_universo


__all__ = [
    "NOMBRE_MODELO",
    "PARAMETROS_MANUAL",
    "PARAMETROS_CURVA",
    "VERSION_MODELO",
    "_factor_carga",
    "proyectar_automatico_oleadas",
    "proyectar_candidato_oleadas",
    "proyectar_universo_automatico_oleadas",
]

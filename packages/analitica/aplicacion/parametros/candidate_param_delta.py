"""Candidato puro para aprender cambios de parámetros entre emisiones.

El modelo está diseñado para el escenario de pocos datos de ``ProySemanal``. No
predice kilos ni utiliza R09: aprende únicamente cómo cambiaron parámetros
homólogos entre una emisión previa y la siguiente, usando identificadores
agronómicos disponibles antes del corte.

La API no realiza I/O ni persistencia::

    modelo = CandidateParamDelta().fit(transiciones_hasta_corte)
    resultado = modelo.predict(parametros_previos, contexto)

``transiciones_hasta_corte`` admite una lista de diccionarios o un DataFrame.
La forma recomendada de cada transición es::

    {
        "parametros_previos": {"X1": 210, "O1": 20, ...},
        "parametros_objetivo": {"X1": 214, "O1": 22, ...},
        "contexto": {"fundo": "Arena", "modulo": "M01", "lote": "L001"},
        "emision_previa": "2026-08-03",
        "emision_objetivo": "2026-08-10",
    }

También se aceptan columnas planas como ``X1_prev``/``X1_next``. La emisión
objetivo puede acompañar la etiqueta para auditoría, pero nunca participa en la
estimación. Campos R09 también son ignorados deliberadamente.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

PARAMETROS_DIAS = frozenset({"X1", "X2", "X3"})
PARAMETROS_LOG = frozenset(
    {
        "O1",
        "O2",
        "O3",
        "N1",
        "N2",
        "N3",
        "A1",
        "A2",
        "A3",
    }
)
PARAMETROS_B = frozenset({"B1", "B2", "B3"})
PARAMETRO_CAIDA = "%Caida"
PARAMETRO_FINICIO = "Finicio"

_PARAMETRO_RE = re.compile(r"^(?P<familia>[XONAB])(?P<indice>[123])$", re.IGNORECASE)
_FEPAS_RE = re.compile(r"^FePas(?P<indice>[1-9][0-9]*)$", re.IGNORECASE)

_PREVIOS_ANIDADOS = (
    "parametros_previos",
    "parametros_anterior",
    "parametros_anteriores",
    "parametros_origen",
)
_OBJETIVOS_ANIDADOS = (
    "parametros_objetivo",
    "parametros_siguientes",
    "parametros_nuevos",
    "parametros_actuales",
)
_SUFIJOS_PREVIOS = ("_prev", "_previo", "_anterior", "_origen")
_SUFIJOS_OBJETIVO = ("_next", "_siguiente", "_objetivo", "_actual", "_nuevo")
_PREFIJOS_PREVIOS = ("prev_", "previo_", "anterior_", "origen_")
_PREFIJOS_OBJETIVO = ("next_", "siguiente_", "objetivo_", "actual_", "nuevo_")

_ALIAS_CONTEXTO = {
    "fundo": ("fundo", "fundo_nombre", "campo"),
    "modulo": ("modulo", "módulo", "modulo_id"),
    "lote": ("lote", "lote_id", "lote_codigo"),
    "variedad": ("variedad", "cultivar"),
}

# Orden de actualización desde el prior más amplio hacia el nivel más específico.
_JERARQUIA = (
    ("variedad", ("variedad",)),
    ("fundo", ("fundo",)),
    ("modulo", ("fundo", "modulo")),
    ("lote", ("fundo", "modulo", "lote")),
)
_RANGO_NIVEL = {"global": 0, "variedad": 1, "fundo": 2, "modulo": 3, "lote": 4}


@dataclass(frozen=True)
class ConfiguracionParamDelta:
    """Controles pequeños y auditables del estimador jerárquico."""

    regularizacion: float = 4.0
    cuantiles: tuple[float, float] = (0.05, 0.95)
    minimo_observaciones_nivel: int = 1
    epsilon: float = 1e-6

    def __post_init__(self) -> None:
        inferior, superior = self.cuantiles
        if self.regularizacion < 0:
            raise ValueError("regularizacion no puede ser negativa")
        if not 0 <= inferior <= superior <= 1:
            raise ValueError("cuantiles debe estar dentro de [0, 1]")
        if self.minimo_observaciones_nivel < 1:
            raise ValueError("minimo_observaciones_nivel debe ser al menos uno")
        if not 0 < self.epsilon < 0.5:
            raise ValueError("epsilon debe estar entre cero y 0.5")


@dataclass(frozen=True)
class _Resumen:
    mediana: float
    n: int


def _normalizar_texto(valor: Any) -> str:
    texto = unicodedata.normalize("NFKD", str(valor).strip())
    return "".join(caracter for caracter in texto if not unicodedata.combining(caracter)).casefold()


def _canonizar_parametro(nombre: Any) -> str | None:
    texto = str(nombre).strip().replace(" ", "")
    normalizado = _normalizar_texto(texto)
    if normalizado in {"%caida", "caida", "porcentajecaida", "pctcaida"}:
        return PARAMETRO_CAIDA
    if normalizado in {"finicio", "fechainicio", "fecha_inicio"}:
        return PARAMETRO_FINICIO
    coincidencia = _PARAMETRO_RE.fullmatch(texto)
    if coincidencia:
        return f"{coincidencia.group('familia').upper()}{coincidencia.group('indice')}"
    coincidencia = _FEPAS_RE.fullmatch(texto)
    if coincidencia:
        return f"FePas{int(coincidencia.group('indice'))}"
    return None


def _buscar_mapping(
    registro: Mapping[str, Any], nombres: Iterable[str]
) -> Mapping[str, Any] | None:
    indice = {_normalizar_texto(clave): clave for clave in registro}
    for nombre in nombres:
        original = indice.get(_normalizar_texto(nombre))
        if original is not None and isinstance(registro[original], Mapping):
            return registro[original]
    return None


def _extraer_planos(registro: Mapping[str, Any], *, previos: bool) -> dict[str, Any]:
    sufijos = _SUFIJOS_PREVIOS if previos else _SUFIJOS_OBJETIVO
    prefijos = _PREFIJOS_PREVIOS if previos else _PREFIJOS_OBJETIVO
    salida: dict[str, Any] = {}
    for columna, valor in registro.items():
        nombre = str(columna).strip()
        normalizado = _normalizar_texto(nombre)
        base: str | None = None
        for sufijo in sufijos:
            if normalizado.endswith(sufijo):
                base = nombre[: -len(sufijo)]
                break
        if base is None:
            for prefijo in prefijos:
                if normalizado.startswith(prefijo):
                    base = nombre[len(prefijo) :]
                    break
        canonico = _canonizar_parametro(base) if base is not None else None
        if canonico is not None:
            salida[canonico] = valor
    return salida


def _canonizar_mapping_parametros(parametros: Mapping[str, Any]) -> dict[str, Any]:
    salida: dict[str, Any] = {}
    for nombre, valor in parametros.items():
        canonico = _canonizar_parametro(nombre)
        if canonico is not None:
            salida[canonico] = valor
    return salida


def _extraer_parametros(
    registro: Mapping[str, Any],
    *,
    previos: bool,
) -> dict[str, Any]:
    nombres = _PREVIOS_ANIDADOS if previos else _OBJETIVOS_ANIDADOS
    anidado = _buscar_mapping(registro, nombres)
    if anidado is not None:
        return _canonizar_mapping_parametros(anidado)
    return _extraer_planos(registro, previos=previos)


def _valor_contexto(mapping: Mapping[str, Any], aliases: Iterable[str]) -> Any:
    indice = {_normalizar_texto(clave): clave for clave in mapping}
    for alias in aliases:
        original = indice.get(_normalizar_texto(alias))
        if original is not None:
            valor = mapping[original]
            if valor is not None and not pd.isna(valor):
                return str(valor).strip()
    return None


def _extraer_contexto(registro: Mapping[str, Any]) -> dict[str, str | None]:
    anidado = _buscar_mapping(registro, ("contexto", "context")) or {}
    contexto: dict[str, str | None] = {}
    for canonico, aliases in _ALIAS_CONTEXTO.items():
        valor = _valor_contexto(anidado, aliases)
        if valor is None:
            valor = _valor_contexto(registro, aliases)
        contexto[canonico] = valor
    return contexto


def _registros(tabla: Any) -> list[dict[str, Any]]:
    if isinstance(tabla, pd.DataFrame):
        return tabla.to_dict("records")
    if isinstance(tabla, Mapping):
        return [dict(tabla)]
    if isinstance(tabla, Iterable) and not isinstance(tabla, (str, bytes)):
        registros = list(tabla)
        if not all(isinstance(registro, Mapping) for registro in registros):
            raise TypeError("Cada transición debe ser un mapping")
        return [dict(registro) for registro in registros]
    raise TypeError("transiciones_hasta_corte debe ser DataFrame o iterable de mappings")


def _numero(valor: Any) -> float | None:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _fecha(valor: Any) -> pd.Timestamp | None:
    try:
        fecha = pd.Timestamp(valor)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(fecha) else fecha


def _logit(valor: float, epsilon: float) -> float:
    limitado = float(np.clip(valor, epsilon, 1 - epsilon))
    return math.log(limitado / (1 - limitado))


def _proporcion_caida(valor: Any) -> tuple[float | None, float]:
    numero = _numero(valor)
    if numero is None:
        return None, 1.0
    escala = 100.0 if 1 < numero <= 100 else 1.0
    proporcion = numero / escala
    if not 0 <= proporcion <= 1:
        return None, escala
    return proporcion, escala


def _tipo_transformacion(parametro: str) -> str:
    if parametro in PARAMETROS_DIAS:
        return "dias"
    if parametro in PARAMETROS_LOG:
        return "log"
    if parametro in PARAMETROS_B:
        return "b_estandarizado"
    if parametro == PARAMETRO_CAIDA:
        return "logit"
    if parametro == PARAMETRO_FINICIO or _FEPAS_RE.fullmatch(parametro):
        return "fecha_dias"
    raise ValueError(f"Parámetro no soportado: {parametro}")


def _delta_crudo(parametro: str, previo: Any, objetivo: Any, epsilon: float) -> float | None:
    transformacion = _tipo_transformacion(parametro)
    if transformacion in {"dias", "b_estandarizado"}:
        anterior = _numero(previo)
        siguiente = _numero(objetivo)
        if anterior is None or siguiente is None:
            return None
        return siguiente - anterior
    if transformacion == "log":
        anterior = _numero(previo)
        siguiente = _numero(objetivo)
        if anterior is None or siguiente is None or anterior <= 0 or siguiente <= 0:
            return None
        return math.log(siguiente) - math.log(anterior)
    if transformacion == "logit":
        anterior, _ = _proporcion_caida(previo)
        siguiente, _ = _proporcion_caida(objetivo)
        if anterior is None or siguiente is None:
            return None
        return _logit(siguiente, epsilon) - _logit(anterior, epsilon)
    anterior = _fecha(previo)
    siguiente = _fecha(objetivo)
    if anterior is None or siguiente is None:
        return None
    return float((siguiente - anterior) / pd.Timedelta(1, unit="D"))


def _escala_robusta(valores: np.ndarray) -> tuple[float, float]:
    centro = float(np.median(valores))
    mad = float(np.median(np.abs(valores - centro)))
    escala = 1.4826 * mad
    if not math.isfinite(escala) or escala <= 1e-12:
        escala = float(np.std(valores, ddof=0))
    if not math.isfinite(escala) or escala <= 1e-12:
        escala = 1.0
    return centro, escala


def _clave_grupo(contexto: Mapping[str, Any], campos: tuple[str, ...]) -> tuple[str, ...] | None:
    valores = tuple(contexto.get(campo) for campo in campos)
    if any(valor is None or str(valor).strip() == "" for valor in valores):
        return None
    return tuple(str(valor).strip() for valor in valores)


def _restaurar_fecha(original: Any, fecha: pd.Timestamp) -> Any:
    if isinstance(original, pd.Timestamp):
        return fecha
    if isinstance(original, datetime):
        return fecha.to_pydatetime()
    if isinstance(original, date):
        return fecha.date()
    if isinstance(original, str):
        return fecha.strftime("%Y-%m-%d")
    return fecha


class CandidateParamDelta:
    """Medianas jerárquicas con shrinkage para deltas de parámetros.

    Solo usa ``fundo``, ``modulo``, ``lote`` y ``variedad`` como contexto. En
    particular, no incorpora fecha/ID de la emisión objetivo ni ninguna salida R09.
    """

    def __init__(
        self,
        config: ConfiguracionParamDelta | None = None,
        *,
        regularizacion: float | None = None,
        cuantiles: tuple[float, float] | None = None,
        minimo_observaciones_nivel: int | None = None,
    ) -> None:
        if config is not None and any(
            valor is not None for valor in (regularizacion, cuantiles, minimo_observaciones_nivel)
        ):
            raise ValueError("Use config o argumentos directos, no ambos")
        self.config = config or ConfiguracionParamDelta(
            regularizacion=4.0 if regularizacion is None else regularizacion,
            cuantiles=(0.05, 0.95) if cuantiles is None else cuantiles,
            minimo_observaciones_nivel=(
                1 if minimo_observaciones_nivel is None else minimo_observaciones_nivel
            ),
        )
        self._ajustado = False
        self.parametros_aprendidos_: tuple[str, ...] = ()
        self.feature_names_: tuple[str, ...] = ("fundo", "modulo", "lote", "variedad")
        self.limites_: dict[str, tuple[float, float]] = {}
        self.estandarizacion_b_: dict[str, tuple[float, float]] = {}
        self._global: dict[str, _Resumen] = {}
        self._grupos: dict[str, dict[str, dict[tuple[str, ...], _Resumen]]] = {}
        self.n_transiciones_: int = 0

    def fit(self, transiciones_hasta_corte: Any) -> CandidateParamDelta:
        """Aprende deltas usando únicamente transiciones ya disponibles al corte."""

        registros = _registros(transiciones_hasta_corte)
        observaciones: list[dict[str, Any]] = []
        for registro in registros:
            previos = _extraer_parametros(registro, previos=True)
            objetivos = _extraer_parametros(registro, previos=False)
            contexto = _extraer_contexto(registro)
            for parametro in sorted(previos.keys() & objetivos.keys()):
                delta = _delta_crudo(
                    parametro,
                    previos[parametro],
                    objetivos[parametro],
                    self.config.epsilon,
                )
                if delta is not None and math.isfinite(delta):
                    observaciones.append({"parametro": parametro, "delta_crudo": delta, **contexto})

        if not observaciones:
            raise ValueError("No hay pares válidos de parámetros previos/objetivo")

        tabla = pd.DataFrame(observaciones)
        self.estandarizacion_b_ = {}
        tabla["delta"] = tabla.delta_crudo.astype(float)
        for parametro in sorted(set(tabla.parametro) & PARAMETROS_B):
            mascara = tabla.parametro.eq(parametro)
            centro, escala = _escala_robusta(tabla.loc[mascara, "delta_crudo"].to_numpy(float))
            self.estandarizacion_b_[parametro] = (centro, escala)
            tabla.loc[mascara, "delta"] = (tabla.loc[mascara, "delta_crudo"] - centro) / escala

        inferior, superior = self.config.cuantiles
        self.limites_ = {}
        self._global = {}
        self._grupos = {}
        for parametro, bloque in tabla.groupby("parametro", sort=True):
            valores = bloque.delta.to_numpy(float)
            limites = (
                float(np.quantile(valores, inferior)),
                float(np.quantile(valores, superior)),
            )
            self.limites_[str(parametro)] = limites
            self._global[str(parametro)] = _Resumen(float(np.median(valores)), len(valores))
            por_nivel: dict[str, dict[tuple[str, ...], _Resumen]] = {}
            for nivel, campos in _JERARQUIA:
                estadisticas: dict[tuple[str, ...], _Resumen] = {}
                agrupables = bloque.dropna(subset=list(campos))
                if not agrupables.empty:
                    llave: str | list[str] = campos[0] if len(campos) == 1 else list(campos)
                    for clave, grupo in agrupables.groupby(llave, dropna=False, sort=False):
                        valores_clave = clave if isinstance(clave, tuple) else (clave,)
                        estadisticas[tuple(str(valor).strip() for valor in valores_clave)] = (
                            _Resumen(float(grupo.delta.median()), len(grupo))
                        )
                por_nivel[nivel] = estadisticas
            self._grupos[str(parametro)] = por_nivel

        self.parametros_aprendidos_ = tuple(sorted(self._global, key=self._orden_parametro))
        self.n_transiciones_ = len(registros)
        self._ajustado = True
        return self

    @staticmethod
    def _orden_parametro(parametro: str) -> tuple[int, int, str]:
        grupos = {"X": 0, "O": 1, "N": 2, "A": 3, "B": 4}
        if parametro == PARAMETRO_CAIDA:
            return (5, 0, parametro)
        if parametro == PARAMETRO_FINICIO:
            return (6, 0, parametro)
        fepas = _FEPAS_RE.fullmatch(parametro)
        if fepas:
            return (7, int(fepas.group("indice")), parametro)
        return (grupos.get(parametro[:1], 99), int(parametro[1:2] or 0), parametro)

    def _estimar_delta(
        self,
        parametro: str,
        contexto: Mapping[str, Any],
    ) -> tuple[float, str, int]:
        resumen_global = self._global[parametro]
        estimacion = resumen_global.mediana
        nivel_usado = "global"
        n_usado = resumen_global.n
        for nivel, campos in _JERARQUIA:
            clave = _clave_grupo(contexto, campos)
            if clave is None:
                continue
            resumen = self._grupos[parametro][nivel].get(clave)
            if resumen is None or resumen.n < self.config.minimo_observaciones_nivel:
                continue
            if self.config.regularizacion:
                peso = resumen.n / (resumen.n + self.config.regularizacion)
                estimacion = peso * resumen.mediana + (1 - peso) * estimacion
            else:
                estimacion = resumen.mediana
            nivel_usado = nivel
            n_usado = resumen.n
        minimo, maximo = self.limites_[parametro]
        return float(np.clip(estimacion, minimo, maximo)), nivel_usado, int(n_usado)

    def _aplicar_delta(self, parametro: str, previo: Any, delta: float) -> tuple[Any, float]:
        transformacion = _tipo_transformacion(parametro)
        if transformacion == "dias":
            numero = _numero(previo)
            if numero is None:
                return previo, math.nan
            return numero + delta, delta
        if transformacion == "log":
            numero = _numero(previo)
            if numero is None or numero <= 0:
                return previo, math.nan
            return numero * math.exp(delta), delta
        if transformacion == "b_estandarizado":
            numero = _numero(previo)
            if numero is None:
                return previo, math.nan
            centro, escala = self.estandarizacion_b_[parametro]
            delta_crudo = centro + escala * delta
            return numero + delta_crudo, delta_crudo
        if transformacion == "logit":
            proporcion, escala_salida = _proporcion_caida(previo)
            if proporcion is None:
                return previo, math.nan
            logit_final = _logit(proporcion, self.config.epsilon) + delta
            final = 1 / (1 + math.exp(-float(np.clip(logit_final, -35, 35))))
            return final * escala_salida, delta
        fecha = _fecha(previo)
        if fecha is None:
            return previo, math.nan
        dias = int(round(delta))
        return _restaurar_fecha(previo, fecha + pd.to_timedelta(dias, unit="D")), float(dias)

    def predict(
        self,
        parametros_previos: Mapping[str, Any],
        contexto: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Corrige un conjunto de parámetros sin mutar los objetos de entrada.

        El resultado incluye el mapping ``parametros`` y trazabilidad por parámetro.
        ``nivel_calibracion`` y ``n_observaciones`` son conservadores: informan el
        nivel más específico alcanzado y el menor soporte entre deltas aplicados.
        """

        if not self._ajustado:
            raise RuntimeError("CandidateParamDelta debe ajustarse antes de predecir")
        if not isinstance(parametros_previos, Mapping):
            raise TypeError("parametros_previos debe ser un mapping")
        if contexto is not None and not isinstance(contexto, Mapping):
            raise TypeError("contexto debe ser un mapping")

        originales = deepcopy(dict(parametros_previos))
        canonicos = _canonizar_mapping_parametros(parametros_previos)
        contexto_normalizado = _extraer_contexto(contexto or {})
        finales = deepcopy(originales)
        detalle: dict[str, dict[str, Any]] = {}
        niveles: list[str] = []
        soportes: list[int] = []

        # Conserva los nombres originales si venían con otra capitalización.
        nombre_salida = {
            canonico: nombre
            for nombre in parametros_previos
            if (canonico := _canonizar_parametro(nombre)) is not None
        }
        for parametro in self.parametros_aprendidos_:
            if parametro not in canonicos:
                continue
            delta, nivel, n = self._estimar_delta(parametro, contexto_normalizado)
            valor_final, delta_aplicado = self._aplicar_delta(
                parametro, canonicos[parametro], delta
            )
            if isinstance(delta_aplicado, float) and math.isnan(delta_aplicado):
                continue
            finales[nombre_salida.get(parametro, parametro)] = valor_final
            niveles.append(nivel)
            soportes.append(n)
            detalle[parametro] = {
                "transformacion": _tipo_transformacion(parametro),
                "delta_modelado": delta,
                "delta_aplicado": delta_aplicado,
                "limites_entrenamiento": self.limites_[parametro],
                "nivel_calibracion": nivel,
                "n_observaciones": n,
            }

        if niveles:
            mas_especifico = max(niveles, key=lambda nivel: _RANGO_NIVEL[nivel])
            nivel_calibracion = (
                mas_especifico if len(set(niveles)) == 1 else f"mixto:{mas_especifico}"
            )
            n_observaciones = min(soportes)
        else:
            nivel_calibracion = "sin_parametros_aplicables"
            n_observaciones = 0

        return {
            "parametros": finales,
            "nivel_calibracion": nivel_calibracion,
            "n_observaciones": int(n_observaciones),
            "detalle_calibracion": detalle,
        }


# Alias breve para integraciones que prefieren nombrar el estimador por dominio.
ModeloDeltaParametros = CandidateParamDelta


__all__ = [
    "CandidateParamDelta",
    "ConfiguracionParamDelta",
    "ModeloDeltaParametros",
    "PARAMETROS_B",
    "PARAMETROS_DIAS",
    "PARAMETROS_LOG",
]

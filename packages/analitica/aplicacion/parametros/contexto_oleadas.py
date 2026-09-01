"""Puente as-of entre contexto agronómico y parámetros de las oleadas.

El proceso manual ya contiene una curva útil (X/O/N y A/B), mientras que las hojas
de clima, riego, poda, flores y cosecha describen el estado del lote. Este módulo no
mezcla esas señales directamente con kilos: aprende deltas de los parámetros del
libro y los aplica antes de proyectar la curva Gaussian/exponencial.

El ajuste es una regresión ridge pequeña y auditable. Sus contribuciones son
asociaciones mecánicas del modelo, no efectos causales. El llamador debe entregar el
contexto ya construido con la regla ``fecha_dato < fecha_emision``; la utilidad de
unión incluida abajo permite aplicar esa regla de forma reproducible.
"""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

PARAMETROS_CONTEXTO = (
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

FEATURES_CONTEXTO_POR_DEFECTO = (
    "dias_desde_poda",
    "poda_dispersion_dias",
    "gdd_acum_poda_obs",
    "gdd_semanas_poda_obs",
    "gdd_28d",
    "riego_lt_planta",
    "riego_m3_ha",
    "riego_agua_ha",
    "DPV",
    "Rad",
    "ETo",
    "flores_promedio",
    "flores_dispersion_relativa",
    "tasa_cuajo",
    "indice_estado",
    "prop_e45",
    "kg_real_acumulado",
    "kg_ultimas_4_semanas_asof",
)

_PARAMETROS_DIAS = frozenset({"X1", "X2", "X3"})
_PARAMETROS_LOG = frozenset(
    {"O1", "O2", "O3", "N1", "N2", "N3", "A1", "A2", "A3"}
)
_PARAMETROS_B = frozenset({"B1", "B2", "B3"})
_CLAVES_CONTEXTO = ("campania", "fundo", "modulo", "turno", "lote", "lote_id")


@dataclass(frozen=True)
class ConfiguracionContextoOleadas:
    """Controles del ajuste continuo, congelables en una corrida."""

    regularizacion: float = 12.0
    minimo_observaciones: int = 24
    minima_cobertura: float = 0.50
    cuantiles: tuple[float, float] = (0.05, 0.95)
    max_abs_delta_dias: float = 21.0
    max_abs_delta_log: float = 0.35
    max_abs_delta_b: float = 0.001

    def __post_init__(self) -> None:
        if self.regularizacion < 0 or not np.isfinite(self.regularizacion):
            raise ValueError("regularizacion debe ser no negativa y finita")
        if self.minimo_observaciones < 2:
            raise ValueError("minimo_observaciones debe ser al menos dos")
        if not 0 < self.minima_cobertura <= 1:
            raise ValueError("minima_cobertura debe estar entre cero y uno")
        inferior, superior = self.cuantiles
        if not 0 <= inferior < superior <= 1:
            raise ValueError("cuantiles debe estar dentro de [0, 1]")
        for nombre in (
            "max_abs_delta_dias",
            "max_abs_delta_log",
            "max_abs_delta_b",
        ):
            if not np.isfinite(getattr(self, nombre)) or getattr(self, nombre) <= 0:
                raise ValueError(f"{nombre} debe ser positivo y finito")


@dataclass(frozen=True)
class _ModeloParametro:
    intercepto: float
    coeficientes: tuple[float, ...]
    centros: tuple[float, ...]
    escalas: tuple[float, ...]
    limite_inferior: float
    limite_superior: float
    transformacion: str
    n_observaciones: int


def _normalizar_nombre(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return "".join(caracter for caracter in texto.casefold() if caracter.isalnum())


def _es_nulo(valor: object) -> bool:
    if valor is None:
        return True
    try:
        resultado = pd.isna(valor)
    except (TypeError, ValueError):
        return False
    return bool(resultado) if isinstance(resultado, (bool, np.bool_)) else False


def _numero(valor: object) -> float | None:
    if _es_nulo(valor):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _indice_mapping(mapping: Mapping[str, Any]) -> dict[str, str]:
    return {_normalizar_nombre(clave): str(clave) for clave in mapping}


def _buscar(mapping: Mapping[str, Any], nombres: Sequence[str]) -> Any:
    indice = _indice_mapping(mapping)
    for nombre in nombres:
        clave = indice.get(_normalizar_nombre(nombre))
        if clave is not None:
            return mapping[clave]
    return None


def _valor_parametro(registro: Mapping[str, Any], parametro: str, lado: str) -> object:
    if lado == "previo":
        anidados = (
            "parametros_previos",
            "parametros_anterior",
            "parametros_anteriores",
            "parametros_origen",
        )
        sufijos = ("_anterior", "_previo", "_prev", "_origen")
        prefijos = ("anterior_", "previo_", "prev_", "origen_")
    else:
        anidados = (
            "parametros_objetivo",
            "parametros_actuales",
            "parametros_siguientes",
            "parametros_nuevos",
        )
        sufijos = ("_actual", "_objetivo", "_siguiente", "_nuevo", "_next")
        prefijos = ("actual_", "objetivo_", "siguiente_", "nuevo_", "next_")

    anidado = _buscar(registro, anidados)
    if isinstance(anidado, Mapping):
        valor = _buscar(anidado, (parametro,))
        if not _es_nulo(valor):
            return valor

    indice = _indice_mapping(registro)
    nombres = [f"{parametro}{sufijo}" for sufijo in sufijos]
    nombres.extend(f"{prefijo}{parametro}" for prefijo in prefijos)
    for nombre in nombres:
        clave = indice.get(_normalizar_nombre(nombre))
        if clave is not None:
            return registro[clave]
    return None


def _transformar_delta(parametro: str, previo: object, actual: object) -> tuple[float, str] | None:
    anterior = _numero(previo)
    siguiente = _numero(actual)
    if anterior is None or siguiente is None:
        return None
    if parametro in _PARAMETROS_DIAS or parametro in _PARAMETROS_B:
        return siguiente - anterior, "dias" if parametro in _PARAMETROS_DIAS else "b"
    if parametro in _PARAMETROS_LOG:
        if anterior <= 0 or siguiente <= 0:
            return None
        return math.log(siguiente / anterior), "log"
    return None


def _escala_robusta(valores: np.ndarray) -> tuple[float, float]:
    centro = float(np.median(valores))
    mad = float(np.median(np.abs(valores - centro)))
    escala = 1.4826 * mad
    if not np.isfinite(escala) or escala <= 1e-12:
        escala = float(np.std(valores, ddof=0))
    if not np.isfinite(escala) or escala <= 1e-12:
        escala = 1.0
    return centro, escala


def _limite_maximo(transformacion: str, config: ConfiguracionContextoOleadas) -> float:
    if transformacion == "dias":
        return config.max_abs_delta_dias
    if transformacion == "log":
        return config.max_abs_delta_log
    return config.max_abs_delta_b


class ModeloContextoOleadas:
    """Aprende cómo el contexto modifica X/O/N/A/B, sin tocar el nivel R09.

    El entrenamiento recibe transiciones de parámetros del libro. Las columnas pueden
    venir como ``X1_anterior``/``X1_actual`` o como mappings anidados. Las features son
    valores numéricos calculados antes de la emisión objetivo.
    """

    def __init__(
        self,
        feature_names: Sequence[str] | None = None,
        *,
        config: ConfiguracionContextoOleadas | None = None,
    ) -> None:
        nombres = tuple(feature_names or FEATURES_CONTEXTO_POR_DEFECTO)
        if not nombres or len(set(nombres)) != len(nombres):
            raise ValueError("feature_names debe contener nombres únicos")
        self.feature_names = nombres
        self.config = config or ConfiguracionContextoOleadas()
        self._modelos: dict[str, _ModeloParametro] = {}
        self._ajustado = False
        self.feature_names_: tuple[str, ...] = ()
        self.features_faltantes_: tuple[str, ...] = ()
        self.parametros_aprendidos_: tuple[str, ...] = ()
        self.n_transiciones_: int = 0
        self.fecha_corte_: pd.Timestamp | None = None

    def fit(
        self,
        transiciones: pd.DataFrame,
        *,
        fecha_corte: object | None = None,
    ) -> ModeloContextoOleadas:
        """Ajusta los deltas usando únicamente transiciones disponibles al corte."""

        if not isinstance(transiciones, pd.DataFrame):
            raise TypeError("transiciones debe ser un pandas.DataFrame")
        if transiciones.empty:
            raise ValueError("transiciones no puede estar vacío")
        base = transiciones.copy()
        self.fecha_corte_ = None
        if fecha_corte is not None:
            corte = pd.Timestamp(fecha_corte).normalize()
            if pd.isna(corte):
                raise ValueError("fecha_corte no es válida")
            fecha_columna = next(
                (
                    columna
                    for columna in (
                        "fecha_emision_actual",
                        "fecha_emision_objetivo",
                        "fecha_emision",
                    )
                    if columna in base
                ),
                None,
            )
            if fecha_columna is None:
                raise ValueError(
                    "fecha_corte requiere fecha_emision_actual, fecha_emision_objetivo "
                    "o fecha_emision"
                )
            fechas = pd.to_datetime(base[fecha_columna], errors="coerce").dt.normalize()
            base = base.loc[fechas.notna() & fechas.lt(corte)].copy()
            self.fecha_corte_ = corte
        if base.empty:
            raise ValueError("no quedan transiciones antes de fecha_corte")

        disponibles = tuple(nombre for nombre in self.feature_names if nombre in base)
        if not disponibles:
            raise ValueError(
                "ninguna feature de contexto está en transiciones: "
                + ", ".join(self.feature_names)
            )
        self.feature_names_ = disponibles
        self.features_faltantes_ = tuple(
            nombre for nombre in self.feature_names if nombre not in disponibles
        )
        self._modelos = {}

        registros = base.to_dict("records")
        for parametro in PARAMETROS_CONTEXTO:
            datos: list[tuple[float, list[float], str]] = []
            for registro in registros:
                delta = _transformar_delta(
                    parametro,
                    _valor_parametro(registro, parametro, "previo"),
                    _valor_parametro(registro, parametro, "actual"),
                )
                if delta is None:
                    continue
                objetivo, transformacion = delta
                valores = [_numero(registro.get(nombre)) for nombre in disponibles]
                if not any(valor is not None for valor in valores):
                    continue
                datos.append(
                    (
                        objetivo,
                        [valor if valor is not None else np.nan for valor in valores],
                        transformacion,
                    )
                )
            if len(datos) < self.config.minimo_observaciones:
                continue
            objetivos = np.asarray([fila[0] for fila in datos], dtype=float)
            matriz = np.asarray([fila[1] for fila in datos], dtype=float)
            centros: list[float] = []
            escalas: list[float] = []
            for posicion in range(matriz.shape[1]):
                columna = matriz[:, posicion]
                observados = columna[np.isfinite(columna)]
                centro, escala = _escala_robusta(observados)
                centros.append(centro)
                escalas.append(escala)
                columna[~np.isfinite(columna)] = centro
            z = (matriz - np.asarray(centros)) / np.asarray(escalas)
            diseno = np.column_stack([np.ones(len(z)), z])
            penalizacion = np.eye(diseno.shape[1], dtype=float) * self.config.regularizacion
            penalizacion[0, 0] = 0.0
            izquierda = diseno.T @ diseno + penalizacion
            derecha = diseno.T @ objetivos
            try:
                coeficientes = np.linalg.solve(izquierda, derecha)
            except np.linalg.LinAlgError:
                coeficientes = np.linalg.pinv(izquierda) @ derecha
            transformacion = datos[0][2]
            limite = _limite_maximo(transformacion, self.config)
            inferior, superior = self.config.cuantiles
            limite_inferior = max(-limite, float(np.quantile(objetivos, inferior)))
            limite_superior = min(limite, float(np.quantile(objetivos, superior)))
            if limite_inferior >= limite_superior:
                limite_inferior, limite_superior = -limite, limite
            self._modelos[parametro] = _ModeloParametro(
                intercepto=float(coeficientes[0]),
                coeficientes=tuple(float(valor) for valor in coeficientes[1:]),
                centros=tuple(centros),
                escalas=tuple(escalas),
                limite_inferior=limite_inferior,
                limite_superior=limite_superior,
                transformacion=transformacion,
                n_observaciones=len(datos),
            )

        if not self._modelos:
            raise ValueError(
                "ningún parámetro alcanzó el mínimo de observaciones con contexto válido"
            )
        self.parametros_aprendidos_ = tuple(
            parametro for parametro in PARAMETROS_CONTEXTO if parametro in self._modelos
        )
        self.n_transiciones_ = len(base)
        self._ajustado = True
        return self

    def _contexto_numerico(
        self,
        contexto: Mapping[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, tuple[str, ...]]:
        if not isinstance(contexto, Mapping):
            raise TypeError("contexto debe ser un mapping")
        valores = np.asarray(
            [_numero(_buscar(contexto, (nombre,))) for nombre in self.feature_names_],
            dtype=float,
        )
        presentes = np.isfinite(valores)
        return valores, presentes, tuple(
            nombre
            for nombre, presente in zip(self.feature_names_, presentes, strict=True)
            if presente
        )

    def predict(
        self,
        parametros_previos: Mapping[str, Any],
        contexto: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Aplica el ajuste y devuelve contribuciones por feature."""

        if not self._ajustado:
            raise RuntimeError("ModeloContextoOleadas debe ajustarse antes de predecir")
        if not isinstance(parametros_previos, Mapping):
            raise TypeError("parametros_previos debe ser un mapping")
        contexto = contexto or {}
        valores, presentes, nombres_presentes = self._contexto_numerico(contexto)
        cobertura = float(presentes.mean()) if len(presentes) else 0.0
        salida = dict(parametros_previos)
        detalles: dict[str, Any] = {}
        usable = cobertura >= self.config.minima_cobertura
        for parametro, modelo in self._modelos.items():
            previo = _numero(_buscar(parametros_previos, (parametro,)))
            if previo is None:
                detalles[parametro] = {"estado": "previo_invalido"}
                continue
            z = np.zeros(len(self.feature_names_), dtype=float)
            for indice, valor in enumerate(valores):
                if np.isfinite(valor):
                    z[indice] = (valor - modelo.centros[indice]) / modelo.escalas[indice]
            contribuciones = {
                nombre: float(modelo.coeficientes[indice] * z[indice])
                if presentes[indice]
                else 0.0
                for indice, nombre in enumerate(self.feature_names_)
            }
            delta = modelo.intercepto + float(np.dot(modelo.coeficientes, z))
            delta = float(np.clip(delta, modelo.limite_inferior, modelo.limite_superior))
            if usable:
                if modelo.transformacion == "log":
                    final = previo * math.exp(delta)
                else:
                    final = previo + delta
                salida[parametro] = final
                estado = "aplicado"
            else:
                delta = 0.0
                estado = "sin_soporte_contexto"
            detalles[parametro] = {
                "estado": estado,
                "valor_previo": previo,
                "valor_final": float(salida[parametro]) if parametro in salida else previo,
                "delta_transformado": delta,
                "transformacion": modelo.transformacion,
                "n_observaciones": modelo.n_observaciones,
                "contribuciones": contribuciones,
                "driver_principal": (
                    max(contribuciones, key=lambda nombre: abs(contribuciones[nombre]))
                    if nombres_presentes
                    else "sin_contexto"
                ),
            }
        aplicados = [
            parametro
            for parametro, detalle in detalles.items()
            if detalle.get("estado") == "aplicado"
        ]
        return {
            "parametros": salida,
            "detalle_calibracion": detalles,
            "nivel_calibracion": "contexto_continuo" if aplicados else "sin_soporte_contexto",
            "n_observaciones": min(
                (self._modelos[parametro].n_observaciones for parametro in aplicados),
                default=0,
            ),
            "features_presentes": nombres_presentes,
            "cobertura_contexto": cobertura,
            "parametros_aplicados": tuple(aplicados),
            "sin_fuga": True,
            "etiqueta_causal": False,
        }


def unir_contexto_asof(
    transiciones: pd.DataFrame,
    contexto: pd.DataFrame,
    *,
    fecha_contexto: str | None = None,
    claves_union: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Une el último contexto estrictamente anterior a cada transición.

    La unión usa las claves comunes entre campaña/fundo/módulo/turno/lote, salvo que
    ``claves_union`` fuerce un conjunto explícito. Esto permite que fuentes con nombres
    de fundo distintos, pero con la misma identidad física, se unan por campaña/módulo/
    turno/lote. Si el contexto es global (por ejemplo, una estación climática), se une
    solo por fecha. No se permite ``fecha_dato == fecha_emision_actual`` para evitar
    fuga de la semana que se está emitiendo.
    """

    if not isinstance(transiciones, pd.DataFrame) or not isinstance(contexto, pd.DataFrame):
        raise TypeError("transiciones y contexto deben ser DataFrames")
    if "fecha_emision_actual" not in transiciones:
        raise ValueError("transiciones requiere fecha_emision_actual")
    if contexto.empty:
        salida = transiciones.copy()
        salida["fecha_contexto_asof"] = pd.NaT
        salida["nivel_contexto_asof"] = "sin_contexto"
        return salida, {"filas": len(salida), "filas_con_contexto": 0, "fuga": False}

    fecha_columna = fecha_contexto or next(
        (
            columna
            for columna in ("fecha_dato", "fecha", "fecha_emision")
            if columna in contexto
        ),
        None,
    )
    if fecha_columna is None:
        raise ValueError("contexto requiere fecha_dato, fecha o fecha_emision")
    izquierda = transiciones.copy().reset_index(drop=True)
    derecha = contexto.copy().reset_index(drop=True)
    izquierda["__fila_contexto"] = np.arange(len(izquierda), dtype=np.int64)
    fecha_izquierda = pd.to_datetime(
        izquierda["fecha_emision_actual"], errors="coerce"
    )
    fecha_derecha = pd.to_datetime(derecha[fecha_columna], errors="coerce")
    if getattr(fecha_izquierda.dt, "tz", None) is not None:
        fecha_izquierda = fecha_izquierda.dt.tz_convert("UTC").dt.tz_localize(None)
    if getattr(fecha_derecha.dt, "tz", None) is not None:
        fecha_derecha = fecha_derecha.dt.tz_convert("UTC").dt.tz_localize(None)
    izquierda["__fecha_emision_asof"] = fecha_izquierda.dt.normalize().astype(
        "datetime64[ns]"
    )
    derecha["__fecha_contexto"] = fecha_derecha.dt.normalize().astype(
        "datetime64[ns]"
    )
    if izquierda.__fecha_emision_asof.isna().any():
        raise ValueError("transiciones contiene fechas de emisión inválidas")
    derecha = derecha[derecha.__fecha_contexto.notna()].copy()
    if claves_union is None:
        claves = [
            clave
            for clave in _CLAVES_CONTEXTO
            if clave in izquierda.columns and clave in derecha.columns
        ]
    else:
        claves = list(dict.fromkeys(str(clave) for clave in claves_union))
        desconocidas = [clave for clave in claves if clave not in _CLAVES_CONTEXTO]
        if desconocidas:
            raise ValueError(
                "claves_union contiene claves no soportadas: "
                + ", ".join(desconocidas)
            )
        faltantes = [
            clave
            for clave in claves
            if clave not in izquierda.columns or clave not in derecha.columns
        ]
        if faltantes:
            raise ValueError(
                "claves_union no están presentes en ambas tablas: "
                + ", ".join(faltantes)
            )
    features = [
        columna
        for columna in derecha.columns
        if columna not in {
            *_CLAVES_CONTEXTO,
            fecha_columna,
            "__fecha_contexto",
        }
    ]
    join_keys = []
    for clave in claves:
        join_key = f"__join_{clave}"
        join_keys.append(join_key)
        izquierda[join_key] = izquierda[clave].astype("string").fillna("__NA__")
        derecha[join_key] = derecha[clave].astype("string").fillna("__NA__")
    columnas_contexto = [f"__contexto_{feature}" for feature in features]
    derecha = derecha.rename(
        columns=dict(zip(features, columnas_contexto, strict=True))
    )
    partes: list[pd.DataFrame] = []
    if join_keys:
        grupos_derecha = {
            clave if isinstance(clave, tuple) else (clave,): grupo
            for clave, grupo in derecha.groupby(join_keys, sort=False, dropna=False)
        }
        grupos_izquierda = izquierda.groupby(join_keys, sort=False, dropna=False)
        for clave, grupo_izquierda in grupos_izquierda:
            clave_tuple = clave if isinstance(clave, tuple) else (clave,)
            grupo_derecha = grupos_derecha.get(clave_tuple)
            izquierdo_ordenado = grupo_izquierda.sort_values(
                "__fecha_emision_asof", kind="stable"
            )
            if grupo_derecha is None or grupo_derecha.empty:
                unido_grupo = izquierdo_ordenado.copy()
                unido_grupo["__fecha_contexto"] = pd.NaT
                for columna in columnas_contexto:
                    unido_grupo[columna] = np.nan
            else:
                derecho_ordenado = grupo_derecha.sort_values(
                    "__fecha_contexto", kind="stable"
                )
                unido_grupo = pd.merge_asof(
                    izquierdo_ordenado,
                    derecho_ordenado[["__fecha_contexto", *columnas_contexto]],
                    left_on="__fecha_emision_asof",
                    right_on="__fecha_contexto",
                    direction="backward",
                    allow_exact_matches=False,
                )
            partes.append(unido_grupo)
    else:
        izquierdo_ordenado = izquierda.sort_values(
            "__fecha_emision_asof", kind="stable"
        )
        derecho_ordenado = derecha.sort_values("__fecha_contexto", kind="stable")
        unido = pd.merge_asof(
            izquierdo_ordenado,
            derecho_ordenado[["__fecha_contexto", *columnas_contexto]],
            left_on="__fecha_emision_asof",
            right_on="__fecha_contexto",
            direction="backward",
            allow_exact_matches=False,
        )
        partes.append(unido)
    unido = pd.concat(partes, ignore_index=True, sort=False)
    unido = unido.sort_values("__fila_contexto", kind="stable")
    for feature, columna in zip(features, columnas_contexto, strict=True):
        if columna in unido:
            unido[feature] = unido[columna]
    unido["fecha_contexto_asof"] = unido["__fecha_contexto"]
    if "lote" in claves or "lote_id" in claves:
        nivel = "exacto"
    elif "modulo" in claves:
        nivel = "modulo"
    else:
        nivel = "global"
    unido["nivel_contexto_asof"] = np.where(
        unido["fecha_contexto_asof"].notna(), nivel, "sin_contexto"
    )
    salida = unido.drop(
        columns=[
            "__fila_contexto",
            "__fecha_emision_asof",
            "__fecha_contexto",
            *join_keys,
            *columnas_contexto,
        ],
        errors="ignore",
    )
    salida = salida.loc[:, ~salida.columns.duplicated()].reset_index(drop=True)
    con_contexto = int(salida.fecha_contexto_asof.notna().sum())
    return salida, {
        "filas": int(len(salida)),
        "filas_con_contexto": con_contexto,
        "cobertura": float(con_contexto / len(salida)) if len(salida) else 0.0,
        "claves_union": claves,
        "features": features,
        "nivel": nivel,
        "fecha_contexto": fecha_columna,
        "fuga": False,
    }


__all__ = [
    "FEATURES_CONTEXTO_POR_DEFECTO",
    "PARAMETROS_CONTEXTO",
    "ConfiguracionContextoOleadas",
    "ModeloContextoOleadas",
    "unir_contexto_asof",
]

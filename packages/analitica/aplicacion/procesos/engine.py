"""Motor de proyección configurable y replay histórico ciego.

Este módulo separa tres decisiones que antes estaban mezcladas:

* qué emisión histórica se reconstruye;
* qué modelo produce frutos por planta y peso;
* qué escenario matemático se quiere explorar.

El entrenamiento de ``Componentes_identidad`` solo usa resultados con objetivo anterior a la
emisión seleccionada. Los reales posteriores viajan únicamente como columna de evaluación,
nunca como entrada. El calendario predeterminado se estima con una rejilla histórica de
ocurrencia y ceros explícitos; ``r09_publicado`` queda disponible como modo de comparación.
Esa elección y sus limitaciones se registran en cada fila y no se ocultan bajo el nombre
"fenológico".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from analitica.dominio.asof import enriquecer_asof
from analitica.dominio.modelos.componentes import (
    FEATURES_FRUTOS,
    FEATURES_PESO,
    challengers_componentes,
)
from analitica.dominio.modelos.ocurrencia import (
    OccurrenceConfig,
    construir_rejilla_ocurrencia,
    estimar_ocurrencia,
)
from analitica.dominio.versiones import banda_horizonte

from .estado_oleadas import NOMBRE_MODELO as NOMBRE_MODELO_ESTADO_OLEADAS
from .estado_oleadas import proyectar_estado_oleadas_asof
from .gauss_estado_integrado import NOMBRE_MODELO as NOMBRE_MODELO_GAUSS_ESTADO
from .gauss_estado_integrado import (
    construir_lotes_gauss_estado,
    proyectar_gauss_estado_asof,
)


class ProjectionNotReady(RuntimeError):
    """La solicitud es válida, pero la historia disponible no permite emitir."""


@dataclass(frozen=True)
class ProjectionScenario:
    """Escenario mecánico sobre las piezas de la identidad de rendimiento.

    Estos porcentajes no son efectos causales. Expresan «qué pasa con el volumen si cambio
    manualmente esta pieza», manteniendo constantes las demás. Para intervenir clima, ETo,
    riego o nutrición se necesita un modelo local de respuesta o un experimento; por eso no
    se aceptan aquí como multiplicadores escondidos.
    """

    nombre: str = "base"
    frutos_pct: float = 0.0
    peso_pct: float = 0.0
    plantas_pct: float = 0.0
    desplazamiento_semanas: int = 0
    parametros: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for nombre, valor in (
            ("frutos_pct", self.frutos_pct),
            ("peso_pct", self.peso_pct),
            ("plantas_pct", self.plantas_pct),
        ):
            if not np.isfinite(valor) or valor <= -100:
                raise ValueError(f"{nombre} debe ser mayor que -100 y finito")
        if not -52 <= int(self.desplazamiento_semanas) <= 52:
            raise ValueError("desplazamiento_semanas debe estar entre -52 y 52")

    @property
    def factor_frutos(self) -> float:
        return 1.0 + self.frutos_pct / 100.0

    @property
    def factor_peso(self) -> float:
        return 1.0 + self.peso_pct / 100.0

    @property
    def factor_plantas(self) -> float:
        return 1.0 + self.plantas_pct / 100.0

    @property
    def factor_kg(self) -> float:
        return self.factor_frutos * self.factor_peso * self.factor_plantas


@dataclass(frozen=True)
class ProjectionConfig:
    """Contrato de una proyección desde una fecha de emisión."""

    fecha_emision: pd.Timestamp | None = None
    horizonte_semanas: int = 10
    modelo: str = "Componentes_identidad"
    calendario: str = "ocurrencia"
    horizontes: tuple[int, ...] | None = None
    minimo_entrenamiento: int = 300
    escenario: ProjectionScenario = field(default_factory=ProjectionScenario)
    peso_forma_gaussiana: float = 1.0

    def __post_init__(self) -> None:
        if not 1 <= int(self.horizonte_semanas) <= 52:
            raise ValueError("horizonte_semanas debe estar entre 1 y 52")
        if self.horizontes is not None:
            invalidos = [h for h in self.horizontes if not 1 <= int(h) <= 52]
            if invalidos:
                raise ValueError(f"horizontes inválidos: {invalidos}")
        if self.modelo not in {
            "Componentes_identidad",
            "R09_publicado",
            NOMBRE_MODELO_ESTADO_OLEADAS,
            NOMBRE_MODELO_GAUSS_ESTADO,
        }:
            raise ValueError(
                "modelo debe ser Componentes_identidad, R09_publicado, "
                f"{NOMBRE_MODELO_ESTADO_OLEADAS} o {NOMBRE_MODELO_GAUSS_ESTADO}"
            )
        if self.calendario not in {"ocurrencia", "r09_publicado"}:
            raise ValueError("calendario debe ser ocurrencia o r09_publicado")
        if self.modelo == NOMBRE_MODELO_GAUSS_ESTADO and int(self.horizonte_semanas) < 6:
            raise ValueError(
                f"{NOMBRE_MODELO_GAUSS_ESTADO} requiere un horizonte de al menos seis semanas"
            )
        if not 0 <= float(self.peso_forma_gaussiana) <= 1:
            raise ValueError("peso_forma_gaussiana debe estar entre cero y uno")


def variables_de_modelo() -> dict[str, list[str]]:
    """Variables declaradas por los dos componentes, para UI, auditoría y model card."""

    return {
        "frutos_por_planta": list(FEATURES_FRUTOS),
        "peso_baya_g": list(FEATURES_PESO),
        "no_causales": [
            "Las variables explican predicción, no una intervención causal.",
            "Clima futuro, nutrición, suelo, polinización y sanidad no se imputan.",
        ],
    }


def _normalizar_fecha(valor: object) -> pd.Timestamp:
    fecha = pd.Timestamp(valor)
    if pd.isna(fecha):
        raise ValueError("fecha_emision no puede ser nula")
    return fecha.normalize()


def _elegir_emision(base: pd.DataFrame, solicitada: object | None) -> pd.Timestamp:
    fechas = pd.to_datetime(base.fecha_emision, errors="coerce").dropna().sort_values().unique()
    if len(fechas) == 0:
        raise ProjectionNotReady("No hay emisiones R09 con fecha válida.")
    if solicitada is None:
        return pd.Timestamp(fechas[-1]).normalize()
    fecha = _normalizar_fecha(solicitada)
    anteriores = [
        pd.Timestamp(f).normalize() for f in fechas if pd.Timestamp(f).normalize() <= fecha
    ]
    if not anteriores:
        raise ProjectionNotReady("La fecha solicitada es anterior a la primera emisión disponible.")
    return max(anteriores)


def _panel_completo(r09: pd.DataFrame, datos, panel_asof: pd.DataFrame | None) -> pd.DataFrame:
    if panel_asof is not None and not panel_asof.empty:
        return panel_asof.copy()
    if datos is None:
        return pd.DataFrame()
    objetivos = r09[r09.modelo == "R09_publicado"].drop_duplicates(
        ["campania", "lote_id", "fecha_emision", "fecha_objetivo"]
    )
    return enriquecer_asof(objetivos, datos)


def _aplicar_escenario(predicciones: pd.DataFrame, escenario: ProjectionScenario) -> pd.DataFrame:
    salida = predicciones.copy()
    for columna in ("plantas", "frutos_por_planta", "peso_baya_g", "p10_kg", "p50_kg", "p90_kg"):
        if columna not in salida:
            salida[columna] = np.nan
    if (
        np.isclose(escenario.factor_frutos, 1.0)
        and np.isclose(escenario.factor_peso, 1.0)
        and np.isclose(escenario.factor_plantas, 1.0)
        and int(escenario.desplazamiento_semanas) == 0
    ):
        return salida
    salida["plantas"] = pd.to_numeric(salida.plantas, errors="coerce") * escenario.factor_plantas
    salida["frutos_por_planta"] = (
        pd.to_numeric(salida.frutos_por_planta, errors="coerce") * escenario.factor_frutos
    )
    salida["peso_baya_g"] = (
        pd.to_numeric(salida.peso_baya_g, errors="coerce") * escenario.factor_peso
    )
    identidad = salida.plantas * salida.frutos_por_planta * salida.peso_baya_g / 1000
    base_p50 = pd.to_numeric(salida.p50_kg, errors="coerce")
    modelos = salida.get("modelo", pd.Series("", index=salida.index)).astype(str)
    factor_componentes = identidad / base_p50.replace(0, np.nan)
    factor_componentes = factor_componentes.replace([np.inf, -np.inf], np.nan)
    factor = factor_componentes.where(
        modelos.eq("Componentes_identidad"), escenario.factor_kg
    ).fillna(escenario.factor_kg)
    for columna in ("p10_kg", "p50_kg", "p90_kg"):
        salida[columna] = pd.to_numeric(salida[columna], errors="coerce") * factor
    # Para un modelo que sí publica componentes, el P50 debe salir de la identidad. Para R09
    # se conserva su P50 publicado porque no estamos fingiendo tener componentes propios.
    if "modelo" in salida and salida.modelo.eq("Componentes_identidad").all():
        salida["p50_kg"] = identidad.clip(lower=0)
    salida["p10_kg"] = np.minimum(salida.p10_kg, salida.p50_kg).clip(lower=0)
    salida["p90_kg"] = np.maximum(salida.p90_kg, salida.p50_kg)
    if escenario.desplazamiento_semanas:
        delta = pd.Timedelta(weeks=int(escenario.desplazamiento_semanas))
        salida["fecha_objetivo"] = pd.to_datetime(salida.fecha_objetivo) + delta
        salida["horizonte_semanas"] = (
            (salida.fecha_objetivo - pd.to_datetime(salida.fecha_emision)).dt.days // 7
        ).astype(int)
        salida["banda_horizonte"] = salida.horizonte_semanas.map(banda_horizonte)
    return salida


def _anotar_trazabilidad(
    salida: pd.DataFrame,
    config: ProjectionConfig,
    emision: pd.Timestamp,
    *,
    calendario_fuente: str,
    calendario_limitacion: str,
) -> pd.DataFrame:
    variables = variables_de_modelo()
    escenario = config.escenario
    metadatos = {
        "modo": "ciega_asof",
        "modelo": config.modelo,
        "fecha_emision": emision.isoformat(),
        "calendario_fuente": calendario_fuente,
        "calendario_limitacion": calendario_limitacion,
        "variables_frutos": variables["frutos_por_planta"],
        "variables_peso": variables["peso_baya_g"],
        "escenario": {
            "nombre": escenario.nombre,
            "frutos_pct": float(escenario.frutos_pct),
            "peso_pct": float(escenario.peso_pct),
            "plantas_pct": float(escenario.plantas_pct),
            "desplazamiento_semanas": int(escenario.desplazamiento_semanas),
            "parametros": dict(escenario.parametros),
            "interpretacion": "escenario mecánico, no efecto causal",
        },
        "peso_forma_gaussiana": float(config.peso_forma_gaussiana),
        "informacion_no_usada": [
            "resultados posteriores a la emisión",
            "clima futuro observado",
            "nutrición, suelo, polinización y sanidad no registradas",
        ],
    }
    salida["modo_proyeccion"] = "ciega_asof"
    salida["corte_asof"] = emision
    salida["calendario_fuente"] = calendario_fuente
    if config.modelo in {
        NOMBRE_MODELO_ESTADO_OLEADAS,
        NOMBRE_MODELO_GAUSS_ESTADO,
    } and "componentes" in salida:
        salida["componentes"] = salida["componentes"].map(
            lambda valor: {
                **valor,
                "trazabilidad_proyeccion": metadatos.copy(),
            }
            if isinstance(valor, dict)
            else metadatos.copy()
        )
    else:
        salida["componentes"] = [metadatos.copy() for _ in range(len(salida))]
    return salida


def _adjuntar_real_para_evaluacion(salida: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    """Reincorpora el observado después de predecir, únicamente para backtesting.

    Las filas de la emisión evaluada se excluyen del entrenamiento de componentes. El
    observado se une al final para que un replay histórico pueda medir WAPE/MAE sin que
    el modelo lo haya visto. En una emisión futura normalmente quedará ``NaN``.
    """
    claves = ["campania", "lote_id", "fecha_emision", "fecha_objetivo"]
    columnas = [
        "real_kg",
        "peso_real_g",
        "plantas_reales",
        "frutos_reales_por_planta",
        "frutos_reales_por_planta_catalogo",
    ]
    if set(claves) - set(salida) or set(claves) - set(base):
        return salida
    disponibles = [c for c in columnas if c in base]
    if not disponibles:
        return salida
    observado = (
        base[claves + disponibles]
        .groupby(claves, as_index=False, dropna=False)
        .agg({c: "max" for c in disponibles})
    )
    izquierda = salida.copy()
    derecha = observado.copy()
    # R09 de PostgreSQL suele traer lote_id numérico; los adaptadores exportados lo
    # representan como texto (y el integrado normaliza siempre a texto). La identidad
    # es la misma aunque el dtype no lo sea, por lo que se normaliza solo en esta unión.
    for columna in claves:
        izquierda[columna] = izquierda[columna].astype("string")
        derecha[columna] = derecha[columna].astype("string")
    izquierda = izquierda.drop(
        columns=[c for c in disponibles if c in izquierda], errors="ignore"
    )
    return izquierda.merge(derecha, on=claves, how="left", validate="1:1")


def proyectar_desde_corte(
    r09: pd.DataFrame,
    *,
    datos=None,
    panel_asof: pd.DataFrame | None = None,
    panel_oleadas: pd.DataFrame | None = None,
    config: ProjectionConfig | None = None,
) -> pd.DataFrame:
    """Emite una proyección desde una fecha conocida sin entrenar con su futuro.

    ``real_kg`` se conserva para validar retrospectivamente la predicción, pero ninguna
    llamada de entrenamiento de componentes recibe las filas con ``fecha_objetivo >=`` la
    emisión elegida.
    """

    config = config or ProjectionConfig()
    base = r09[r09.modelo == "R09_publicado"].copy()
    if base.empty:
        raise ProjectionNotReady("No hay filas R09_publicado para construir la proyección.")
    base["fecha_emision"] = pd.to_datetime(base.fecha_emision, errors="coerce").dt.normalize()
    base["fecha_objetivo"] = pd.to_datetime(base.fecha_objetivo, errors="coerce").dt.normalize()
    emision = _elegir_emision(base, config.fecha_emision)
    panel = _panel_completo(r09, datos, panel_asof)

    calendario_fuente = "R09_publicado"
    calendario_limitacion = (
        "El calendario es el publicado por R09; esta corrida no intenta estimar ocurrencia."
    )
    if config.modelo == "R09_publicado":
        salida = base[base.fecha_emision == emision].copy()
    elif config.modelo == NOMBRE_MODELO_ESTADO_OLEADAS:
        # El challenger necesita el panel completo para aprender de cierres anteriores,
        # pero solo se entrega al usuario la emisión solicitada. Los horizontes 0 de R09
        # no son válidos para el contrato as-of y se excluyen antes de normalizar.
        base_estado = base[base.fecha_objetivo.gt(base.fecha_emision)].copy()
        salida_estado, _ = proyectar_estado_oleadas_asof(
            base_estado,
            panel_oleadas=panel_oleadas,
            horizonte_semanas=config.horizonte_semanas,
        )
        salida = salida_estado[salida_estado.fecha_emision == emision].copy()
        calendario_fuente = "R09_publicado"
        calendario_limitacion = (
            "El nivel y el calendario vienen de R09; el estado reciente se corrige con "
            "cierres estrictamente anteriores y las oleadas son una descomposición opcional."
        )
    elif config.modelo == NOMBRE_MODELO_GAUSS_ESTADO:
        if datos is None:
            raise ProjectionNotReady(
                f"{NOMBRE_MODELO_GAUSS_ESTADO} requiere datos con maestro de lotes y poda."
            )
        maestro = getattr(datos, "lotes", pd.DataFrame())
        poda = getattr(datos, "poda", pd.DataFrame())
        try:
            lotes_gauss, metadata_lotes = construir_lotes_gauss_estado(
            base,
            maestro_lotes=maestro,
            poda=poda,
            cosecha=getattr(datos, "cosecha", pd.DataFrame()),
        )
        except (TypeError, ValueError) as exc:
            raise ProjectionNotReady(
                f"{NOMBRE_MODELO_GAUSS_ESTADO} no puede reconstruir lotes: {exc}"
            ) from exc
        salida, metadata_gauss = proyectar_gauss_estado_asof(
            base,
            lotes_gauss,
            getattr(datos, "cosecha", pd.DataFrame()),
            emision,
            semanas=config.horizonte_semanas,
            peso_forma_gaussiana=config.peso_forma_gaussiana,
            config_estado=None,
            panel_oleadas_manual=(
                panel_oleadas
                if panel_oleadas is not None
                and {
                    "campania",
                    "modulo",
                    "turno",
                    "lote",
                    "fecha_emision",
                    "fecha_objetivo",
                    "horizonte_semanas",
                    "kg",
                    "kg_ola_1",
                    "kg_ola_2",
                    "kg_ola_3",
                }
                <= set(panel_oleadas.columns)
                else None
            ),
        )
        # La información del adaptador queda en cada fila para que una proyección viva
        # pueda explicar por qué un lote quedó fuera del universo Gaussiano.
        metadata_gauss["lotes"] = metadata_lotes
        resumen_integracion = {
            "lotes_panel": metadata_lotes["lotes_panel"],
            "lotes_validos": metadata_lotes["lotes_validos"],
            "lotes_descartados": metadata_lotes["lotes_descartados"],
            "filas_h6_extendido": metadata_gauss["filas_h6_extendido"],
            "etiqueta_causal": False,
        }
        salida["componentes"] = salida.componentes.map(
            lambda valor: {
                **valor,
                "resumen_integracion_gauss_estado": resumen_integracion,
            }
            if isinstance(valor, dict)
            else {"resumen_integracion_gauss_estado": resumen_integracion}
        )
        calendario_fuente = "R09_publicado + forma_gaussiana_asof"
        calendario_limitacion = (
            "El nivel operativo viene de R09; la forma H1-H6 se construye con la curva "
            "Gaussiana as-of y el estado reciente usa solo cierres anteriores."
        )
    else:
        base_modelo = base.assign(modelo="R09_publicado")
        if config.calendario == "ocurrencia":
            entrenamiento, futuro = construir_rejilla_ocurrencia(
                base_modelo, emision=emision, horizonte=config.horizonte_semanas
            )
            if entrenamiento.empty or futuro.empty:
                raise ProjectionNotReady("No hay rejilla histórica para estimar ocurrencia.")
            if datos is not None:
                panel_futuro = enriquecer_asof(
                    futuro.drop(columns=["real_kg"], errors="ignore"), datos
                )
                panel_modelo = pd.concat([panel, panel_futuro], ignore_index=True, sort=False)
            else:
                panel_modelo = panel
            ampliado = pd.concat(
                [base_modelo[base_modelo.fecha_emision < emision], futuro],
                ignore_index=True,
                sort=False,
            )
            candidatos = challengers_componentes(
                ampliado,
                panel_asof=panel_modelo,
                minimo_entrenamiento=config.minimo_entrenamiento,
                heredar_calendario=False,
            )
            ocurrencia = estimar_ocurrencia(
                entrenamiento,
                futuro,
                panel_asof=panel_modelo,
                config=OccurrenceConfig(minimo_entrenamiento=config.minimo_entrenamiento),
            )
            claves = ["campania", "lote_id", "fecha_emision", "fecha_objetivo"]
            candidatos = candidatos.merge(
                ocurrencia[[*claves, "probabilidad_cosecha", "ocurrencia_gate"]],
                on=claves,
                how="left",
                validate="1:1",
            )
            gate = ~candidatos.ocurrencia_gate.astype("boolean").fillna(False).to_numpy(dtype=bool)
            candidatos.loc[gate, ["frutos_por_planta", "p50_kg", "p10_kg", "p90_kg"]] = 0.0
            calendario_fuente = "modelo_ocurrencia"
            calendario_limitacion = (
                "La ocurrencia se estima con una rejilla histórica con ceros de cosecha; "
                "la probabilidad no es una causa ni una garantía de cosecha."
            )
        else:
            candidatos = challengers_componentes(
                base_modelo,
                panel_asof=panel,
                minimo_entrenamiento=config.minimo_entrenamiento,
                heredar_calendario=True,
            )
        salida = candidatos[candidatos.fecha_emision == emision].copy()
        if salida.empty:
            raise ProjectionNotReady(
                "Componentes_identidad no emitió para esta fecha: historia as-of insuficiente."
            )
    # La emisión operativa R09 incluye la semana de publicación (horizonte 0).
    # Se conserva para planificación diaria, mientras el backtesting mantiene su
    # regla más estricta y solo evalúa horizontes emitidos antes de la semana objetivo.
    horizonte_minimo = 0 if config.modelo == "R09_publicado" else 1
    salida = salida[
        salida.horizonte_semanas.between(horizonte_minimo, config.horizonte_semanas)
    ].copy()
    salida = _adjuntar_real_para_evaluacion(salida, base)
    if config.horizontes is not None:
        permitidos = {int(h) for h in config.horizontes}
        salida = salida[salida.horizonte_semanas.isin(permitidos)].copy()
    if salida.empty:
        raise ProjectionNotReady("No hay semanas objetivo dentro del horizonte solicitado.")
    salida = _aplicar_escenario(salida, config.escenario)
    if config.escenario.desplazamiento_semanas:
        # El desplazamiento cambia el objetivo: el observado de la fecha original ya no
        # es comparable con esta hipótesis mecánica.
        for columna in (
            "real_kg",
            "peso_real_g",
            "plantas_reales",
            "frutos_reales_por_planta",
            "frutos_reales_por_planta_catalogo",
        ):
            if columna in salida:
                salida[columna] = np.nan
    return _anotar_trazabilidad(
        salida,
        config,
        emision,
        calendario_fuente=calendario_fuente,
        calendario_limitacion=calendario_limitacion,
    )


def replay_historico_ciego(
    r09: pd.DataFrame,
    *,
    fecha_emision: object,
    datos=None,
    panel_asof: pd.DataFrame | None = None,
    horizonte_semanas: int = 10,
    minimo_entrenamiento: int = 300,
) -> pd.DataFrame:
    """Alias explícito para una prueba retrospectiva que separa predicción y evaluación."""

    return proyectar_desde_corte(
        r09,
        datos=datos,
        panel_asof=panel_asof,
        config=ProjectionConfig(
            fecha_emision=pd.Timestamp(fecha_emision),
            horizonte_semanas=horizonte_semanas,
            modelo="Componentes_identidad",
            minimo_entrenamiento=minimo_entrenamiento,
        ),
    )
